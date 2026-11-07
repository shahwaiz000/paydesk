"""Database tables.

Stage 2: stations, drivers and users (logins).
Later stages add payroll months, salaries, adjustments, payments and disputes.
"""

from datetime import date

from sqlalchemy import Boolean, Date, ForeignKey, String
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
