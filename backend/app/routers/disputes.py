"""Stage 9: the accountant's dispute inbox. The finance manager can read it."""

from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.orm import Session, selectinload

from ..ai.disputes import draft_reply
from ..ai.gemini import AIError, is_enabled
from ..database import get_db
from ..deps import require_roles
from ..models import ACCOUNTANT, FINANCE_MANAGER, Adjustment, Dispute, PayrollMonth, Salary, User
from ..payroll.engine import clear_salaries
from .salaries import build_payslip

router = APIRouter(prefix="/api/disputes", tags=["disputes"])
can_view = require_roles(ACCOUNTANT, FINANCE_MANAGER)
can_answer = require_roles(ACCOUNTANT)

EDITABLE = ("ready", "calculated")      # sent-for-approval / approved months can't be changed


class DraftIn(BaseModel):
    decision: str = Field(pattern="^(accepted|rejected)$")


class AnswerIn(BaseModel):
    decision: str = Field(pattern="^(accepted|rejected)$")
    reply: str = Field(min_length=5, max_length=1000)
    remove_deduction: bool = False


def utc_iso(dt: datetime | None) -> str | None:
    """Times are saved in UTC. The "Z" tells the browser, so it shows Riyadh time."""
    return dt.isoformat() + "Z" if dt else None


def dispute_out(d: Dispute, with_driver: bool = True) -> dict:
    data = {
        "id": d.id, "month_id": d.month_id, "period": d.month.period, "topic": d.topic, "line_key": d.line_key,
        "line": None if d.topic != "deduction" else {
            "type": d.line_type, "amount": d.line_amount, "day": d.line_day.isoformat() if d.line_day else None,
            "reference": d.line_reference, "note": d.line_note, "carried_from": d.line_carried_from,
        },
        "message": d.message, "status": d.status, "reply": d.reply,
        "deduction_removed": d.deduction_removed,
        "created_at": utc_iso(d.created_at),
        "answered_at": utc_iso(d.answered_at),
    }
    if with_driver:
        data.update({
            "driver_id": d.driver_id, "driver_name": d.driver.name, "station": d.station.name,
            "station_code": d.station.code, "answered_by": d.answered_by, "ai_draft": d.ai_draft,
        })
    return data


def matching_adjustment(db: Session, d: Dispute) -> Adjustment | None:
    """The deduction in this month's files that the disputed line came from (not for carried lines)."""
    if d.topic != "deduction" or d.line_carried_from:
        return None
    q = select(Adjustment).where(
        Adjustment.month_id == d.month_id, Adjustment.driver_id == d.driver_id, Adjustment.kind == "Deduction",
        Adjustment.type == d.line_type, Adjustment.amount == d.line_amount,
    )
    q = q.where(Adjustment.day == d.line_day) if d.line_day else q.where(Adjustment.day.is_(None))
    q = (q.where(Adjustment.reference == d.line_reference) if d.line_reference
         else q.where(Adjustment.reference.is_(None)))
    return db.scalars(q.order_by(Adjustment.id)).first()


def _get(db: Session, dispute_id: int) -> Dispute:
    d = db.get(Dispute, dispute_id)
    if d is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Dispute not found")
    return d


@router.get("")
def list_disputes(state: str = "open", month_id: int | None = None,
                  db: Session = Depends(get_db), _: User = Depends(can_view)):
    q = (select(Dispute).options(selectinload(Dispute.driver), selectinload(Dispute.station),
                                 selectinload(Dispute.month)))
    if state == "open":
        q = q.where(Dispute.status == "open").order_by(Dispute.created_at, Dispute.id)
    elif state == "answered":
        q = q.where(Dispute.status != "open").order_by(Dispute.answered_at.desc(), Dispute.id.desc())
    else:
        q = q.order_by(Dispute.id.desc())
    if month_id:
        q = q.where(Dispute.month_id == month_id)
    rows = db.scalars(q.limit(500)).all()
    counts = dict(db.execute(select(Dispute.status, func.count()).group_by(Dispute.status)).all())
    return {
        "items": [dispute_out(d) | {"can_remove": matching_adjustment(db, d) is not None
                                     and d.month.status in EDITABLE and d.status == "open"} for d in rows],
        "counts": {"open": counts.get("open", 0), "accepted": counts.get("accepted", 0),
                   "rejected": counts.get("rejected", 0)},
        "ai_enabled": is_enabled(),
    }


@router.get("/count")
def open_count(db: Session = Depends(get_db), _: User = Depends(can_view)):
    return {"open": db.scalar(select(func.count()).where(Dispute.status == "open")) or 0}


@router.post("/{dispute_id}/draft")
def ai_draft(dispute_id: int, body: DraftIn, db: Session = Depends(get_db), _: User = Depends(can_answer)):
    d = _get(db, dispute_id)
    salary = db.scalar(select(Salary).where(Salary.month_id == d.month_id, Salary.driver_id == d.driver_id))
    payslip = build_payslip(db, d.month, salary) if salary else None
    try:
        text = draft_reply(d, payslip, body.decision)
    except AIError as e:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(e))
    d.ai_draft = text
    db.commit()
    return {"draft": text}


@router.post("/{dispute_id}/answer")
def answer(dispute_id: int, body: AnswerIn, db: Session = Depends(get_db), user: User = Depends(can_answer)):
    d = _get(db, dispute_id)
    if d.status != "open":
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "This dispute is already answered")
    month: PayrollMonth = d.month
    note = None
    if body.remove_deduction:
        if body.decision != "accepted":
            raise HTTPException(status.HTTP_400_BAD_REQUEST, "Only remove a deduction when you agree with the driver")
        if month.status not in EDITABLE:
            raise HTTPException(status.HTTP_400_BAD_REQUEST,
                                "This month is sent for approval or approved - correct it in next month's adjustments file")
        adj = matching_adjustment(db, d)
        if adj is None:
            raise HTTPException(status.HTTP_400_BAD_REQUEST,
                                "Can't find this deduction in this month's files (carried from an earlier month?). "
                                "Correct it in the adjustments file instead")
        db.delete(adj)
        clear_salaries(db, month.id)     # deductions changed -> salaries must be recalculated
        month.status = "ready"
        d.deduction_removed = True
        note = ("Deduction removed. Click \"Calculate salaries\" for this month again. "
                "If you upload the deductions file again, delete this line from the file too.")
    d.status = body.decision
    d.reply = body.reply.strip()
    d.answered_at = datetime.now(timezone.utc).replace(tzinfo=None)
    d.answered_by = user.username
    db.commit()
    db.refresh(d)
    return {"dispute": dispute_out(d), "note": note}
