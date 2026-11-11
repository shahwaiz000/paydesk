"""Salary calculation, salary list, totals and payslip (Stage 4)."""

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session, selectinload

from ..database import get_db
from ..deps import get_current_user, require_roles
from ..models import (
    ACCOUNTANT, CASHIER, DRIVER, FINANCE_MANAGER, DeliveryDay, Driver, PayrollMonth, Salary, Station, User,
)
from ..payroll.engine import calculate_month, get_settings, money
from .months import get_month

router = APIRouter(prefix="/api/months/{month_id}", tags=["salaries"])
FINAL_STATUSES = ("approved",)            # approved by the finance manager = final and locked
can_view_all = require_roles(ACCOUNTANT, FINANCE_MANAGER)


def salary_row(s: Salary) -> dict:
    return {
        "driver_id": s.driver_id, "name": s.driver.name, "station": s.station.name, "station_code": s.station.code,
        "payment_method": s.payment_method, "days_worked": s.days_worked, "full_month": s.full_month,
        "fixed_pay": s.fixed_pay, "prepaid_count": s.prepaid_count, "prepaid_pay": s.prepaid_pay,
        "cod_count": s.cod_count, "cod_pay": s.cod_pay, "bonuses": s.bonuses, "gross": s.gross,
        "deductions_due": s.deductions_due, "deductions_applied": s.deductions_applied,
        "carried_forward": s.carried_forward, "net": s.net, "previous_net": s.previous_net, "flags": s.flags,
        "change_reason": s.change_reason, "ai_reason": s.ai_reason,
    }


@router.post("/calculate")
def calculate(month_id: int, db: Session = Depends(get_db), _: User = Depends(require_roles(ACCOUNTANT))):
    month = get_month(db, month_id)
    if month.status not in ("ready", "calculated"):
        raise HTTPException(status.HTTP_400_BAD_REQUEST,
                            "All 4 files must be imported without errors before calculating")
    return calculate_month(db, month)


@router.get("/summary")
def summary(month_id: int, db: Session = Depends(get_db), _: User = Depends(can_view_all)):
    month = get_month(db, month_id)
    S = Salary
    total = db.execute(
        select(func.count(), func.sum(S.gross), func.sum(S.deductions_applied), func.sum(S.carried_forward),
               func.sum(S.net), func.sum(S.fixed_pay), func.sum(S.prepaid_pay), func.sum(S.cod_pay),
               func.sum(S.bonuses))
        .where(S.month_id == month.id)
    ).one()
    by_method = dict(db.execute(
        select(S.payment_method, func.sum(S.net)).where(S.month_id == month.id).group_by(S.payment_method)
    ).all())
    stations = db.execute(
        select(Station.code, Station.name, func.count(S.id), func.sum(S.net),
               func.sum(S.net).filter(S.payment_method == "Cash"), func.count(S.id).filter(S.payment_method == "Cash"))
        .join(S, S.station_id == Station.id).where(S.month_id == month.id)
        .group_by(Station.id).order_by(Station.code)
    ).all()
    flagged = {}
    for flags in db.scalars(select(S.flags).where(S.month_id == month.id)):
        for f in flags:
            flagged[f] = flagged.get(f, 0) + 1
    return {
        "period": month.period, "status": month.status,
        "drivers": total[0], "gross": money(total[1] or 0), "deductions": money(total[2] or 0),
        "carried_forward": money(total[3] or 0), "net": money(total[4] or 0),
        "fixed": money(total[5] or 0), "prepaid": money(total[6] or 0), "cod": money(total[7] or 0),
        "bonuses": money(total[8] or 0),
        "cash_net": money(by_method.get("Cash") or 0), "bank_net": money(by_method.get("Bank") or 0),
        "flags": flagged,
        "ai_summary": month.ai_summary,
        "ai_summary_at": month.ai_summary_at.isoformat() if month.ai_summary_at else None,
        "stations": [
            {"code": r[0], "name": r[1], "drivers": r[2], "net": money(r[3] or 0),
             "cash_needed": money(r[4] or 0), "cash_drivers": r[5]}
            for r in stations
        ],
    }


@router.get("/salaries")
def list_salaries(month_id: int, station: str | None = None, q: str | None = None, flag: str | None = None,
                  payment: str | None = None, page: int = 1, size: int = 50,
                  db: Session = Depends(get_db), _: User = Depends(can_view_all)):
    month = get_month(db, month_id)
    stmt = (select(Salary).join(Salary.driver).join(Salary.station)
            .where(Salary.month_id == month.id)
            .options(selectinload(Salary.driver), selectinload(Salary.station)))
    if station:
        stmt = stmt.where(Station.code == station)
    if payment:
        stmt = stmt.where(Salary.payment_method == payment)
    if q:
        like = f"%{q.strip()}%"
        stmt = stmt.where(or_(Driver.id.ilike(like), Driver.name.ilike(like)))
    rows = db.scalars(stmt.order_by(Station.code, Driver.id)).all()
    if flag:
        rows = [r for r in rows if flag in r.flags]
    size = max(1, min(size, 200))
    start = (max(page, 1) - 1) * size
    return {"total": len(rows), "page": page, "size": size,
            "items": [salary_row(s) for s in rows[start:start + size]]}


@router.get("/salaries/{driver_id}")
def payslip(month_id: int, driver_id: str, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    month = get_month(db, month_id)
    s = db.scalar(select(Salary).where(Salary.month_id == month.id, Salary.driver_id == driver_id.upper()))
    if s is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "No salary for this driver this month")

    allowed = (
        user.role in (ACCOUNTANT, FINANCE_MANAGER)
        or (user.role == CASHIER and user.station_id == s.station_id)
        or (user.role == DRIVER and user.driver_id == s.driver_id)
    )
    if not allowed:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "You can't see this payslip")

    return build_payslip(db, month, s)


def line_key(l) -> str:
    """Stays the same after a recalculation, so a dispute can find its line again."""
    return "|".join([l.kind, l.type, l.reference or "", l.day.isoformat() if l.day else "",
                     f"{l.amount_due:.2f}", l.carried_from or ""])


def build_payslip(db: Session, month: PayrollMonth, s: Salary) -> dict:
    """Everything on one payslip: totals, rates, every deduction/bonus line and the daily deliveries."""
    days = db.execute(
        select(DeliveryDay.day, DeliveryDay.prepaid, DeliveryDay.cod)
        .where(DeliveryDay.month_id == month.id, DeliveryDay.driver_id == s.driver_id)
        .order_by(DeliveryDay.day)
    ).all()
    settings = get_settings(db)
    data = salary_row(s)
    data.update({
        "month_id": month.id,
        "period": month.period,
        "month_status": month.status,
        "final": month.status in FINAL_STATUSES,
        "rates": {"fixed_salary": settings.fixed_salary, "prepaid_rate": settings.prepaid_rate,
                  "cod_rate": settings.cod_rate, "proration_days": settings.proration_days,
                  "deduction_cap_pct": settings.deduction_cap_pct},
        "joining_date": s.driver.joining_date.isoformat(),
        "leaving_date": s.driver.leaving_date.isoformat() if s.driver.leaving_date else None,
        "lines": [{
            "key": line_key(l), "kind": l.kind, "type": l.type, "amount_due": l.amount_due, "amount_applied": l.amount_applied,
            "carried": money(l.amount_due - l.amount_applied) if l.kind == "Deduction" else 0,
            "day": l.day.isoformat() if l.day else None, "reference": l.reference, "note": l.note,
            "plate_no": l.plate_no, "carried_from": l.carried_from,
        } for l in s.lines],
        "daily": [{
            "day": d.day.isoformat() if d.day else None, "prepaid": d.prepaid, "cod": d.cod,
            "earned": money(d.prepaid * settings.prepaid_rate + d.cod * settings.cod_rate),
        } for d in days],
    })
    return data


__all__ = ["router", "PayrollMonth"]
