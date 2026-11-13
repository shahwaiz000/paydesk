"""Automation 2 - "Why was my salary cut?" on Telegram. Used by n8n, not by people.

Every call needs the header  X-PayDesk-Key  (same "PayDesk key" credential as automation 1).

n8n workflow 03 (chat bot) - checks Telegram every few seconds:
    GET  /api/automation/telegram/bot               Telegram API address (with the token from .env) + offset
    GET  /api/automation/telegram/offset            the last Telegram update n8n already handled
    PUT  /api/automation/telegram/offset            save it after a batch
    POST /api/automation/telegram/message           one message / button tap -> what to answer
         action "reply"  = send `telegram` as it is
         action "ask_ai" = Gemini answers `question` from `facts` (his payslip only), then send
    GET  /api/automation/telegram/answers           accountant answers not yet sent on Telegram
    POST /api/automation/telegram/answers/{id}/delivered

n8n workflow 02 (salary messages) - PayDesk calls it when the station emails are done:
    GET  /api/automation/months/{id}/telegram-salary-messages
    POST /api/automation/months/{id}/telegram-salary-messages/{driver_id}/result

Safety:
  * A chat sees nothing until the driver links it with his driver ID + PIN (5 wrong tries an hour).
  * After that it only ever gets HIS OWN payslip. No name, Iqama, IBAN or phone goes to the AI.
  * The bot never changes money. "This is wrong" only opens a dispute for the accountant.
"""

from __future__ import annotations

import re
import time
from collections import defaultdict, deque
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from ..config import settings
from ..ai.payslip_chat import MAX_QUESTION, _facts, explain_in_words
from ..database import get_db
from ..models import (
    DRIVER, AutomationState, Dispute, PayrollMonth, Salary, TelegramLink, TelegramNotice, User,
)
from ..security import verify_password
from .automation import check_key
from .distribution import month_name
from .me import VISIBLE_STATUSES, open_dispute
from .salaries import FINAL_STATUSES, build_payslip

router = APIRouter(prefix="/api/automation", tags=["automation 2 - telegram"], dependencies=[Depends(check_key)])

QUESTIONS_PER_HOUR = 20          # per driver - keeps the free Gemini limit safe
LINK_TRIES_PER_HOUR = 5          # wrong driver ID / PIN tries per chat
_asked: dict[str, deque] = defaultdict(deque)
_bad_links: dict[str, deque] = defaultdict(deque)

ARABIC = re.compile(r"[؀-ۿ]")


def _now() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


def _n(x: float) -> str:
    return f"{x:,.2f}".rstrip("0").rstrip(".")


def _limited(store: dict[str, deque], key: str, limit: int) -> bool:
    """True when `key` already used `limit` tries in the last hour."""
    now, q = time.monotonic(), store[key]
    while q and now - q[0] > 3600:
        q.popleft()
    return len(q) >= limit


# ------------------------------------------------------------------ bot texts (English + Arabic)

T = {
    "welcome": (
        "👋 Welcome to PayDesk.\n"
        "I explain your salary and answer questions like \"why was 300 cut?\".\n\n"
        "First link your account (once):\n/link YOUR_DRIVER_ID YOUR_PIN\nExample: /link D10001 1234\n\n"
        "👋 أهلاً بك في PayDesk.\n"
        "أشرح لك راتبك وأجيب عن أسئلتك مثل \"ليش انخصم 300؟\".\n\n"
        "أولاً اربط حسابك (مرة واحدة):\n/link رقم_السائق الرقم_السري\nمثال: /link D10001 1234"
    ),
    "link_format": (
        "Please send: /link YOUR_DRIVER_ID YOUR_PIN\nExample: /link D10001 1234\n\n"
        "أرسل: /link رقم_السائق الرقم_السري\nمثال: /link D10001 1234"
    ),
    "link_wrong": (
        "❌ Driver ID or PIN is wrong. Please try again.\n\n"
        "❌ رقم السائق أو الرقم السري غير صحيح. حاول مرة أخرى."
    ),
    "link_blocked": (
        "⛔ Too many wrong tries. Please try again in one hour.\n\n"
        "⛔ محاولات خاطئة كثيرة. حاول بعد ساعة."
    ),
    "linked": (
        "✅ Linked to driver {driver_id}. I deleted your PIN message for safety.\n"
        "Send /salary to see your salary, or just ask me a question.\n\n"
        "✅ تم الربط بالسائق {driver_id}. حذفت رسالة الرقم السري للأمان.\n"
        "أرسل /salary لعرض راتبك، أو اسألني أي سؤال."
    ),
    "not_linked": (
        "🔒 This chat is not linked yet.\nSend: /link YOUR_DRIVER_ID YOUR_PIN\n\n"
        "🔒 هذه المحادثة غير مربوطة بعد.\nأرسل: /link رقم_السائق الرقم_السري"
    ),
    "unlinked": (
        "👋 This chat is no longer linked. Send /link to link again.\n\n"
        "👋 تم إلغاء الربط. أرسل /link للربط مرة أخرى."
    ),
    "no_salary": (
        "There is no salary for you yet. You will get a message here when it is ready.\n\n"
        "لا يوجد راتب لك بعد. ستصلك رسالة هنا عندما يكون جاهزاً."
    ),
    "help": (
        "What I can do:\n/salary – your latest salary\n/wrong – report a wrong deduction\n"
        "/unlink – stop using this chat\nOr just ask: \"why was my salary cut?\"\n\n"
        "ماذا أستطيع:\n/salary – آخر راتب لك\n/wrong – بلّغ عن خصم خاطئ\n"
        "/unlink – إيقاف هذه المحادثة\nأو اسأل مباشرة: \"ليش انخصم من راتبي؟\""
    ),
    "too_many_questions": (
        f"You can ask {QUESTIONS_PER_HOUR} questions an hour. Please try again later.\n\n"
        f"يمكنك أن تسأل {QUESTIONS_PER_HOUR} سؤالاً في الساعة. حاول لاحقاً."
    ),
    "ask_reason": (
        "✍️ Please write in ONE message why this is wrong.\nSend /cancel to stop.\n\n"
        "✍️ اكتب في رسالة واحدة لماذا هذا خطأ.\nأرسل /cancel للإلغاء."
    ),
    "cancelled": "OK, cancelled.\n\nتم الإلغاء.",
    "reported": (
        "📨 Sent to the payroll team (report #{id}). You will get the answer here.\n\n"
        "📨 تم الإرسال إلى فريق الرواتب (بلاغ رقم {id}). سيصلك الرد هنا."
    ),
    "no_deductions": (
        "Nothing was deducted from this salary. If something else is wrong, tap the button below.\n\n"
        "لم يُخصم شيء من هذا الراتب. إذا كان هناك خطأ آخر اضغط الزر بالأسفل."
    ),
    "pick_deduction": (
        "Which deduction is wrong? Tap it below.\n\n"
        "أي خصم خاطئ؟ اضغط عليه بالأسفل."
    ),
    "button_gone": (
        "This button is old – the salary has changed. Send /salary again.\n\n"
        "هذا الزر قديم – تغيّر الراتب. أرسل /salary مرة أخرى."
    ),
}


# ------------------------------------------------------------------ helpers

def _link(db: Session, chat_id: str) -> TelegramLink | None:
    return db.scalar(select(TelegramLink).where(TelegramLink.chat_id == chat_id))


def latest_salary(db: Session, driver_id: str) -> tuple[PayrollMonth, Salary] | None:
    row = db.execute(
        select(PayrollMonth, Salary).join(Salary, Salary.month_id == PayrollMonth.id)
        .where(Salary.driver_id == driver_id, PayrollMonth.status.in_(VISIBLE_STATUSES))
        .order_by(PayrollMonth.period.desc())
    ).first()
    return (row[0], row[1]) if row else None


def _own_month(db: Session, driver_id: str, month_id: int) -> tuple[PayrollMonth, Salary] | None:
    month = db.get(PayrollMonth, month_id)
    if month is None or month.status not in VISIBLE_STATUSES:
        return None
    salary = db.scalar(select(Salary).where(Salary.month_id == month.id, Salary.driver_id == driver_id))
    return (month, salary) if salary else None


def deductions(p: dict) -> list[dict]:
    return [l for l in p["lines"] if l["kind"] == "Deduction"]


def _short_day(iso: str | None) -> str:
    return "" if not iso else f"{int(iso[8:10])}/{int(iso[5:7])}"


def wrong_buttons(p: dict) -> dict:
    """Inline buttons under a salary message: one "This is wrong" per deduction + "other problem"."""
    rows = [[{"text": f"❌ Wrong: {l['type']} {_n(l['amount_due'])}", "callback_data": f"w:{p['month_id']}:{i}"}]
            for i, l in enumerate(deductions(p))][:8]
    rows.append([{"text": "⚠️ Other problem / مشكلة أخرى", "callback_data": f"o:{p['month_id']}"}])
    return {"inline_keyboard": rows}


def salary_message(p: dict) -> str:
    """The salary explained in simple English. n8n asks Gemini for the Arabic under it."""
    r = p["rates"]
    out = [f"💰 PayDesk – your salary for {month_name(p['period'])}"]
    if not p["final"]:
        out.append("(not final yet – it can still change)")
    out += ["", f"Net salary: SAR {_n(p['net'])}", "", f"How you earned SAR {_n(p['gross'])}:"]
    if p["full_month"]:
        out.append(f"• Fixed salary: SAR {_n(p['fixed_pay'])} (full month)")
    else:
        out.append(f"• Fixed salary: SAR {_n(p['fixed_pay'])} for {p['days_worked']} days "
                   f"({_n(r['fixed_salary'])} ÷ {r['proration_days']} × {p['days_worked']})")
    out.append(f"• {p['prepaid_count']} prepaid × {_n(r['prepaid_rate'])} = SAR {_n(p['prepaid_pay'])}")
    out.append(f"• {p['cod_count']} COD × {_n(r['cod_rate'])} = SAR {_n(p['cod_pay'])}")
    if p["bonuses"]:
        out.append(f"• Bonuses: SAR {_n(p['bonuses'])}")

    lines = deductions(p)
    out.append("")
    if not lines:
        out.append("Nothing was deducted. ✅")
    else:
        out.append(f"Deducted: SAR {_n(p['deductions_applied'])}")
        for l in lines:
            why = ", ".join(x for x in [l["reference"], _short_day(l["day"]), l["note"],
                                         f"from {month_name(l['carried_from'])}" if l["carried_from"] else None] if x)
            taken = f"SAR {_n(l['amount_applied'])}"
            if l["carried"] > 0:
                taken += f" now, SAR {_n(l['carried'])} next month"
            out.append(f"• {l['type']}: {taken}" + (f" – {why}" if why else ""))
    if p["carried_forward"] > 0:
        out.append(f"By law at most {_n(r['deduction_cap_pct'])}% of your earnings can be deducted in one month, "
                   f"so SAR {_n(p['carried_forward'])} moves to next month.")
    out += ["", "Paid by bank transfer." if p["payment_method"] == "Bank" else "Paid in cash by your station cashier.",
            "", "Ask me anything about it, for example \"why was 300 cut?\". "
                "If a deduction is wrong, tap the button below."]
    return "\n".join(out)


def _reply(chat_id: str, text: str, buttons: dict | None = None, delete_message_id: int | None = None) -> dict:
    tg = {"chat_id": chat_id, "text": text[:4000]}
    if buttons:
        tg["reply_markup"] = buttons
    return {"action": "reply", "telegram": tg, "delete_message_id": delete_message_id}


# ------------------------------------------------------------------ the chat bot (workflow 03)

class MessageIn(BaseModel):
    chat_id: str = Field(min_length=1, max_length=30)
    text: str | None = Field(default=None, max_length=2000)
    callback_data: str | None = Field(default=None, max_length=64)   # a button was tapped
    message_id: int | None = None                                    # to delete the /link message (PIN)


@router.get("/telegram/offset")
def get_offset(db: Session = Depends(get_db)):
    row = db.get(AutomationState, "telegram_offset")
    return {"offset": int(row.value) if row else 0}


@router.get("/telegram/bot")
def bot_info(db: Session = Depends(get_db)):
    """n8n reads the bot token from PayDesk, so it never sits in a workflow file or on GitHub."""
    if not settings.telegram_bot_token:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, "TELEGRAM_BOT_TOKEN is not set in backend\\.env")
    return {"api": f"https://api.telegram.org/bot{settings.telegram_bot_token}", **get_offset(db)}


class OffsetIn(BaseModel):
    offset: int = Field(ge=0)


@router.put("/telegram/offset")
def save_offset(body: OffsetIn, db: Session = Depends(get_db)):
    row = db.get(AutomationState, "telegram_offset")
    if row is None:
        db.add(AutomationState(key="telegram_offset", value=str(body.offset)))
    elif body.offset > int(row.value):          # never go back - no message is handled twice
        row.value = str(body.offset)
    db.commit()
    return get_offset(db)


def _do_link(db: Session, chat_id: str, text: str, message_id: int | None) -> dict:
    parts = text.split()
    if len(parts) != 3:
        return _reply(chat_id, T["link_format"])
    if _limited(_bad_links, chat_id, LINK_TRIES_PER_HOUR):
        return _reply(chat_id, T["link_blocked"], delete_message_id=message_id)
    driver_id, pin = parts[1].upper(), parts[2]
    user = db.scalar(select(User).where(User.role == DRIVER, User.driver_id == driver_id, User.is_active.is_(True)))
    if user is None or not verify_password(pin, user.password_hash):
        _bad_links[chat_id].append(time.monotonic())
        return _reply(chat_id, T["link_wrong"], delete_message_id=message_id)
    # One chat per driver and one driver per chat - a new link replaces the old one
    for old in db.scalars(select(TelegramLink).where((TelegramLink.chat_id == chat_id)
                                                      | (TelegramLink.driver_id == driver_id))).all():
        db.delete(old)
    db.flush()
    db.add(TelegramLink(chat_id=chat_id, driver_id=driver_id, linked_at=_now()))
    db.commit()
    print(f"[automation 2] chat linked to driver {driver_id}")
    return _reply(chat_id, T["linked"].format(driver_id=driver_id), delete_message_id=message_id)


def _salary_reply(db: Session, link: TelegramLink) -> dict:
    found = latest_salary(db, link.driver_id)
    if not found:
        return _reply(link.chat_id, T["no_salary"])
    p = build_payslip(db, *found)
    return _reply(link.chat_id, salary_message(p), wrong_buttons(p))


def _wrong_menu(db: Session, link: TelegramLink) -> dict:
    found = latest_salary(db, link.driver_id)
    if not found:
        return _reply(link.chat_id, T["no_salary"])
    p = build_payslip(db, *found)
    return _reply(link.chat_id, T["pick_deduction"] if deductions(p) else T["no_deductions"], wrong_buttons(p))


def _button(db: Session, link: TelegramLink, data: str) -> dict:
    """w:<month_id>:<n> = deduction n is wrong · o:<month_id> = other problem
    cy:<payment_id> = "yes, I received my cash" · cn:<payment_id> = "no / wrong amount" (automation 3)."""
    parts = data.split(":")
    if parts[0] in ("cy", "cn"):
        from .payday import ASK_HOW_MUCH, confirm, own_payment
        try:
            pay = own_payment(db, link.driver_id, int(parts[1]))
        except (IndexError, ValueError):
            pay = None
        if pay is None:                                       # not his payment
            return _reply(link.chat_id, T["button_gone"])
        if parts[0] == "cy":
            return _reply(link.chat_id, confirm(db, pay))
        if pay.answer:
            return _reply(link.chat_id, confirm(db, pay))      # "you already answered"
        link.pending_month_id, link.pending_topic, link.pending_line_key = pay.month_id, "cash", str(pay.id)
        db.commit()
        return _reply(link.chat_id, ASK_HOW_MUCH)
    try:
        kind, month_id = parts[0], int(parts[1])
        index = int(parts[2]) if kind == "w" else None
    except (IndexError, ValueError):
        return _reply(link.chat_id, T["button_gone"])
    found = _own_month(db, link.driver_id, month_id)       # only HIS month
    if not found or kind not in ("w", "o"):
        return _reply(link.chat_id, T["button_gone"])
    link.pending_month_id, link.pending_topic, link.pending_line_key = month_id, "other", None
    if kind == "w":
        lines = deductions(build_payslip(db, *found))
        if index is None or not 0 <= index < len(lines):
            link.pending_month_id = link.pending_topic = None
            db.commit()
            return _reply(link.chat_id, T["button_gone"])
        link.pending_topic, link.pending_line_key = "deduction", lines[index]["key"]
    db.commit()
    return _reply(link.chat_id, T["ask_reason"])


def _save_reason(db: Session, link: TelegramLink, text: str) -> dict:
    month_id, topic, line_key = link.pending_month_id, link.pending_topic, link.pending_line_key
    link.pending_month_id = link.pending_topic = link.pending_line_key = None
    db.commit()
    if topic == "cash":                                       # automation 3: "I got a different amount"
        from .payday import own_payment, report_wrong
        pay = own_payment(db, link.driver_id, int(line_key or 0))
        return _reply(link.chat_id, report_wrong(db, pay, text) if pay else T["button_gone"])
    found = _own_month(db, link.driver_id, month_id)
    if not found:
        return _reply(link.chat_id, T["button_gone"])
    try:
        d = open_dispute(db, *found, topic, line_key, text, source="telegram")
    except HTTPException as e:
        return _reply(link.chat_id, f"⚠️ {e.detail}")
    print(f"[automation 2] driver {link.driver_id} reported a problem on Telegram (dispute #{d.id})")
    return _reply(link.chat_id, T["reported"].format(id=d.id))


@router.post("/telegram/message")
def handle_message(body: MessageIn, db: Session = Depends(get_db)):
    chat_id = body.chat_id
    text = (body.text or "").strip()
    command = text.split()[0].lower().split("@")[0] if text.startswith("/") else ""

    if command == "/link":
        return _do_link(db, chat_id, text, body.message_id)
    link = _link(db, chat_id)
    if link is None:
        return _reply(chat_id, T["welcome"] if command in ("/start", "/help") else T["not_linked"])

    if text and not command:
        link.language = "ar" if ARABIC.search(text) else "en"
        db.commit()
    if body.callback_data:
        return _button(db, link, body.callback_data)
    if command == "/cancel":
        link.pending_month_id = link.pending_topic = link.pending_line_key = None
        db.commit()
        return _reply(chat_id, T["cancelled"])
    if link.pending_topic and text and not command:
        return _save_reason(db, link, text)
    if command == "/unlink":
        db.delete(link)
        db.commit()
        return _reply(chat_id, T["unlinked"])
    if command in ("/salary", "/start"):
        return _salary_reply(db, link)
    if command == "/wrong":
        return _wrong_menu(db, link)
    if command or not text:
        return _reply(chat_id, T["help"])

    # A question -> Gemini (in n8n) answers from HIS payslip only
    found = latest_salary(db, link.driver_id)
    if not found:
        return _reply(chat_id, T["no_salary"])
    if _limited(_asked, link.driver_id, QUESTIONS_PER_HOUR):
        return _reply(chat_id, T["too_many_questions"])
    _asked[link.driver_id].append(time.monotonic())
    p = build_payslip(db, *found)
    return {
        "action": "ask_ai",
        "question": text[:MAX_QUESTION],
        "language": link.language,                # answer in the language he wrote in
        "facts": _facts(p),                       # numbers only: no name, Iqama, IBAN or phone
        "fallback_text": "\n".join(explain_in_words(p)),   # used if Gemini is down
        "telegram": {"chat_id": chat_id, "reply_markup": wrong_buttons(p)},
        "delete_message_id": None,
    }


# ------------------------------------------------------------------ accountant answers -> Telegram

@router.get("/telegram/answers")
def answers_to_deliver(db: Session = Depends(get_db)):
    """Answered disputes of linked drivers, answered after they linked, not sent on Telegram yet."""
    rows = db.execute(
        select(Dispute, TelegramLink).join(TelegramLink, TelegramLink.driver_id == Dispute.driver_id)
        .where(Dispute.status != "open", Dispute.telegram_sent_at.is_(None),
               Dispute.answered_at >= TelegramLink.linked_at)
        .options(selectinload(Dispute.month)).order_by(Dispute.answered_at)
    ).all()
    out = []
    for d, link in rows[:50]:
        what = (f"{d.line_type} SAR {_n(d.line_amount or 0)}" if d.topic == "deduction" else d.topic)
        if d.status == "accepted":
            head = "✅ The payroll team agrees with you. / فريق الرواتب يتفق معك."
            if d.deduction_removed:
                head += "\nThe deduction was removed. / تم إلغاء الخصم."
        else:
            head = "ℹ️ The payroll team checked it and kept it. / راجع فريق الرواتب البلاغ وأبقى عليه."
        text = (f"📬 Answer to your report #{d.id} ({month_name(d.month.period)} – {what})\n"
                f"📬 الرد على بلاغك رقم {d.id}\n\n{head}\n\n{d.reply}")
        out.append({"dispute_id": d.id, "driver_id": d.driver_id, "language": link.language,
                    "reply": d.reply, "telegram": {"chat_id": link.chat_id, "text": text[:4000]}})
    return {"count": len(out), "answers": out}


@router.post("/telegram/answers/{dispute_id}/delivered")
def answer_delivered(dispute_id: int, db: Session = Depends(get_db)):
    d = db.get(Dispute, dispute_id)
    if d is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Dispute not found")
    if d.telegram_sent_at is None:
        d.telegram_sent_at = _now()
        db.commit()
    return {"ok": True}


# ------------------------------------------------------------------ salary messages (workflow 02)

def _approved(db: Session, month_id: int) -> PayrollMonth:
    month = db.get(PayrollMonth, month_id)
    if month is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Month not found")
    if month.status not in FINAL_STATUSES:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Salary messages are only sent for approved months")
    return month


@router.get("/months/{month_id}/telegram-salary-messages")
def salary_messages(month_id: int, db: Session = Depends(get_db)):
    """Linked drivers of this month who did not get their salary message yet."""
    month = _approved(db, month_id)
    done = set(db.scalars(select(TelegramNotice.driver_id).where(TelegramNotice.month_id == month.id,
                                                                  TelegramNotice.status == "sent")))
    rows = db.execute(
        select(Salary, TelegramLink).join(TelegramLink, TelegramLink.driver_id == Salary.driver_id)
        .where(Salary.month_id == month.id).order_by(Salary.driver_id)
    ).all()
    out = []
    for s, link in rows:
        if s.driver_id in done:
            continue
        p = build_payslip(db, month, s)
        out.append({
            "driver_id": s.driver_id, "language": link.language,
            "text_en": salary_message(p),
            "telegram": {"chat_id": link.chat_id, "reply_markup": wrong_buttons(p)},
        })
    return {"month_id": month.id, "period": month.period, "month_name": month_name(month.period),
            "count": len(out), "messages": out}


class NoticeIn(BaseModel):
    status: str = Field(pattern="^(sent|failed)$")
    note: str | None = Field(default=None, max_length=400)


@router.post("/months/{month_id}/telegram-salary-messages/{driver_id}/result")
def salary_message_result(month_id: int, driver_id: str, body: NoticeIn, db: Session = Depends(get_db)):
    month = _approved(db, month_id)
    link = db.scalar(select(TelegramLink).where(TelegramLink.driver_id == driver_id))
    row = db.scalar(select(TelegramNotice).where(TelegramNotice.month_id == month.id,
                                                  TelegramNotice.driver_id == driver_id))
    if row is None:
        row = TelegramNotice(month_id=month.id, driver_id=driver_id, chat_id=link.chat_id if link else "",
                             status=body.status)
        db.add(row)
    elif row.status == "sent":                     # never marked back
        return {"ok": True, "status": "sent"}
    row.status, row.note, row.at = body.status, body.note, _now()
    db.commit()
    return {"ok": True, "status": row.status}
