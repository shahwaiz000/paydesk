"""Stage 11 (part 1): send the salary email to every station.

After the finance manager approves a month, the accountant clicks ONE button and PayDesk
makes one email per station:

    To:      the station cashier
    Body:    how many drivers, how much cash to prepare, the list of cash drivers
    Attach:  Excel file - every driver of the station, net salary, Cash/Bank, signature column

Demo mode: nothing really leaves PayDesk. The emails are saved in the Outbox, where you can
open each one and download its Excel file - exactly what the cashier would receive.

"Send a real copy": ONE email at a time goes to n8n (webhook). n8n adds an Arabic version with
Gemini and sends it with Gmail to YOUR inbox - never to a station. The address is set in n8n only.
"""

import base64
import io
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import StreamingResponse
import httpx
from openpyxl import Workbook
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
from sqlalchemy import func, select
from sqlalchemy.orm import Session, selectinload

from ..config import settings
from ..database import get_db
from ..deps import require_roles
from ..models import ACCOUNTANT, FINANCE_MANAGER, OutboxEmail, PayrollMonth, Salary, Station, User
from ..payroll.engine import money
from .months import get_month

router = APIRouter(prefix="/api/months/{month_id}/outbox", tags=["distribution"])
can_view = require_roles(ACCOUNTANT, FINANCE_MANAGER)

DEMO_DOMAIN = "stations.paydesk.demo"
XLSX = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"


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


# ------------------------------------------------------------------ API

def email_row(e: OutboxEmail, with_body: bool = False) -> dict:
    data = {
        "id": e.id, "station_code": e.station.code, "station": e.station.name, "to": e.to_address,
        "subject": e.subject, "attachment_name": e.attachment_name, "drivers": e.drivers,
        "cash_drivers": e.cash_drivers, "cash_total": e.cash_total,
        "bank_drivers": e.bank_drivers, "bank_total": e.bank_total,
        "status": e.status, "sent_by": e.sent_by, "sent_at": _iso(e.sent_at),
        "real_copies": e.real_copies or 0, "real_copy_at": _iso(e.real_copy_at),
    }
    if with_body:
        data["body"] = e.body
    return data


def outbox_out(db: Session, month: PayrollMonth) -> dict:
    emails = db.scalars(select(OutboxEmail).where(OutboxEmail.month_id == month.id)
                        .options(selectinload(OutboxEmail.station)).order_by(OutboxEmail.id)).all()
    stations = db.scalar(select(func.count(func.distinct(Salary.station_id))).where(Salary.month_id == month.id)) or 0
    return {
        "period": month.period, "month_status": month.status,
        "can_send": month.status == "approved" and not emails,
        "stations": stations,
        "sent": len(emails),
        "sent_at": _iso(emails[0].sent_at) if emails else None,
        "sent_by": emails[0].sent_by if emails else None,
        "cash_total": money(sum(e.cash_total for e in emails)),
        "bank_total": money(sum(e.bank_total for e in emails)),
        "emails": [email_row(e) for e in emails],
        "n8n_ready": bool(settings.n8n_webhook_url),
    }


@router.get("")
def outbox(month_id: int, db: Session = Depends(get_db), _: User = Depends(can_view)):
    return outbox_out(db, get_month(db, month_id))


@router.post("/send")
def send_station_emails(month_id: int, db: Session = Depends(get_db),
                        user: User = Depends(require_roles(ACCOUNTANT))):
    month = get_month(db, month_id)
    if month.status != "approved":
        raise HTTPException(status.HTTP_400_BAD_REQUEST,
                            "The finance manager must approve this month before salaries are sent to stations")
    if db.scalar(select(func.count()).where(OutboxEmail.month_id == month.id)):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "The station emails for this month were already sent")

    salaries = db.scalars(select(Salary).where(Salary.month_id == month.id)
                          .options(selectinload(Salary.driver), selectinload(Salary.station))
                          .order_by(Salary.driver_id)).all()
    if not salaries:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "No salaries in this month")

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
            status="demo", sent_by=user.username, sent_at=now,
        ))
    db.commit()
    print(f"[outbox] {month.period}: {len(by_station)} station emails saved (demo - not really sent)")
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


MAX_REAL_COPIES_PER_DAY = 10      # safety: nobody can flood your inbox by clicking many times


@router.post("/{email_id}/real-copy")
def send_real_copy(month_id: int, email_id: int, db: Session = Depends(get_db),
                   user: User = Depends(require_roles(ACCOUNTANT))):
    """Send ONE station email to n8n, which emails a real copy to your own Gmail."""
    month = get_month(db, month_id)
    e = _get_email(db, month, email_id)
    if not settings.n8n_webhook_url:
        raise HTTPException(status.HTTP_400_BAD_REQUEST,
                            "n8n is not connected. Add N8N_WEBHOOK_URL=... to backend\\.env and restart Window 3")
    today = _now().replace(hour=0, minute=0, second=0, microsecond=0)
    sent_today = db.scalar(select(func.sum(OutboxEmail.real_copies))
                           .where(OutboxEmail.real_copy_at >= today)) or 0
    if sent_today >= MAX_REAL_COPIES_PER_DAY:
        raise HTTPException(status.HTTP_429_TOO_MANY_REQUESTS,
                            f"Limit reached: {MAX_REAL_COPIES_PER_DAY} real copies per day")

    payload = {
        "source": "PayDesk", "period": month.period, "month_name": month_name(month.period),
        "station_code": e.station.code, "station": e.station.name,
        "station_email": e.to_address,             # shown in the email only - n8n sends to YOUR address
        "subject": e.subject, "body": e.body,
        "drivers": e.drivers, "cash_drivers": e.cash_drivers, "cash_total": e.cash_total,
        "bank_drivers": e.bank_drivers, "bank_total": e.bank_total,
        "attachment_name": e.attachment_name,
        "attachment_base64": base64.b64encode(e.attachment).decode(),
        "sent_by": user.username,
    }
    try:
        res = httpx.post(settings.n8n_webhook_url, json=payload, timeout=90)
    except httpx.HTTPError:
        raise HTTPException(status.HTTP_502_BAD_GATEWAY,
                            "Can't reach n8n. Is n8n running (npx n8n@2.45.7) and the workflow published?")
    if res.status_code >= 400:
        hint = " (workflow not published/active?)" if res.status_code == 404 else ""
        raise HTTPException(status.HTTP_502_BAD_GATEWAY, f"n8n answered with error {res.status_code}{hint}")

    e.real_copies = (e.real_copies or 0) + 1
    e.real_copy_at = _now()
    db.commit()
    print(f"[outbox] real copy of {e.station.code} sent to n8n")
    return email_row(e, with_body=True)
