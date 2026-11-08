"""The salary engine.

For every driver who worked at least one day this month:

    fixed pay   = 1,500 for a full month
                  1,500 / 30 x days worked for joiners and leavers (never more than 1,500)
    prepaid pay = prepaid deliveries x 2
    COD pay     = COD deliveries x 3
    gross       = fixed + prepaid + COD + bonuses

    deductions  = this month's deductions + anything carried from last month
    cap         = 50% of gross  (Saudi Labor Law, Article 93)
    applied     = deductions taken this month, oldest first, up to the cap
    carried     = the rest -> next month's payslip
    net         = gross - applied

All rates come from the PayrollSetting table, so the accountant can change them.
"""

from __future__ import annotations

import calendar
from collections import defaultdict
from datetime import date

from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session

from ..models import (
    Adjustment, DeliveryDay, Driver, PayrollMonth, PayrollSetting, Salary, SalaryLine,
)


def money(x: float) -> float:
    return round(x + 0.0000001, 2)


def get_settings(db: Session) -> PayrollSetting:
    s = db.scalar(select(PayrollSetting))
    if s is None:
        s = PayrollSetting(fixed_salary=1500, prepaid_rate=2, cod_rate=3, proration_days=30,
                           deduction_cap_pct=50, unusual_change_pct=30)
        db.add(s)
        db.flush()
    return s


def month_range(period: str) -> tuple[date, date]:
    y, m = map(int, period.split("-"))
    return date(y, m, 1), date(y, m, calendar.monthrange(y, m)[1])


def previous_period(period: str) -> str:
    y, m = map(int, period.split("-"))
    return f"{y - 1}-12" if m == 1 else f"{y}-{m - 1:02d}"


def fixed_pay(settings: PayrollSetting, days_worked: int, full_month: bool) -> float:
    if full_month:
        return settings.fixed_salary
    return money(min(settings.fixed_salary, settings.fixed_salary / settings.proration_days * days_worked))


def _month_name(period: str) -> str:
    y, m = map(int, period.split("-"))
    return calendar.month_name[m]


def _plural(n: int, word: str) -> str:
    word = word.lower()
    return f"{n} {word}" + ("" if n == 1 else "s")


def explain_change(prev: Salary, prev_period: str, net: float, days: int, fixed: float, prepaid: int,
                   prepaid_pay: float, cod: int, cod_pay: float, bonuses: float, applied: float,
                   lines: list[SalaryLine]) -> str:
    """Plain-English reason why net pay moved a lot since last month (no AI needed)."""
    diff = money(net - prev.net)
    types: dict[str, int] = defaultdict(int)
    for line in lines:
        if line.kind == "Deduction" and line.amount_applied > 0:
            types[line.type] += 1
    deduction_detail = ", ".join(_plural(n, t) for t, n in types.items()) or "none"
    parts = [
        ("fixed pay", fixed - prev.fixed_pay, f"{days} vs {prev.days_worked} days"),
        ("prepaid pay", prepaid_pay - prev.prepaid_pay, f"{prepaid} vs {prev.prepaid_count} deliveries"),
        ("COD pay", cod_pay - prev.cod_pay, f"{cod} vs {prev.cod_count} deliveries"),
        ("bonuses", bonuses - prev.bonuses, ""),
        ("deductions", -(applied - prev.deductions_applied), f"this month: {deduction_detail}"),
    ]
    parts = sorted([p for p in parts if abs(p[1]) >= 1], key=lambda p: -abs(p[1]))[:3]
    bits = []
    for name, delta, why in parts:
        if name == "deductions":   # deductions going UP means pay goes DOWN - say it in words
            label = f"{abs(delta):,.0f} more deducted" if delta < 0 else f"{abs(delta):,.0f} less deducted"
        else:
            label = f"{name} {'+' if delta > 0 else '-'}{abs(delta):,.0f}"
        bits.append(label + (f" ({why})" if why else ""))
    direction = "Up" if diff > 0 else "Down"
    return f"{direction} {abs(diff):,.0f} SAR vs {_month_name(prev_period)}: " + "; ".join(bits)


def clear_salaries(db: Session, month_id: int) -> None:
    ids = select(Salary.id).where(Salary.month_id == month_id)
    db.execute(delete(SalaryLine).where(SalaryLine.salary_id.in_(ids)))
    db.execute(delete(Salary).where(Salary.month_id == month_id))


def calculate_month(db: Session, month: PayrollMonth) -> dict:
    settings = get_settings(db)
    start, end = month_range(month.period)
    days_in_month = (end - start).days + 1

    clear_salaries(db, month.id)

    # Deliveries per driver
    counts = {
        r.driver_id: (int(r.prepaid or 0), int(r.cod or 0))
        for r in db.execute(
            select(DeliveryDay.driver_id, func.sum(DeliveryDay.prepaid).label("prepaid"),
                   func.sum(DeliveryDay.cod).label("cod"))
            .where(DeliveryDay.month_id == month.id).group_by(DeliveryDay.driver_id)
        )
    }

    # This month's deductions and bonuses
    adjustments: dict[str, list[Adjustment]] = defaultdict(list)
    for a in db.scalars(select(Adjustment).where(Adjustment.month_id == month.id)
                        .order_by(Adjustment.day, Adjustment.id)):
        adjustments[a.driver_id].append(a)

    # Last month: net (for the unusual-change check) and anything not yet deducted
    prev_period = previous_period(month.period)
    prev_month = db.scalar(select(PayrollMonth).where(PayrollMonth.period == prev_period))
    prev_salary: dict[str, Salary] = {}
    carried_in: dict[str, list[SalaryLine]] = defaultdict(list)
    if prev_month:
        for s in db.scalars(select(Salary).where(Salary.month_id == prev_month.id)):
            prev_salary[s.driver_id] = s
            for line in s.lines:
                left = money(line.amount_due - line.amount_applied)
                if line.kind == "Deduction" and left > 0:
                    carried_in[s.driver_id].append(line)

    drivers = db.scalars(
        select(Driver).where(Driver.joining_date <= end)
        .where((Driver.leaving_date.is_(None)) | (Driver.leaving_date >= start))
    ).all()

    totals = defaultdict(float)
    for d in drivers:
        first = max(d.joining_date, start)
        last = min(d.leaving_date or end, end)
        days = (last - first).days + 1
        full = days >= days_in_month

        prepaid, cod = counts.get(d.id, (0, 0))
        fixed = fixed_pay(settings, days, full)
        prepaid_pay = money(prepaid * settings.prepaid_rate)
        cod_pay = money(cod * settings.cod_rate)

        lines: list[SalaryLine] = []
        bonuses = 0.0
        # Carried from last month first (oldest debt is cleared first)
        for old in carried_in.get(d.id, []):
            left = money(old.amount_due - old.amount_applied)
            lines.append(SalaryLine(
                kind="Deduction", type=old.type, amount_due=left, amount_applied=0, day=old.day,
                reference=old.reference, note=old.note, plate_no=old.plate_no,
                carried_from=old.carried_from or prev_period,
            ))
        for a in adjustments.get(d.id, []):
            if a.kind == "Bonus":
                bonuses += a.amount
                lines.append(SalaryLine(kind="Bonus", type=a.type, amount_due=a.amount, amount_applied=a.amount,
                                        day=a.day, reference=a.reference, note=a.note))
            else:
                lines.append(SalaryLine(kind="Deduction", type=a.type, amount_due=a.amount, amount_applied=0,
                                        day=a.day, reference=a.reference, note=a.note, plate_no=a.plate_no))

        gross = money(fixed + prepaid_pay + cod_pay + bonuses)
        room = money(gross * settings.deduction_cap_pct / 100)
        due = applied = 0.0
        for line in lines:
            if line.kind != "Deduction":
                continue
            due += line.amount_due
            take = money(min(line.amount_due, max(room, 0)))
            line.amount_applied = take
            room = money(room - take)
            applied += take
        due, applied = money(due), money(applied)
        carried = money(due - applied)
        net = money(gross - applied)

        flags = []
        if carried > 0:
            flags.append("capped")
        if not full:
            flags.append("joiner" if d.joining_date >= start else "leaver")
        if prepaid + cod == 0:
            flags.append("no_deliveries")
        prev = prev_salary.get(d.id)
        previous = prev.net if prev else None
        reason = None
        if previous and abs(net - previous) / previous * 100 > settings.unusual_change_pct:
            flags.append("unusual_change")
            reason = explain_change(prev, prev_period, net, days, fixed, prepaid, prepaid_pay, cod, cod_pay,
                                    money(bonuses), applied, lines)

        db.add(Salary(
            month_id=month.id, driver_id=d.id, station_id=d.station_id, payment_method=d.payment_method,
            days_worked=days, full_month=full, fixed_pay=fixed, prepaid_count=prepaid, prepaid_pay=prepaid_pay,
            cod_count=cod, cod_pay=cod_pay, bonuses=money(bonuses), gross=gross, deductions_due=due,
            deductions_applied=applied, carried_forward=carried, net=net, previous_net=previous,
            flags=flags, lines=lines, change_reason=reason,
        ))
        totals["drivers"] += 1
        totals["gross"] += gross
        totals["deductions"] += applied
        totals["carried_forward"] += carried
        totals["net"] += net
        totals["cash_net" if d.payment_method == "Cash" else "bank_net"] += net

    month.status = "calculated"
    month.ai_summary = None          # numbers changed -> old AI summary is out of date
    month.ai_summary_at = None
    db.commit()
    return {k: (int(v) if k == "drivers" else money(v)) for k, v in totals.items()}
