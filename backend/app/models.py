"""Database tables.

Stage 2: stations, drivers and users (logins).
Stage 3: payroll months, uploaded files, deliveries, adjustments, vehicles.
Later stages add salaries, payments and disputes.
"""

from datetime import date, datetime

from sqlalchemy import JSON, Boolean, Date, DateTime, Float, ForeignKey, Integer, String, func
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
    status: Mapped[str] = mapped_column(String(20), default="draft")   # draft -> ready -> ...
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())

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
