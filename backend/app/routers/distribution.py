"""Stage 11 + Automation 1: the salary email to every station.

When the finance manager clicks "Approve & lock":
  1. PayDesk prepares one email per station (body + Excel to sign) and saves it in the Outbox.
  2. PayDesk calls the n8n webhook (N8N_MONTH_APPROVED_URL) - in the background, so approving stays fast.
  3. n8n does the rest (see n8n/01-station-emails.json): reads the emails from PayDesk, asks Gemini
     ONCE for the Arabic text, sends every email with Gmail, logs each one in a Google Sheet,
     reports each result back to PayDesk and emails the accountant a summary.

Demo safety: PayDesk tells n8n to send EVERY email to DEMO_INBOX (your own Gmail).
The real station address is only written inside the email. Nothing ever reaches a station.
"""

import io
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, status
from fastapi.responses import StreamingResponse
import httpx
from openpyxl import Workbook
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
from sqlalchemy import func, select
from sqlalchemy.orm import Session, selectinload

from ..config import settings
from ..database import SessionLocal, get_db
from ..deps import require_roles
from ..models import ACCOUNTANT, FINANCE_MANAGER, OutboxEmail, PayrollMonth, Salary, Station, User
from ..payroll.engine import money
from .months import get_month

router = APIRouter(prefix="/api/months/{month_id}/outbox", tags=["distribution"])
can_view = require_roles(ACCOUNTANT, FINANCE_MANAGER)

DEMO_DOMAIN = "stations.paydesk.demo"
XLSX = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
WAITING = ("prepared", "demo", "failed")      # emails n8n still has to send
STUCK_AFTER = timedelta(minutes=10)            # a "running" automation older than this can be started again


def _now() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


def _iso(dt: datetime | None) -> str | None:
    return dt.isoformat() + "Z" if dt else None


def month_name(period: str) -> str:
    return datetime.strptime(period + "-01", "%Y-%m-%d").strftime("%B %Y")   # "October 2026"


def station_email(st: Station) -> str:
    return st.email or f"{st.code.lower()}@{DEMO_DOMAIN}"


def _sar(x: float) -> str:
    return f"{x:,.2f}"


# ------------------------------------------------------------------ building one email

def build_body(month: PayrollMonth, st: Station, cash: list[Salary], bank: list[Salary]) -> str:
    cash_total = money(sum(s.net for s in cash))
    bank_total = money(sum(s.net for s in bank))
    lines = [
        f"Dear {st.name} cashier,",
        "",
        f"The {month_name(month.period)} driver salaries are approved and final.",
        "",
        f"  Drivers at your station:  {len(cash) + len(bank)}",
        f"  Cash drivers (you pay):   {len(cash)}  -  SAR {_sar(cash_total)}",
        f"  Bank drivers (bank pays): {len(bank)}  -  SAR {_sar(bank_total)}",
        "",
    ]
    if cash:
        lines += [f"Please prepare SAR {_sar(cash_total)} in cash and pay these drivers:", ""]
        for i, s in enumerate(cash, 1):
            lines.append(f"  {i:>3}. {s.driver_id:<8} {s.driver.name:<28} SAR {_sar(s.net):>10}")
        lines += [
            "",
            "Pay each driver the exact amount, ask him to sign the attached sheet,",
            "and keep the signed sheet for the finance team.",
        ]
    else:
        lines.append("You have no cash drivers this month - nothing to pay in cash.")
    if bank:
        lines += ["", "Bank drivers will receive their salary by bank transfer. You don't pay them."]
    lines += [
        "",
        "Drivers can see their full payslip in PayDesk. If a driver doesn't agree with",
        "an amount, he can press \"I don't agree\" on his payslip.",
        "",
        "Regards,",
        "Payroll team - PayDesk",
    ]
    return "\n".join(lines)


def build_sheet(month: PayrollMonth, st: Station, cash: list[Salary], bank: list[Salary]) -> bytes:
    wb = Workbook()
    ws = wb.active
    ws.title = "Salaries"
    bold = Font(bold=True)
    head_fill = PatternFill("solid", fgColor="E0E7FF")
    thin = Side(style="thin", color="CBD5E1")
    box = Border(left=thin, right=thin, top=thin, bottom=thin)

    ws.append([f"{st.code} - {st.name}  |  {month_name(month.period)} salaries (approved)"])
    ws["A1"].font = Font(bold=True, size=13)
    ws.append([])

    def table(title: str, rows: list[Salary], signature: bool) -> None:
        ws.append([title])
        ws.cell(ws.max_row, 1).font = bold
        headers = ["#", "Driver ID", "Name", "Days", "Gross (SAR)", "Deductions (SAR)", "Net to pay (SAR)"]
        if signature:
            headers += ["Paid on (date)", "Driver signature"]
        ws.append(headers)
        for c in ws[ws.max_row]:
            c.font, c.fill, c.border = bold, head_fill, box
        for i, s in enumerate(rows, 1):
            ws.append([i, s.driver_id, s.driver.name, s.days_worked, s.gross, s.deductions_applied, s.net]
                      + (["", ""] if signature else []))
            for c in ws[ws.max_row]:
                c.border = box
        ws.append(["", "", "Total", "", money(sum(s.gross for s in rows)),
                   money(sum(s.deductions_applied for s in rows)), money(sum(s.net for s in rows))])
        for c in ws[ws.max_row]:
            c.font = bold
        ws.append([])

    table(f"CASH drivers - paid by you ({len(cash)})", cash, signature=True)
    if bank:
        table(f"BANK drivers - paid by bank transfer, for your information ({len(bank)})", bank, signature=False)

    for col, width in zip("ABCDEFGHI", (5, 11, 30, 7, 13, 16, 16, 15, 22)):
        ws.column_dimensions[col].width = width
    for row in ws.iter_rows(min_row=3):
        for c in row:
            if isinstance(c.value, float):
                c.number_format = "#,##0.00"
                c.alignment = Alignment(horizontal="right")
    ws.page_setup.orientation = "landscape"
    ws.page_setup.fitToWidth = 1

    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


# ------------------------------------------------------------------ preparing + starting n8n

def prepare_station_emails(db: Session, month: PayrollMonth, by: str) -> int:
    """Make one Outbox email per station (only once per month). Returns how many exist."""
    existing = db.scalar(select(func.count()).where(OutboxEmail.month_id == month.id)) or 0
    if existing:
        return existing
    salaries = db.scalars(select(Salary).where(Salary.month_id == month.id)
                          .options(selectinload(Salary.driver), selectinload(Salary.station))
                          .order_by(Salary.driver_id)).all()
    by_station: dict[int, list[Salary]] = {}
    for s in salaries:
        by_station.setdefault(s.station_id, []).append(s)

    now = _now()
    for rows in sorted(by_station.values(), key=lambda r: r[0].station.code):
        st = rows[0].station
        cash = [s for s in rows if s.payment_method == "Cash"]
        bank = [s for s in rows if s.payment_method != "Cash"]
        db.add(OutboxEmail(
            month_id=month.id, station_id=st.id, to_address=station_email(st),
            subject=f"{month_name(month.period)} salaries - {st.code} {st.name} - "
                    f"cash to pay SAR {_sar(money(sum(s.net for s in cash)))}",
            body=build_body(month, st, cash, bank),
            attachment_name=f"PayDesk_{month.period}_{st.code}_salaries.xlsx",
            attachment=build_sheet(month, st, cash, bank),
            drivers=len(rows), cash_drivers=len(cash), cash_total=money(sum(s.net for s in cash)),
            bank_drivers=len(bank), bank_total=money(sum(s.net for s in bank)),
            status="prepared", sent_by=by, sent_at=now,
        ))
    db.flush()
    print(f"[outbox] {month.period}: {len(by_station)} station emails prepared")
    return len(by_station)


def missing_setup() -> list[str]:
    """Which .env lines are still missing for automation 1."""
    need = {"N8N_MONTH_APPROVED_URL": settings.n8n_month_approved_url,
            "AUTOMATION_KEY": settings.automation_key, "DEMO_INBOX": settings.demo_inbox}
    return [name for name, value in need.items() if not value]


def _waiting(db: Session, month: PayrollMonth) -> int:
    return db.scalar(select(func.count()).where(OutboxEmail.month_id == month.id,
                                                 OutboxEmail.status.in_(WAITING))) or 0


def begin_run(db: Session, month: PayrollMonth, by: str) -> bool:
    """Mark the automation as started. Returns True if n8n should be called now."""
    month.emails_run_by = by
    month.emails_run_started_at = _now()
    month.emails_run_finished_at = None
    missing = missing_setup()
    if missing:
        month.emails_run_status = "not_connected"
        month.emails_run_note = "Add " + ", ".join(missing) + " to backend\\.env and restart the backend window"
        return False
    month.emails_run_status = "running"
    month.emails_run_note = None
    return True


def call_n8n(month_id: int) -> None:
    """Runs in the background after the response is sent: tell n8n to start."""
    with SessionLocal() as db:
        month = db.get(PayrollMonth, month_id)
        if month is None:
            return
        payload = {"source": "PayDesk", "event": "month_approved", "month_id": month.id,
                   "period": month.period, "month_name": month_name(month.period),
                   "stations_to_send": _waiting(db, month)}
        note = None
        try:
            res = httpx.post(settings.n8n_month_approved_url, json=payload, timeout=20)
            if res.status_code == 404:
                note = "n8n answered 404 - is the workflow published (Active)?"
            elif res.status_code >= 400:
                note = f"n8n answered with error {res.status_code}"
        except httpx.HTTPError:
            note = "Can't reach n8n. Is it running (npx n8n@2.45.7)?"
        if note:
            month.emails_run_status = "failed"
            month.emails_run_note = note
            month.emails_run_finished_at = _now()
            print(f"[automation 1] {month.period}: {note}")
        else:
            print(f"[automation 1] {month.period}: n8n started ({payload['stations_to_send']} stations)")
        db.commit()


def run_seconds(month: PayrollMonth) -> int | None:
    if month.emails_run_started_at and month.emails_run_finished_at:
        return max(0, round((month.emails_run_finished_at - month.emails_run_started_at).total_seconds()))
    return None


# ------------------------------------------------------------------ API (logged-in users)

def _status(e: OutboxEmail) -> str:
    return "prepared" if e.status == "demo" else e.status


def email_row(e: OutboxEmail, with_body: bool = False) -> dict:
    data = {
        "id": e.id, "station_code": e.station.code, "station": e.station.name, "to": e.to_address,
        "subject": e.subject, "attachment_name": e.attachment_name, "drivers": e.drivers,
        "cash_drivers": e.cash_drivers, "cash_total": e.cash_total,
        "bank_drivers": e.bank_drivers, "bank_total": e.bank_total,
        "status": _status(e), "prepared_at": _iso(e.sent_at),
        "delivered_to": e.delivered_to, "delivered_at": _iso(e.delivered_at),
        "gmail_id": e.gmail_id, "delivery_note": e.delivery_note,
    }
    if with_body:
        data["body"] = e.body
    return data


def _can_run(month: PayrollMonth, waiting: int) -> bool:
    if month.status != "approved" or waiting == 0:
        return False
    if month.emails_run_status == "running":
        return bool(month.emails_run_started_at and _now() - month.emails_run_started_at > STUCK_AFTER)
    return True


def outbox_out(db: Session, month: PayrollMonth) -> dict:
    emails = db.scalars(select(OutboxEmail).where(OutboxEmail.month_id == month.id)
                        .options(selectinload(OutboxEmail.station)).order_by(OutboxEmail.id)).all()
    stations = db.scalar(select(func.count(func.distinct(Salary.station_id))).where(Salary.month_id == month.id)) or 0
    statuses = [_status(e) for e in emails]
    waiting = sum(1 for x in statuses if x in WAITING)
    return {
        "period": month.period, "month_status": month.status,
        "stations": stations,
        "prepared": len(emails),
        "delivered": statuses.count("sent"),
        "failed": statuses.count("failed"),
        "waiting": waiting,
        "cash_total": money(sum(e.cash_total for e in emails)),
        "bank_total": money(sum(e.bank_total for e in emails)),
        "run": {
            "status": month.emails_run_status, "by": month.emails_run_by,
            "started_at": _iso(month.emails_run_started_at), "finished_at": _iso(month.emails_run_finished_at),
            "seconds": run_seconds(month), "note": month.emails_run_note,
        },
        "can_run": _can_run(month, waiting if emails else stations),
        "n8n_ready": not missing_setup(),
        "missing_setup": missing_setup(),
        "demo_inbox": settings.demo_inbox or None,
        "emails": [email_row(e) for e in emails],
    }


@router.get("")
def outbox(month_id: int, db: Session = Depends(get_db), _: User = Depends(can_view)):
    return outbox_out(db, get_month(db, month_id))


@router.post("/run")
def run_automation(month_id: int, tasks: BackgroundTasks, db: Session = Depends(get_db),
                   user: User = Depends(require_roles(ACCOUNTANT))):
    """Start automation 1 again (n8n wasn't connected, failed, or some emails failed).
    n8n only gets the emails that are not sent yet - nobody gets the same email twice."""
    month = get_month(db, month_id)
    if month.status != "approved":
        raise HTTPException(status.HTTP_400_BAD_REQUEST,
                            "The finance manager must approve this month before salaries are sent to stations")
    prepare_station_emails(db, month, user.username)
    if not _can_run(month, _waiting(db, month)):
        reason = ("The automation is already running" if month.emails_run_status == "running"
                  else "All station emails are already sent")
        raise HTTPException(status.HTTP_400_BAD_REQUEST, reason)
    if begin_run(db, month, user.username):
        tasks.add_task(call_n8n, month.id)
    db.commit()
    return outbox_out(db, month)


def _get_email(db: Session, month: PayrollMonth, email_id: int) -> OutboxEmail:
    e = db.get(OutboxEmail, email_id)
    if e is None or e.month_id != month.id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Email not found")
    return e


@router.get("/{email_id}")
def open_email(month_id: int, email_id: int, db: Session = Depends(get_db), _: User = Depends(can_view)):
    return email_row(_get_email(db, get_month(db, month_id), email_id), with_body=True)


@router.get("/{email_id}/attachment")
def download_attachment(month_id: int, email_id: int, db: Session = Depends(get_db), _: User = Depends(can_view)):
    e = _get_email(db, get_month(db, month_id), email_id)
    return StreamingResponse(io.BytesIO(e.attachment), media_type=XLSX,
                             headers={"Content-Disposition": f'attachment; filename="{e.attachment_name}"'})
