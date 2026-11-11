"""Stage 8: the driver's own pages. A driver only ever gets HIS OWN data from here."""

import time
from collections import defaultdict, deque

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..ai.gemini import AIError, is_enabled
from ..ai.payslip_chat import MAX_QUESTION, answer_question, explain_in_words
from ..database import get_db
from ..deps import require_roles
from ..models import DRIVER, PayrollMonth, Salary, User
from .salaries import FINAL_STATUSES, build_payslip

router = APIRouter(prefix="/api/me", tags=["driver"])
is_driver = require_roles(DRIVER)

# A driver sees a month once salaries are calculated. Before approval it is marked "not final".
VISIBLE_STATUSES = ("calculated",) + FINAL_STATUSES

QUESTIONS_PER_HOUR = 20                       # keeps the free Gemini limit safe
_asked: dict[int, deque] = defaultdict(deque)


class ChatTurn(BaseModel):
    role: str
    text: str = Field(max_length=2000)


class Question(BaseModel):
    question: str = Field(min_length=1, max_length=MAX_QUESTION)
    history: list[ChatTurn] = Field(default_factory=list, max_length=20)


def _own_salary(db: Session, user: User, month_id: int) -> tuple[PayrollMonth, Salary]:
    month = db.get(PayrollMonth, month_id)
    salary = None
    if month is not None and month.status in VISIBLE_STATUSES:
        salary = db.scalar(select(Salary).where(Salary.month_id == month.id, Salary.driver_id == user.driver_id))
    if salary is None:
        # Same answer for "not your month" and "does not exist" - nothing to guess from
        raise HTTPException(status.HTTP_404_NOT_FOUND, "No payslip for this month yet")
    return month, salary


@router.get("/payslips")
def my_payslips(db: Session = Depends(get_db), user: User = Depends(is_driver)):
    rows = db.execute(
        select(PayrollMonth, Salary)
        .join(Salary, Salary.month_id == PayrollMonth.id)
        .where(Salary.driver_id == user.driver_id, PayrollMonth.status.in_(VISIBLE_STATUSES))
        .order_by(PayrollMonth.period.desc())
    ).all()
    d = user.driver
    return {
        "driver": {
            "id": d.id, "name": d.name, "station": d.station.name, "joining_date": d.joining_date.isoformat(),
            "payment_method": d.payment_method, "iban_last4": d.iban[-4:] if d.iban else None,
        },
        "months": [{
            "month_id": m.id, "period": m.period, "final": m.status in FINAL_STATUSES,
            "net": s.net, "gross": s.gross, "deductions": s.deductions_applied, "carried_forward": s.carried_forward,
            "days_worked": s.days_worked, "deliveries": s.prepaid_count + s.cod_count,
        } for m, s in rows],
        "ai_enabled": is_enabled(),
    }


@router.get("/payslips/{month_id}")
def my_payslip(month_id: int, db: Session = Depends(get_db), user: User = Depends(is_driver)):
    month, salary = _own_salary(db, user, month_id)
    data = build_payslip(db, month, salary)
    data["in_words"] = explain_in_words(data)
    data["ai_enabled"] = is_enabled()
    return data


@router.post("/payslips/{month_id}/ask")
def ask_about_payslip(month_id: int, body: Question, db: Session = Depends(get_db),
                      user: User = Depends(is_driver)):
    # Plain "def": FastAPI runs it in a thread, so a slow AI answer never blocks other users.
    month, salary = _own_salary(db, user, month_id)

    now = time.monotonic()
    asked = _asked[user.id]
    while asked and now - asked[0] > 3600:
        asked.popleft()
    if len(asked) >= QUESTIONS_PER_HOUR:
        raise HTTPException(status.HTTP_429_TOO_MANY_REQUESTS,
                            f"You can ask {QUESTIONS_PER_HOUR} questions an hour. Please try again later.")

    data = build_payslip(db, month, salary)
    try:
        answer = answer_question(data, body.question, [t.model_dump() for t in body.history])
    except AIError as e:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(e))
    asked.append(now)
    return {"answer": answer}
