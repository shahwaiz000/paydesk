"""Database tables.

Stage 2: stations, drivers and users (logins).
Stage 3: payroll months, uploaded files, deliveries, adjustments, vehicles.
Later stages add salaries, payments and disputes.
"""

from datetime import date, datetime

from sqlalchemy import (
    JSON, Boolean, Date, DateTime, Float, ForeignKey, Integer, LargeBinary, String, Text, UniqueConstraint, func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .database import Base

# The 4 kinds of users in PayDesk
ACCOUNTANT = "accountant"
FINANCE_MANAGER = "finance_manager"
CASHIER = "cashier"
DRIVER = "driver"
ROLES = (ACCOUNTANT, FINANCE_MANAGER, CASHIER, DRIVER)


class Station(Base):
    __tablename__ = "stations"

    id: Mapped[int] = mapped_column(primary_key=True)
    code: Mapped[str] = mapped_column(String(20), unique=True, index=True)   # RUH-01
    name: Mapped[str] = mapped_column(String(100))                           # Riyadh - Azizia
    city: Mapped[str] = mapped_column(String(50))                            # Riyadh
    email: Mapped[str | None] = mapped_column(String(120))                   # station cashier email (Stage 11)

    drivers: Mapped[list["Driver"]] = relationship(back_populates="station")


class Driver(Base):
    __tablename__ = "drivers"

    id: Mapped[str] = mapped_column(String(20), primary_key=True)            # D10001
    name: Mapped[str] = mapped_column(String(100))
    iqama_no: Mapped[str | None] = mapped_column(String(20))
    station_id: Mapped[int] = mapped_column(ForeignKey("stations.id"), index=True)
    joining_date: Mapped[date] = mapped_column(Date)
    leaving_date: Mapped[date | None] = mapped_column(Date)
    payment_method: Mapped[str] = mapped_column(String(10))                  # Cash / Bank
    iban: Mapped[str | None] = mapped_column(String(34))
    phone: Mapped[str | None] = mapped_column(String(20))

    station: Mapped[Station] = relationship(back_populates="drivers")


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(primary_key=True)
    username: Mapped[str] = mapped_column(String(50), unique=True, index=True)  # always lowercase
    full_name: Mapped[str] = mapped_column(String(100))
    password_hash: Mapped[str] = mapped_column(String(100))   # for drivers this is their PIN
    role: Mapped[str] = mapped_column(String(20))
    station_id: Mapped[int | None] = mapped_column(ForeignKey("stations.id"))   # cashiers
    driver_id: Mapped[str | None] = mapped_column(ForeignKey("drivers.id"))     # drivers
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)

    station: Mapped[Station | None] = relationship()
    driver: Mapped[Driver | None] = relationship()


# ------------------------------------------------------------------ Stage 3

# The 4 files, in the order they must be uploaded
FILE_KINDS = ("drivers", "vehicles", "deliveries", "adjustments")


class PayrollMonth(Base):
    __tablename__ = "payroll_months"

    id: Mapped[int] = mapped_column(primary_key=True)
    period: Mapped[str] = mapped_column(String(7), unique=True)        # "2026-10"
    status: Mapped[str] = mapped_column(String(20), default="draft")
    # draft -> ready (4 files clean) -> calculated -> submitted (waiting for approval) -> approved (locked)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    ai_summary: Mapped[str | None] = mapped_column(Text)               # AI-written month summary
    ai_summary_at: Mapped[datetime | None] = mapped_column(DateTime)
    # Stage 10: accountant sends -> finance manager approves (month locked) or sends back
    submitted_by: Mapped[str | None] = mapped_column(String(50))
    submitted_at: Mapped[datetime | None] = mapped_column(DateTime)
    approved_by: Mapped[str | None] = mapped_column(String(50))
    approved_at: Mapped[datetime | None] = mapped_column(DateTime)
    returned_note: Mapped[str | None] = mapped_column(String(400))   # why the manager sent it back
    # Automation 1: n8n sends the station emails after approval
    # None -> running -> done / failed;  not_connected = n8n webhook not set in .env
    emails_run_status: Mapped[str | None] = mapped_column(String(20))
    emails_run_by: Mapped[str | None] = mapped_column(String(50))
    emails_run_started_at: Mapped[datetime | None] = mapped_column(DateTime)
    emails_run_finished_at: Mapped[datetime | None] = mapped_column(DateTime)
    emails_run_note: Mapped[str | None] = mapped_column(String(400))

    uploads: Mapped[list["FileUpload"]] = relationship(
        back_populates="month", cascade="all, delete-orphan", order_by="FileUpload.id"
    )


class FileUpload(Base):
    """One uploaded file and its check report (the latest one per kind counts)."""

    __tablename__ = "file_uploads"

    id: Mapped[int] = mapped_column(primary_key=True)
    month_id: Mapped[int] = mapped_column(ForeignKey("payroll_months.id"), index=True)
    kind: Mapped[str] = mapped_column(String(20))                      # drivers / vehicles / ...
    filename: Mapped[str] = mapped_column(String(200))
    uploaded_by: Mapped[str] = mapped_column(String(50))
    uploaded_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    rows: Mapped[int] = mapped_column(Integer, default=0)
    error_count: Mapped[int] = mapped_column(Integer, default=0)
    warning_count: Mapped[int] = mapped_column(Integer, default=0)
    status: Mapped[str] = mapped_column(String(20), default="checking")  # imported / has_errors
    column_map: Mapped[dict] = mapped_column(JSON, default=dict)       # "Driver No" -> driver_id
    issues: Mapped[list] = mapped_column(JSON, default=list)
    summary: Mapped[dict] = mapped_column(JSON, default=dict)

    month: Mapped[PayrollMonth] = relationship(back_populates="uploads")


class DeliveryDay(Base):
    """Deliveries per driver per day (or per month when the export only has totals)."""

    __tablename__ = "delivery_days"

    id: Mapped[int] = mapped_column(primary_key=True)
    month_id: Mapped[int] = mapped_column(ForeignKey("payroll_months.id"), index=True)
    driver_id: Mapped[str] = mapped_column(String(20), index=True)
    day: Mapped[date | None] = mapped_column(Date)
    prepaid: Mapped[int] = mapped_column(Integer, default=0)
    cod: Mapped[int] = mapped_column(Integer, default=0)


class VehicleAssignment(Base):
    __tablename__ = "vehicle_assignments"

    id: Mapped[int] = mapped_column(primary_key=True)
    month_id: Mapped[int] = mapped_column(ForeignKey("payroll_months.id"), index=True)
    plate_no: Mapped[str] = mapped_column(String(20), index=True)
    driver_id: Mapped[str] = mapped_column(String(20))
    from_date: Mapped[date] = mapped_column(Date)
    to_date: Mapped[date] = mapped_column(Date)


class Adjustment(Base):
    """A deduction or bonus line. Every deduction must say WHY (type + reference/note)."""

    __tablename__ = "adjustments"

    id: Mapped[int] = mapped_column(primary_key=True)
    month_id: Mapped[int] = mapped_column(ForeignKey("payroll_months.id"), index=True)
    driver_id: Mapped[str] = mapped_column(String(20), index=True)
    plate_no: Mapped[str | None] = mapped_column(String(20))
    matched_by_plate: Mapped[bool] = mapped_column(Boolean, default=False)
    kind: Mapped[str] = mapped_column(String(10))                      # Deduction / Bonus
    type: Mapped[str] = mapped_column(String(20))                      # Traffic fine, Lost parcel...
    amount: Mapped[float] = mapped_column(Float)
    day: Mapped[date | None] = mapped_column(Date)
    reference: Mapped[str | None] = mapped_column(String(50))
    note: Mapped[str | None] = mapped_column(String(200))
    source: Mapped[str] = mapped_column(String(20), default="file")   # file / ai_document


# ------------------------------------------------------------------ Stage 4

class PayrollSetting(Base):
    """Salary rules. One row. The accountant can change these (no code change needed)."""

    __tablename__ = "payroll_settings"

    id: Mapped[int] = mapped_column(primary_key=True)
    fixed_salary: Mapped[float] = mapped_column(Float, default=1500)
    prepaid_rate: Mapped[float] = mapped_column(Float, default=2)
    cod_rate: Mapped[float] = mapped_column(Float, default=3)
    proration_days: Mapped[int] = mapped_column(Integer, default=30)       # joiners/leavers: fixed / 30 x days
    deduction_cap_pct: Mapped[float] = mapped_column(Float, default=50)    # max % of gross deducted
    unusual_change_pct: Mapped[float] = mapped_column(Float, default=30)   # flag if net moves more than this


class Salary(Base):
    """One driver's salary for one month."""

    __tablename__ = "salaries"

    id: Mapped[int] = mapped_column(primary_key=True)
    month_id: Mapped[int] = mapped_column(ForeignKey("payroll_months.id"), index=True)
    driver_id: Mapped[str] = mapped_column(ForeignKey("drivers.id"), index=True)
    station_id: Mapped[int] = mapped_column(ForeignKey("stations.id"), index=True)
    payment_method: Mapped[str] = mapped_column(String(10))
    days_worked: Mapped[int] = mapped_column(Integer)
    full_month: Mapped[bool] = mapped_column(Boolean)
    fixed_pay: Mapped[float] = mapped_column(Float)
    prepaid_count: Mapped[int] = mapped_column(Integer)
    prepaid_pay: Mapped[float] = mapped_column(Float)
    cod_count: Mapped[int] = mapped_column(Integer)
    cod_pay: Mapped[float] = mapped_column(Float)
    bonuses: Mapped[float] = mapped_column(Float)
    gross: Mapped[float] = mapped_column(Float)
    deductions_due: Mapped[float] = mapped_column(Float)       # this month + carried in
    deductions_applied: Mapped[float] = mapped_column(Float)   # after the 50% cap
    carried_forward: Mapped[float] = mapped_column(Float)      # goes to next month
    net: Mapped[float] = mapped_column(Float)
    previous_net: Mapped[float | None] = mapped_column(Float)
    flags: Mapped[list] = mapped_column(JSON, default=list)    # ["unusual_change", "capped", ...]
    change_reason: Mapped[str | None] = mapped_column(String(400))  # rule-based: why net changed vs last month
    ai_reason: Mapped[str | None] = mapped_column(String(400))      # AI-written one-line reason

    driver: Mapped[Driver] = relationship()
    station: Mapped[Station] = relationship()
    lines: Mapped[list["SalaryLine"]] = relationship(
        back_populates="salary", cascade="all, delete-orphan", order_by="SalaryLine.id"
    )


class SalaryLine(Base):
    """A deduction or bonus line on the payslip, with its reason."""

    __tablename__ = "salary_lines"

    id: Mapped[int] = mapped_column(primary_key=True)
    salary_id: Mapped[int] = mapped_column(ForeignKey("salaries.id"), index=True)
    kind: Mapped[str] = mapped_column(String(10))              # Deduction / Bonus
    type: Mapped[str] = mapped_column(String(20))
    amount_due: Mapped[float] = mapped_column(Float)
    amount_applied: Mapped[float] = mapped_column(Float)       # what was actually taken this month
    day: Mapped[date | None] = mapped_column(Date)
    reference: Mapped[str | None] = mapped_column(String(50))
    note: Mapped[str | None] = mapped_column(String(200))
    plate_no: Mapped[str | None] = mapped_column(String(20))
    carried_from: Mapped[str | None] = mapped_column(String(7))  # "2026-09" if carried from an earlier month

    salary: Mapped[Salary] = relationship(back_populates="lines")


# ------------------------------------------------------------------ Stage 9

DISPUTE_TOPICS = ("deduction", "deliveries", "days", "other")


class Dispute(Base):
    """A driver says "I don't agree". The line he means is copied here, because payslip lines are
    rebuilt every time salaries are recalculated."""

    __tablename__ = "disputes"

    id: Mapped[int] = mapped_column(primary_key=True)
    month_id: Mapped[int] = mapped_column(ForeignKey("payroll_months.id"), index=True)
    driver_id: Mapped[str] = mapped_column(ForeignKey("drivers.id"), index=True)
    station_id: Mapped[int] = mapped_column(ForeignKey("stations.id"), index=True)
    topic: Mapped[str] = mapped_column(String(20))                    # deduction / deliveries / days / other
    line_key: Mapped[str | None] = mapped_column(String(200))          # which deduction line (topic = deduction)
    line_type: Mapped[str | None] = mapped_column(String(20))
    line_amount: Mapped[float | None] = mapped_column(Float)
    line_day: Mapped[date | None] = mapped_column(Date)
    line_reference: Mapped[str | None] = mapped_column(String(50))
    line_note: Mapped[str | None] = mapped_column(String(200))
    line_carried_from: Mapped[str | None] = mapped_column(String(7))
    message: Mapped[str] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(10), default="open")   # open / accepted / rejected
    reply: Mapped[str | None] = mapped_column(Text)
    ai_draft: Mapped[str | None] = mapped_column(Text)
    deduction_removed: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    answered_at: Mapped[datetime | None] = mapped_column(DateTime)
    answered_by: Mapped[str | None] = mapped_column(String(50))
    source: Mapped[str] = mapped_column(String(10), default="web")      # web / telegram (automation 2)
    telegram_sent_at: Mapped[datetime | None] = mapped_column(DateTime)  # answer delivered on Telegram

    driver: Mapped[Driver] = relationship()
    station: Mapped[Station] = relationship()
    month: Mapped[PayrollMonth] = relationship()


# ------------------------------------------------------------------ Stage 10

MONTH_STATUSES = ("draft", "ready", "calculated", "submitted", "approved")
LOCKED_STATUSES = ("submitted", "approved")      # nobody can change files, fines or salaries


class MonthEvent(Base):
    """History of a payroll month: who sent it, approved it or sent it back, and when. Only ever added to."""

    __tablename__ = "month_events"

    id: Mapped[int] = mapped_column(primary_key=True)
    month_id: Mapped[int] = mapped_column(ForeignKey("payroll_months.id"), index=True)
    action: Mapped[str] = mapped_column(String(20))        # submitted / approved / sent_back
    by: Mapped[str] = mapped_column(String(50))
    at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    note: Mapped[str | None] = mapped_column(String(400))
    totals: Mapped[dict] = mapped_column(JSON, default=dict)   # drivers / net at that moment


# ------------------------------------------------------------------ Stage 11

class OutboxEmail(Base):
    """One salary email to one station (after the month is approved).

    PayDesk prepares the email + Excel here when the month is approved. n8n (automation 1) then
    sends it with Gmail - to the demo inbox, never to the real station - and reports back.
    """

    __tablename__ = "outbox_emails"

    id: Mapped[int] = mapped_column(primary_key=True)
    month_id: Mapped[int] = mapped_column(ForeignKey("payroll_months.id"), index=True)
    station_id: Mapped[int] = mapped_column(ForeignKey("stations.id"), index=True)
    to_address: Mapped[str] = mapped_column(String(120))
    subject: Mapped[str] = mapped_column(String(200))
    body: Mapped[str] = mapped_column(Text)
    attachment_name: Mapped[str] = mapped_column(String(120))
    attachment: Mapped[bytes] = mapped_column(LargeBinary)
    drivers: Mapped[int] = mapped_column(Integer)
    cash_drivers: Mapped[int] = mapped_column(Integer)
    cash_total: Mapped[float] = mapped_column(Float)
    bank_drivers: Mapped[int] = mapped_column(Integer)
    bank_total: Mapped[float] = mapped_column(Float)
    # prepared = waiting for n8n · sent = n8n sent it with Gmail · failed = n8n could not send it
    # (old rows may say "demo" - treated like "prepared")
    status: Mapped[str] = mapped_column(String(20), default="prepared")
    real_copies: Mapped[int] = mapped_column(Integer, default=0)       # old Stage 11 button (not used any more)
    real_copy_at: Mapped[datetime | None] = mapped_column(DateTime)
    delivered_to: Mapped[str | None] = mapped_column(String(120))      # the demo inbox n8n really sent it to
    delivered_at: Mapped[datetime | None] = mapped_column(DateTime)
    gmail_id: Mapped[str | None] = mapped_column(String(80))
    delivery_note: Mapped[str | None] = mapped_column(String(400))     # error text when it failed
    sent_by: Mapped[str] = mapped_column(String(50))
    sent_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())

    station: Mapped[Station] = relationship()


# ------------------------------------------------------------------ Automation 2 (Telegram)

class TelegramLink(Base):
    """One Telegram chat <-> one driver. The driver links once with /link <driver ID> <PIN>.
    After that the bot only ever shows him HIS OWN salary."""

    __tablename__ = "telegram_links"

    id: Mapped[int] = mapped_column(primary_key=True)
    chat_id: Mapped[str] = mapped_column(String(30), unique=True, index=True)
    driver_id: Mapped[str] = mapped_column(ForeignKey("drivers.id"), unique=True, index=True)
    linked_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    language: Mapped[str] = mapped_column(String(2), default="en")      # en / ar - the last language he wrote in
    # "This is wrong" was tapped -> the next message is the reason
    pending_month_id: Mapped[int | None] = mapped_column(Integer)
    pending_topic: Mapped[str | None] = mapped_column(String(20))
    pending_line_key: Mapped[str | None] = mapped_column(String(200))

    driver: Mapped[Driver] = relationship()


class TelegramNotice(Base):
    """Salary message sent on Telegram (workflow 02): one per driver per month - never twice."""

    __tablename__ = "telegram_notices"
    __table_args__ = (UniqueConstraint("month_id", "driver_id"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    month_id: Mapped[int] = mapped_column(ForeignKey("payroll_months.id"), index=True)
    driver_id: Mapped[str] = mapped_column(ForeignKey("drivers.id"))
    chat_id: Mapped[str] = mapped_column(String(30))
    status: Mapped[str] = mapped_column(String(10))                     # sent / failed
    note: Mapped[str | None] = mapped_column(String(400))
    at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())


class AutomationState(Base):
    """Small saved values for n8n, e.g. the last Telegram update it has read."""

    __tablename__ = "automation_state"

    key: Mapped[str] = mapped_column(String(50), primary_key=True)
    value: Mapped[str] = mapped_column(String(200))


# ------------------------------------------------------------------ Automation 3 (cash received?)

class CashPayment(Base):
    """A station cashier paid a cash driver. The driver confirms on Telegram (automation 3) -
    this replaces the paper signature sheet."""

    __tablename__ = "cash_payments"
    __table_args__ = (UniqueConstraint("month_id", "driver_id"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    month_id: Mapped[int] = mapped_column(ForeignKey("payroll_months.id"), index=True)
    driver_id: Mapped[str] = mapped_column(ForeignKey("drivers.id"), index=True)
    station_id: Mapped[int] = mapped_column(ForeignKey("stations.id"), index=True)
    amount: Mapped[float] = mapped_column(Float)                       # net salary paid in cash
    paid_by: Mapped[str] = mapped_column(String(50))                   # cashier username
    paid_at: Mapped[datetime] = mapped_column(DateTime)
    asked_at: Mapped[datetime | None] = mapped_column(DateTime)        # Telegram question sent
    reminded_at: Mapped[datetime | None] = mapped_column(DateTime)     # one reminder if no answer
    answer: Mapped[str | None] = mapped_column(String(10))             # confirmed / wrong
    answered_at: Mapped[datetime | None] = mapped_column(DateTime)
    said_amount: Mapped[float | None] = mapped_column(Float)           # "I only got 1000"
    note: Mapped[str | None] = mapped_column(String(300))
    alerted_at: Mapped[datetime | None] = mapped_column(DateTime)      # accountant emailed about "wrong"

    driver: Mapped[Driver] = relationship()
    station: Mapped[Station] = relationship()
    month: Mapped[PayrollMonth] = relationship()
