"""AI features for the Review step.

1. explain_unusual(): one short reason per flagged salary (one Gemini call for all of them)
2. month_summary():   a short report for the finance manager
"""

from __future__ import annotations

import calendar
import json
from collections import Counter
from datetime import datetime

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..models import PayrollMonth, Salary, SalaryLine, Station
from ..payroll.engine import money, previous_period
from .gemini import AIError, generate, generate_json

MAX_EXPLAIN = 150


def _label(period: str) -> str:
    y, m = map(int, period.split("-"))
    return f"{calendar.month_name[m]} {y}"


def explain_unusual(db: Session, month: PayrollMonth) -> int:
    flagged = [s for s in db.scalars(select(Salary).where(Salary.month_id == month.id))
               if "unusual_change" in s.flags][:MAX_EXPLAIN]
    if not flagged:
        return 0
    prev_label = _label(previous_period(month.period))

    facts = []
    for s in flagged:
        deductions = Counter(l.type for l in s.lines if l.kind == "Deduction" and l.amount_applied > 0)
        facts.append({
            "id": s.driver_id,
            "net_now": s.net, "net_last_month": s.previous_net,
            "days_worked": s.days_worked, "prepaid_deliveries": s.prepaid_count, "cod_deliveries": s.cod_count,
            "fixed_pay": s.fixed_pay, "delivery_pay": money(s.prepaid_pay + s.cod_pay), "bonuses": s.bonuses,
            "deducted": s.deductions_applied, "deduction_types": dict(deductions),
            "carried_to_next_month": s.carried_forward,
            "calculated_comparison": s.change_reason,
        })

    prompt = f"""You help a payroll accountant at a delivery company in Saudi Arabia review driver salaries.
These drivers' net pay changed by more than 30% compared with {prev_label}.
For EACH driver write ONE short sentence (max 25 words) explaining the main reason in plain English.
Start with "Up" or "Down" and the SAR amount. Mention the biggest cause first (for example fewer
working days, fewer deliveries, a lost parcel or traffic fine, a bonus). Use ONLY the numbers given.
Do not invent anything. Do not give advice.

Return JSON: an object where each key is the driver id and the value is the sentence.

Drivers:
{json.dumps(facts, ensure_ascii=False)}"""

    answer = generate_json(prompt)
    if not isinstance(answer, dict):
        raise AIError("Gemini answered, but not in the expected format - try again")
    count = 0
    for s in flagged:
        text = answer.get(s.driver_id)
        if isinstance(text, str) and text.strip():
            s.ai_reason = text.strip()[:400]
            count += 1
    db.commit()
    return count


def month_summary(db: Session, month: PayrollMonth) -> str:
    S = Salary
    rows = db.execute(
        select(func.count(), func.sum(S.gross), func.sum(S.deductions_applied), func.sum(S.net),
               func.sum(S.carried_forward))
        .where(S.month_id == month.id)
    ).one()
    if not rows[0]:
        raise AIError("Calculate salaries first")

    prev = db.scalar(select(PayrollMonth).where(PayrollMonth.period == previous_period(month.period)))
    prev_rows = None
    if prev:
        prev_rows = db.execute(
            select(func.count(), func.sum(S.net), func.sum(S.deductions_applied)).where(S.month_id == prev.id)
        ).one()

    by_type = dict(db.execute(
        select(SalaryLine.type, func.sum(SalaryLine.amount_applied))
        .join(S, SalaryLine.salary_id == S.id)
        .where(S.month_id == month.id, SalaryLine.kind == "Deduction")
        .group_by(SalaryLine.type)
    ).all())
    flags = Counter(f for fl in db.scalars(select(S.flags).where(S.month_id == month.id)) for f in fl)
    stations = db.execute(
        select(Station.name, func.sum(S.deductions_applied).label("ded"), func.sum(S.net))
        .join(S, S.station_id == Station.id).where(S.month_id == month.id)
        .group_by(Station.id).order_by(func.sum(S.deductions_applied).desc()).limit(3)
    ).all()
    cash = db.scalar(select(func.sum(S.net)).where(S.month_id == month.id, S.payment_method == "Cash")) or 0

    facts = {
        "month": _label(month.period),
        "drivers_paid": rows[0], "gross_sar": money(rows[1] or 0), "deducted_sar": money(rows[2] or 0),
        "net_sar": money(rows[3] or 0), "carried_to_next_month_sar": money(rows[4] or 0),
        "cash_at_stations_sar": money(cash), "bank_transfer_sar": money((rows[3] or 0) - cash),
        "deductions_by_type_sar": {k: money(v or 0) for k, v in by_type.items()},
        "flag_counts": dict(flags),
        "stations_with_most_deductions": [
            {"station": r[0], "deducted_sar": money(r[1] or 0)} for r in stations
        ],
        "last_month": None if not prev_rows or not prev_rows[0] else {
            "month": _label(prev.period), "drivers_paid": prev_rows[0],
            "net_sar": money(prev_rows[1] or 0), "deducted_sar": money(prev_rows[2] or 0),
        },
    }

    prompt = f"""You write a short payroll summary for the finance manager of a delivery company in Saudi Arabia.
Use ONLY these numbers. Write 4 to 6 short bullet points in plain English, each starting with "- ".
Cover: total to pay (cash vs bank), change vs last month if given, the biggest deduction types,
how many salaries need review (unusual_change, capped), and stations with most deductions.
No greeting, no advice, no invented numbers. Format SAR amounts like 1,234,567 SAR.

Data:
{json.dumps(facts, ensure_ascii=False)}"""

    text = generate(prompt)
    month.ai_summary = text.strip()[:3000]
    month.ai_summary_at = datetime.now()
    db.commit()
    return month.ai_summary
