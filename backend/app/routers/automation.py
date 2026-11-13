"""Automation API - used by n8n, not by people.

No login here. Every call must send the secret header  X-PayDesk-Key: <AUTOMATION_KEY from .env>.
In n8n this is the "PayDesk key" credential (Header Auth).

Automation 1 (station emails) uses:
    GET  /api/automation/months/{id}/station-emails     the emails still to send (+ cash driver lists)
    GET  /api/automation/outbox/{email_id}/attachment   the station's Excel file
    POST /api/automation/outbox/{email_id}/result       "sent" or "failed" for one station
    POST /api/automation/months/{id}/run-finished       end of the run -> totals for the summary email
                                                        (+ starts automation 2: Telegram salary messages)

Automation 2 (Telegram) lives in telegram.py.
"""

import io
import secrets

import httpx
from fastapi import APIRouter, BackgroundTasks, Depends, Header, HTTPException, status
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.orm import Session, selectinload

from ..config import settings
from ..database import SessionLocal, get_db
from ..models import OutboxEmail, PayrollMonth, Salary, TelegramLink
from ..payroll.engine import money
from .distribution import WAITING, XLSX, _now, _status, month_name, run_seconds


def check_key(x_paydesk_key: str = Header(default="")) -> None:
    if not settings.automation_key:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE,
                            "AUTOMATION_KEY is not set in backend\\.env")
    if not secrets.compare_digest(x_paydesk_key, settings.automation_key):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Wrong or missing X-PayDesk-Key")


router = APIRouter(prefix="/api/automation", tags=["automation"], dependencies=[Depends(check_key)])


class ResultIn(BaseModel):
    status: str = Field(pattern="^(sent|failed)$")
    gmail_id: str | None = Field(default=None, max_length=80)
    note: str | None = None


def _month(db: Session, month_id: int) -> PayrollMonth:
    month = db.get(PayrollMonth, month_id)
    if month is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Month not found")
    if month.status != "approved":
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Only approved months are sent to stations")
    return month


def _send_to() -> str:
    if not settings.demo_inbox:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE,
                            "DEMO_INBOX is not set in backend\\.env - PayDesk never sends to real stations")
    return settings.demo_inbox


@router.get("/months/{month_id}/station-emails")
def station_emails(month_id: int, db: Session = Depends(get_db)):
    month = _month(db, month_id)
    send_to = _send_to()
    emails = db.scalars(select(OutboxEmail).where(OutboxEmail.month_id == month.id,
                                                   OutboxEmail.status.in_(WAITING))
                        .options(selectinload(OutboxEmail.station)).order_by(OutboxEmail.id)).all()
    cash = db.scalars(select(Salary).where(Salary.month_id == month.id, Salary.payment_method == "Cash")
                      .options(selectinload(Salary.driver)).order_by(Salary.driver_id)).all()
    cash_by_station: dict[int, list[dict]] = {}
    for s in cash:
        cash_by_station.setdefault(s.station_id, []).append(
            {"driver_id": s.driver_id, "name": s.driver.name, "net": s.net})

    return {
        "month_id": month.id, "period": month.period, "month_name": month_name(month.period),
        "send_to": send_to,           # demo: every email goes here, never to the station
        "count": len(emails),
        "stations": [{
            "email_id": e.id, "station_code": e.station.code, "station": e.station.name,
            "cashier_email": e.to_address, "send_to": send_to,
            "subject": e.subject, "drivers": e.drivers,
            "cash_drivers": e.cash_drivers, "cash_total": e.cash_total,
            "bank_drivers": e.bank_drivers, "bank_total": e.bank_total,
            "attachment_name": e.attachment_name,
            "cash_list": cash_by_station.get(e.station_id, []),
        } for e in emails],
    }


def _email(db: Session, email_id: int) -> OutboxEmail:
    e = db.get(OutboxEmail, email_id)
    if e is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Email not found")
    return e


@router.get("/outbox/{email_id}/attachment")
def attachment(email_id: int, db: Session = Depends(get_db)):
    e = _email(db, email_id)
    return StreamingResponse(io.BytesIO(e.attachment), media_type=XLSX,
                             headers={"Content-Disposition": f'attachment; filename="{e.attachment_name}"'})


@router.post("/outbox/{email_id}/result")
def result(email_id: int, body: ResultIn, db: Session = Depends(get_db)):
    e = _email(db, email_id)
    if _status(e) == "sent":                      # already sent - never mark it back
        return {"ok": True, "status": "sent"}
    e.status = body.status
    if body.status == "sent":
        e.delivered_to, e.delivered_at = settings.demo_inbox, _now()
        e.gmail_id, e.delivery_note = body.gmail_id, None
    else:
        e.delivery_note = (body.note or "Gmail could not send it")[:400]
    db.commit()
    return {"ok": True, "status": e.status}


def call_salary_messages(month_id: int) -> None:
    """Automation 2: after all station emails are sent, n8n messages every linked driver on Telegram."""
    with SessionLocal() as db:
        month = db.get(PayrollMonth, month_id)
        linked = db.scalar(select(func.count()).select_from(Salary)
                           .join(TelegramLink, TelegramLink.driver_id == Salary.driver_id)
                           .where(Salary.month_id == month_id)) or 0
    if month is None or not linked:
        return
    payload = {"source": "PayDesk", "event": "salary_messages", "month_id": month_id,
               "period": month.period, "month_name": month_name(month.period), "linked_drivers": linked}
    try:
        res = httpx.post(settings.n8n_salary_messages_url, json=payload, timeout=20)
        note = None if res.status_code < 400 else f"n8n answered with error {res.status_code}"
    except httpx.HTTPError:
        note = "Can't reach n8n"
    print(f"[automation 2] {month.period}: " + (note or f"salary messages started ({linked} linked drivers)"))


@router.post("/months/{month_id}/run-finished")
def run_finished(month_id: int, tasks: BackgroundTasks, db: Session = Depends(get_db)):
    month = _month(db, month_id)
    emails = db.scalars(select(OutboxEmail).where(OutboxEmail.month_id == month.id)).all()
    statuses = [_status(e) for e in emails]
    sent, failed = statuses.count("sent"), statuses.count("failed")
    waiting = statuses.count("prepared")
    month.emails_run_finished_at = _now()
    if failed or waiting:
        month.emails_run_status = "failed"
        month.emails_run_note = f"{failed} failed, {waiting} not sent - press \"Run again\" on the Outbox page"
    else:
        month.emails_run_status = "done"
        month.emails_run_note = None
    db.commit()
    print(f"[automation 1] {month.period}: finished - {sent} sent, {failed} failed, {run_seconds(month)} s")
    if month.emails_run_status == "done" and settings.n8n_salary_messages_url:
        tasks.add_task(call_salary_messages, month.id)
    return {
        "period": month.period, "month_name": month_name(month.period),
        "stations": len(emails), "sent": sent, "failed": failed, "waiting": waiting,
        "seconds": run_seconds(month), "status": month.emails_run_status,
        "cash_total": money(sum(e.cash_total for e in emails)),
        "bank_total": money(sum(e.bank_total for e in emails)),
        "notify_to": settings.demo_inbox,
        "outbox_url": f"{settings.frontend_origin}/months/{month.id}/outbox",
    }
