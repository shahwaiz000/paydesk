"""Driver search and driver profile (salary history across months)."""

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import or_, select
from sqlalchemy.orm import Session, selectinload

from ..database import get_db
from ..deps import require_roles
from ..models import ACCOUNTANT, CASHIER, FINANCE_MANAGER, Driver, PayrollMonth, Salary, Station, User

router = APIRouter(prefix="/api/drivers", tags=["drivers"])
can_search = require_roles(ACCOUNTANT, FINANCE_MANAGER, CASHIER)


def driver_out(d: Driver) -> dict:
    return {
        "id": d.id, "name": d.name, "station": d.station.name, "station_code": d.station.code,
        "city": d.station.city, "payment_method": d.payment_method,
        "joining_date": d.joining_date.isoformat(),
        "leaving_date": d.leaving_date.isoformat() if d.leaving_date else None,
        "phone": d.phone, "iban_last4": d.iban[-4:] if d.iban else None,
    }


@router.get("")
def search_drivers(q: str = "", station: str | None = None, limit: int = 50,
                   db: Session = Depends(get_db), user: User = Depends(can_search)):
    stmt = select(Driver).join(Driver.station).options(selectinload(Driver.station))
    if user.role == CASHIER:                       # cashiers only see their own station
        stmt = stmt.where(Driver.station_id == user.station_id)
    elif station:
        stmt = stmt.where(Station.code == station)
    text = q.strip()
    if text:
        like = f"%{text}%"
        stmt = stmt.where(or_(Driver.id.ilike(like), Driver.name.ilike(like),
                              Driver.phone.ilike(like), Driver.iqama_no.ilike(like)))
    limit = max(1, min(limit, 200))
    rows = db.scalars(stmt.order_by(Driver.name).limit(limit + 1)).all()
    return {"items": [driver_out(d) for d in rows[:limit]], "more": len(rows) > limit}


@router.get("/{driver_id}")
def driver_profile(driver_id: str, db: Session = Depends(get_db), user: User = Depends(can_search)):
    d = db.get(Driver, driver_id.strip().upper())
    if d is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Driver not found")
    if user.role == CASHIER and d.station_id != user.station_id:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "This driver is not at your station")

    history = db.execute(
        select(PayrollMonth.id, PayrollMonth.period, Salary.days_worked, Salary.prepaid_count, Salary.cod_count,
               Salary.gross, Salary.deductions_applied, Salary.carried_forward, Salary.net, Salary.flags)
        .join(Salary, Salary.month_id == PayrollMonth.id)
        .where(Salary.driver_id == d.id)
        .order_by(PayrollMonth.period.desc())
    ).all()
    data = driver_out(d)
    data["months"] = [{
        "month_id": r[0], "period": r[1], "days_worked": r[2], "prepaid_count": r[3], "cod_count": r[4],
        "gross": r[5], "deductions": r[6], "carried_forward": r[7], "net": r[8], "flags": r[9],
    } for r in history]
    return data
