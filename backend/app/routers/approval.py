"""Stage 10: approve & lock.

    calculated --(accountant: Send for approval)--> submitted --(finance manager: Approve)--> approved
                         ^                               |
                         +----(finance manager: Send back, with a reason)

While a month is "submitted" or "approved" nobody can change its files, fines or salaries.
"approved" is final: drivers see "Final" on their payslip. Corrections go into next month.
"""

from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..database import get_db
from ..deps import require_roles
from ..models import (
    ACCOUNTANT, FINANCE_MANAGER, Dispute, MonthEvent, PayrollMonth, Salary, User,
)
from ..payroll.engine import money, previous_period
from .months import get_month

router = APIRouter(prefix="/api/months/{month_id}", tags=["approval"])
can_view = require_roles(ACCOUNTANT, FINANCE_MANAGER)


class SubmitIn(BaseModel):
    note: str | None = Field(default=None, max_length=400)


class SendBackIn(BaseModel):
    reason: str = Field(min_length=5, max_length=400)


def _now() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)   # saved in UTC like the rest


def _iso(dt: datetime | None) -> str | None:
    return dt.isoformat() + "Z" if dt else None


def _totals(db: Session, month: PayrollMonth) -> dict:
    S = Salary
    row = db.execute(select(func.count(), func.sum(S.net), func.sum(S.deductions_applied))
                     .where(S.month_id == month.id)).one()
    by_method = dict(db.execute(select(S.payment_method, func.sum(S.net))
                                .where(S.month_id == month.id).group_by(S.payment_method)).all())
    return {"drivers": row[0] or 0, "net": money(row[1] or 0), "deductions": money(row[2] or 0),
            "cash_net": money(by_method.get("Cash") or 0), "bank_net": money(by_method.get("Bank") or 0)}


def checks(db: Session, month: PayrollMonth) -> list[dict]:
    """The checklist on the approval card. "blocking" checks must pass before sending / approving."""
    out = []
    calculated = month.status in ("calculated", "submitted", "approved")
    out.append({"key": "calculated", "ok": calculated, "blocking": True,
                "text": "Salaries are calculated" if calculated else "Calculate salaries first"})

    open_disputes = db.scalar(select(func.count()).where(Dispute.month_id == month.id,
                                                         Dispute.status == "open")) or 0
    out.append({"key": "disputes", "ok": open_disputes == 0, "blocking": True,
                "text": "No driver disputes waiting" if open_disputes == 0
                else f"{open_disputes} driver dispute(s) waiting for an answer"})

    prev = db.scalar(select(PayrollMonth).where(PayrollMonth.period == previous_period(month.period)))
    prev_ok = prev is None or prev.status == "approved"
    out.append({"key": "previous", "ok": prev_ok, "blocking": True, "approve_only": True,
                "text": ("Previous month is approved" if prev else "No earlier month in PayDesk") if prev_ok
                else f"Approve {prev.period} first (this month carries deductions from it)"})

    flags: dict[str, int] = {}
    explained = 0
    for s_flags, reason in db.execute(select(Salary.flags, Salary.ai_reason).where(Salary.month_id == month.id)):
        for f in s_flags:
            flags[f] = flags.get(f, 0) + 1
        if "unusual_change" in s_flags and reason:
            explained += 1
    unusual = flags.get("unusual_change", 0)
    if unusual:
        out.append({"key": "unusual", "ok": explained >= unusual, "blocking": False,
                    "text": f"{unusual} salaries changed more than 30% vs last month"
                            + (f" ({explained} explained by AI)" if explained else " - check them in the review")})
    if flags.get("capped"):
        out.append({"key": "capped", "ok": True, "blocking": False,
                    "text": f"{flags['capped']} drivers hit the 50% deduction limit (rest moves to next month)"})
    if flags.get("no_deliveries"):
        out.append({"key": "no_deliveries", "ok": False, "blocking": False,
                    "text": f"{flags['no_deliveries']} drivers have no deliveries this month"})
    return out


def _blockers(db: Session, month: PayrollMonth, for_approve: bool) -> list[str]:
    return [c["text"] for c in checks(db, month)
            if c["blocking"] and not c["ok"] and (for_approve or not c.get("approve_only"))]


def approval_out(db: Session, month: PayrollMonth) -> dict:
    events = db.scalars(select(MonthEvent).where(MonthEvent.month_id == month.id).order_by(MonthEvent.id)).all()
    return {
        "status": month.status,
        "submitted_by": month.submitted_by, "submitted_at": _iso(month.submitted_at),
        "approved_by": month.approved_by, "approved_at": _iso(month.approved_at),
        "returned_note": month.returned_note,
        "totals": _totals(db, month),
        "checks": checks(db, month),
        "events": [{"action": e.action, "by": e.by, "at": _iso(e.at), "note": e.note, "totals": e.totals}
                   for e in events],
    }


def _log(db: Session, month: PayrollMonth, action: str, user: User, note: str | None = None) -> None:
    db.add(MonthEvent(month_id=month.id, action=action, by=user.username, at=_now(), note=note,
                      totals=_totals(db, month)))


@router.get("/approval")
def approval(month_id: int, db: Session = Depends(get_db), _: User = Depends(can_view)):
    return approval_out(db, get_month(db, month_id))


@router.post("/submit")
def submit(month_id: int, body: SubmitIn, db: Session = Depends(get_db),
           user: User = Depends(require_roles(ACCOUNTANT))):
    month = get_month(db, month_id)
    if month.status != "calculated":
        raise HTTPException(status.HTTP_400_BAD_REQUEST,
                            "Only a calculated month can be sent for approval" if month.status not in
                            ("submitted", "approved") else "This month is already sent")
    blockers = _blockers(db, month, for_approve=False)
    if blockers:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Can't send yet: " + "; ".join(blockers))
    month.status = "submitted"
    month.submitted_by, month.submitted_at = user.username, _now()
    month.returned_note = None
    _log(db, month, "submitted", user, (body.note or "").strip() or None)
    db.commit()
    return approval_out(db, month)


@router.post("/approve")
def approve(month_id: int, db: Session = Depends(get_db), user: User = Depends(require_roles(FINANCE_MANAGER))):
    month = get_month(db, month_id)
    if month.status != "submitted":
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "The accountant must send this month for approval first")
    blockers = _blockers(db, month, for_approve=True)
    if blockers:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Can't approve yet: " + "; ".join(blockers))
    month.status = "approved"
    month.approved_by, month.approved_at = user.username, _now()
    _log(db, month, "approved", user)
    db.commit()
    return approval_out(db, month)


@router.post("/send-back")
def send_back(month_id: int, body: SendBackIn, db: Session = Depends(get_db),
              user: User = Depends(require_roles(FINANCE_MANAGER))):
    month = get_month(db, month_id)
    if month.status != "submitted":
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Only a month waiting for approval can be sent back")
    month.status = "calculated"          # the accountant can change it again
    month.returned_note = body.reason.strip()
    month.submitted_by = month.submitted_at = None
    _log(db, month, "sent_back", user, month.returned_note)
    db.commit()
    return approval_out(db, month)
