"""Automation 3 - "Did the driver get his cash?" (replaces the paper signature sheet).

People (PayDesk pages):
    GET  /api/payday                      cashier: his station's cash drivers · staff: all stations + problems
    POST /api/payday/{month_id}/paid      cashier marks drivers as paid  {driver_ids: [...]}

n8n (workflow 04, header X-PayDesk-Key):
    GET  /api/automation/cash/to-ask                  Telegram questions (and one reminder) to send
    POST /api/automation/cash/{id}/asked              {kind: ask|reminder, ok: true|false}
    GET  /api/automation/cash/alerts                  drivers who said "wrong amount" -> email the accountant
    POST /api/automation/cash/{id}/alerted
    GET  /api/automation/cash/summary                 evening summary for the accountant

The driver's ✅ / ❌ taps arrive through the chat bot (workflow 03 -> /api/automation/telegram/message).
"""

from __future__ import annotations

import re
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from ..config import settings
from ..database import get_db
from ..deps import require_roles
from ..models import ACCOUNTANT, CASHIER, FINANCE_MANAGER, CashPayment, PayrollMonth, Salary, TelegramLink, User
from .automation import check_key
from .distribution import month_name

router = APIRouter(prefix="/api/payday", tags=["payday"])
auto = APIRouter(prefix="/api/automation/cash", tags=["automation 3 - cash received"],
                 dependencies=[Depends(check_key)])
can_view = require_roles(ACCOUNTANT, FINANCE_MANAGER, CASHIER)
is_cashier = require_roles(CASHIER)


def _now() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


def _iso(dt: datetime | None) -> str | None:
    return dt.isoformat() + "Z" if dt else None


def _n(x: float) -> str:
    return f"{x:,.2f}".rstrip("0").rstrip(".")


def latest_approved(db: Session) -> PayrollMonth | None:
    return db.scalar(select(PayrollMonth).where(PayrollMonth.status == "approved")
                     .order_by(PayrollMonth.period.desc()))


def driver_status(p: CashPayment | None, linked: bool) -> str:
    """not_paid · waiting (asked, no answer) · confirmed · wrong · no_telegram (paid, can't ask)"""
    if p is None:
        return "not_paid"
    if p.answer:
        return p.answer
    return "waiting" if linked else "no_telegram"


# ------------------------------------------------------------------ pages

@router.get("")
def payday(month_id: int | None = None, db: Session = Depends(get_db), user: User = Depends(can_view)):
    month = db.get(PayrollMonth, month_id) if month_id else latest_approved(db)
    if month is None or month.status != "approved":
        return {"month": None}
    q = (select(Salary).where(Salary.month_id == month.id, Salary.payment_method == "Cash")
         .options(selectinload(Salary.driver), selectinload(Salary.station)).order_by(Salary.driver_id))
    if user.role == CASHIER:
        q = q.where(Salary.station_id == user.station_id)
    salaries = db.scalars(q).all()
    pays = {p.driver_id: p for p in db.scalars(select(CashPayment).where(CashPayment.month_id == month.id))}
    linked = set(db.scalars(select(TelegramLink.driver_id)))
    rows = []
    for s in salaries:
        p = pays.get(s.driver_id)
        rows.append({
            "driver_id": s.driver_id, "name": s.driver.name, "station_code": s.station.code,
            "station": s.station.name, "net": s.net, "telegram": s.driver_id in linked,
            "status": driver_status(p, s.driver_id in linked),
            "paid_at": _iso(p.paid_at) if p else None, "paid_by": p.paid_by if p else None,
            "answered_at": _iso(p.answered_at) if p else None,
            "said_amount": p.said_amount if p else None, "note": p.note if p else None,
        })
    out = {"month": {"id": month.id, "period": month.period, "month_name": month_name(month.period)},
           "totals": _totals(rows)}
    if user.role == CASHIER:
        out["drivers"] = rows
    else:
        out["stations"] = _by_station(rows)
        out["problems"] = [r for r in rows if r["status"] == "wrong"]
    return out


def _totals(rows: list[dict]) -> dict:
    count = lambda st: sum(1 for r in rows if r["status"] == st)  # noqa: E731
    return {
        "drivers": len(rows), "cash": round(sum(r["net"] for r in rows), 2),
        "paid": sum(1 for r in rows if r["status"] != "not_paid"),
        "paid_amount": round(sum(r["net"] for r in rows if r["status"] != "not_paid"), 2),
        "confirmed": count("confirmed"), "wrong": count("wrong"), "waiting": count("waiting"),
        "no_telegram": count("no_telegram"), "not_paid": count("not_paid"),
    }


def _by_station(rows: list[dict]) -> list[dict]:
    groups: dict[str, list[dict]] = {}
    for r in rows:
        groups.setdefault(r["station_code"], []).append(r)
    out = []
    for code, rs in sorted(groups.items()):
        t = _totals(rs)
        state = "all_paid" if t["not_paid"] == 0 else ("not_started" if t["paid"] == 0 else "partly_paid")
        out.append({"station_code": code, "station": rs[0]["station"], "state": state, **t})
    return out


class PaidIn(BaseModel):
    driver_ids: list[str] = Field(min_length=1, max_length=200)


@router.post("/{month_id}/paid")
def mark_paid(month_id: int, body: PaidIn, db: Session = Depends(get_db), user: User = Depends(is_cashier)):
    month = db.get(PayrollMonth, month_id)
    if month is None or month.status != "approved":
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Only approved months can be paid")
    # Only HIS station's cash drivers of this month
    salaries = db.scalars(select(Salary).where(
        Salary.month_id == month.id, Salary.station_id == user.station_id, Salary.payment_method == "Cash",
        Salary.driver_id.in_([d.strip().upper() for d in body.driver_ids]))).all()
    if not salaries:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "None of these are cash drivers of your station")
    done = set(db.scalars(select(CashPayment.driver_id).where(CashPayment.month_id == month.id)))
    now, added = _now(), 0
    for s in salaries:
        if s.driver_id in done:          # paid once - can't be paid twice
            continue
        db.add(CashPayment(month_id=month.id, driver_id=s.driver_id, station_id=s.station_id,
                           amount=s.net, paid_by=user.username, paid_at=now))
        added += 1
    db.commit()
    if added:
        print(f"[automation 3] {user.username} marked {added} driver(s) paid for {month.period}")
    return {"marked": added}


# ------------------------------------------------------------------ Telegram texts

def ask_text(p: CashPayment, reminder: bool) -> str:
    m = month_name(p.month.period)
    head = "⏰ Reminder / تذكير\n\n" if reminder else ""
    return (f"{head}💵 Salary paid – {m}\n"
            f"Your cashier at {p.station.name} marked you PAID: SAR {_n(p.amount)}.\n"
            f"Did you receive exactly this amount?\n\n"
            f"💵 تم صرف الراتب – {m}\n"
            f"أمين الصندوق في {p.station.name} سجّل أنك استلمت: {_n(p.amount)} ريال.\n"
            f"هل استلمت هذا المبلغ بالضبط؟")


def ask_buttons(p: CashPayment) -> dict:
    return {"inline_keyboard": [
        [{"text": "✅ Yes, received / نعم استلمت", "callback_data": f"cy:{p.id}"}],
        [{"text": "❌ No / wrong amount / لا", "callback_data": f"cn:{p.id}"}],
    ]}


ARABIC_DIGITS = str.maketrans("٠١٢٣٤٥٦٧٨٩٫", "0123456789.")


def first_amount(text: str) -> float | None:
    m = re.search(r"\d[\d,]*(?:\.\d+)?", text.translate(ARABIC_DIGITS))
    if not m:
        return None
    try:
        return float(m.group().replace(",", ""))
    except ValueError:
        return None


def own_payment(db: Session, driver_id: str, payment_id: int) -> CashPayment | None:
    p = db.get(CashPayment, payment_id)
    return p if p is not None and p.driver_id == driver_id else None   # only HIS payment


def confirm(db: Session, p: CashPayment) -> str:
    if p.answer:
        return "You already answered this one. Thank you!\n\nلقد أجبت على هذا من قبل. شكراً!"
    p.answer, p.answered_at = "confirmed", _now()
    db.commit()
    print(f"[automation 3] driver {p.driver_id} confirmed SAR {p.amount} received")
    return (f"✅ Thank you! Saved: you received SAR {_n(p.amount)} for {month_name(p.month.period)}.\n"
            f"No paper signature needed.\n\n"
            f"✅ شكراً! تم الحفظ: استلمت {_n(p.amount)} ريال. لا حاجة لتوقيع ورقي.")


def report_wrong(db: Session, p: CashPayment, text: str) -> str:
    if p.answer:
        return "You already answered this one. Thank you!\n\nلقد أجبت على هذا من قبل. شكراً!"
    p.answer, p.answered_at = "wrong", _now()
    p.said_amount, p.note = first_amount(text), " ".join(text.split())[:300]
    db.commit()
    print(f"[automation 3] driver {p.driver_id} says the cash amount is wrong ({p.said_amount})")
    return ("⚠️ Sent to the payroll team. They will check with your station and answer you here.\n\n"
            "⚠️ تم الإرسال إلى فريق الرواتب. سيتحققون مع محطتك ويردون عليك هنا.")


ASK_HOW_MUCH = ("How much did you receive? Write the amount and a short note.\n"
                "Example: 1000 – cashier said the rest next week\nSend /cancel to stop.\n\n"
                "كم استلمت؟ اكتب المبلغ وملاحظة قصيرة.\n"
                "مثال: 1000 – قال أمين الصندوق الباقي الأسبوع القادم")


# ------------------------------------------------------------------ n8n (workflow 04)

@auto.get("/to-ask")
def to_ask(db: Session = Depends(get_db)):
    """Questions for drivers who were just paid, and ONE reminder after CASH_REMINDER_HOURS."""
    rows = db.execute(
        select(CashPayment, TelegramLink).join(TelegramLink, TelegramLink.driver_id == CashPayment.driver_id)
        .options(selectinload(CashPayment.month), selectinload(CashPayment.station))
        .where(CashPayment.answer.is_(None), CashPayment.reminded_at.is_(None))
        .order_by(CashPayment.id)
    ).all()
    late = _now() - timedelta(hours=settings.cash_reminder_hours)
    out = []
    for p, link in rows:
        kind = "ask" if p.asked_at is None else ("reminder" if p.asked_at <= late else None)
        if kind:
            out.append({"payment_id": p.id, "driver_id": p.driver_id, "kind": kind,
                        "telegram": {"chat_id": link.chat_id, "text": ask_text(p, kind == "reminder"),
                                     "reply_markup": ask_buttons(p)}})
    return {"count": len(out[:100]), "messages": out[:100]}


class AskedIn(BaseModel):
    kind: str = Field(pattern="^(ask|reminder)$")
    ok: bool = True


@auto.post("/{payment_id}/asked")
def asked(payment_id: int, body: AskedIn, db: Session = Depends(get_db)):
    p = db.get(CashPayment, payment_id)
    if p is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Payment not found")
    if body.ok:
        if body.kind == "ask" and p.asked_at is None:
            p.asked_at = _now()
        elif body.kind == "reminder":
            p.reminded_at = _now()
        db.commit()
    return {"ok": True}


@auto.get("/alerts")
def alerts(db: Session = Depends(get_db)):
    rows = db.scalars(select(CashPayment).where(CashPayment.answer == "wrong", CashPayment.alerted_at.is_(None))
                      .options(selectinload(CashPayment.driver), selectinload(CashPayment.station),
                               selectinload(CashPayment.month)).order_by(CashPayment.id)).all()
    return {"count": len(rows), "notify_to": settings.demo_inbox, "alerts": [{
        "payment_id": p.id, "month_name": month_name(p.month.period), "driver_id": p.driver_id,
        "driver_name": p.driver.name, "station_code": p.station.code, "station": p.station.name,
        "amount": p.amount, "said_amount": p.said_amount, "note": p.note, "paid_by": p.paid_by,
        "difference": round(p.amount - p.said_amount, 2) if p.said_amount is not None else None,
    } for p in rows]}


@auto.post("/{payment_id}/alerted")
def alerted(payment_id: int, db: Session = Depends(get_db)):
    p = db.get(CashPayment, payment_id)
    if p is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Payment not found")
    p.alerted_at = p.alerted_at or _now()
    db.commit()
    return {"ok": True}


@auto.get("/summary")
def summary(db: Session = Depends(get_db)):
    """Evening email: how far is payday? Uses the latest approved month."""
    month = latest_approved(db)
    if month is None:
        return {"month": None, "notify_to": settings.demo_inbox}
    staff = db.scalar(select(User).where(User.role == ACCOUNTANT))
    data = payday(month.id, db, staff)
    st = data["stations"]
    return {
        "month": data["month"], "notify_to": settings.demo_inbox, "totals": data["totals"],
        "stations": len(st),
        "stations_all_paid": sum(1 for s in st if s["state"] == "all_paid"),
        "stations_partly_paid": [s for s in st if s["state"] == "partly_paid"],
        "stations_not_started": [s for s in st if s["state"] == "not_started"],
        "problems": data["problems"],
        "payday_url": f"{settings.frontend_origin}/payday",
    }
