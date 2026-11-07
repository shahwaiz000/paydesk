"""Fill an empty database with DEMO users, stations and drivers.

Only runs when SEED_DEMO_DATA=true and the database has no users yet.
Stations and drivers come from samples/generated/drivers.xlsx
(make it with: python scripts/generate_demo_data.py).

Demo logins:
    accountant / demo123          - payroll accountant (head office)
    manager    / demo123          - finance manager
    ruh-01     / demo123          - cashier of station RUH-01 (any station code works)
    d10001     / 1234             - driver D10001 (any driver ID works, PIN 1234)
"""

import pandas as pd
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from .config import settings
from .models import ACCOUNTANT, CASHIER, DRIVER, FINANCE_MANAGER, Driver, Station, User
from .security import hash_password

DEMO_PASSWORD = "demo123"
DEMO_PIN = "1234"


def _clean(value) -> str | None:
    if value is None or pd.isna(value):
        return None
    text = str(value).strip()
    return text or None


def _to_date(value):
    text = _clean(value)
    return pd.to_datetime(text).date() if text else None


def seed_demo(db: Session) -> None:
    if (db.scalar(select(func.count()).select_from(User)) or 0) > 0:
        return  # already has data - never overwrite

    password_hash = hash_password(DEMO_PASSWORD)
    db.add_all([
        User(username="accountant", full_name="Payroll Accountant", password_hash=password_hash, role=ACCOUNTANT),
        User(username="manager", full_name="Finance Manager", password_hash=password_hash, role=FINANCE_MANAGER),
    ])

    drivers_file = settings.demo_data_dir / "drivers.xlsx"
    if not drivers_file.exists():
        print(f"[seed] {drivers_file} not found - only accountant/manager created.")
        db.commit()
        return

    df = pd.read_excel(drivers_file, dtype=str)

    # Stations
    stations: dict[str, Station] = {}
    for row in df[["station_code", "station", "city"]].drop_duplicates().itertuples(index=False):
        st = Station(code=row.station_code, name=row.station, city=row.city)
        stations[row.station_code] = st
        db.add(st)
        db.add(User(
            username=row.station_code.lower(),
            full_name=f"Cashier - {row.station}",
            password_hash=password_hash,
            role=CASHIER,
            station=st,
        ))

    # Drivers (one PIN hash for all demo drivers - hashing 750 times is slow)
    pin_hash = hash_password(DEMO_PIN)
    for row in df.itertuples(index=False):
        driver = Driver(
            id=row.driver_id,
            name=row.name,
            iqama_no=_clean(row.iqama_no),
            station=stations[row.station_code],
            joining_date=_to_date(row.joining_date),
            leaving_date=_to_date(row.leaving_date),
            payment_method=row.payment_method,
            iban=_clean(row.iban),
            phone=_clean(row.phone),
        )
        db.add(driver)
        db.add(User(
            username=row.driver_id.lower(),
            full_name=row.name,
            password_hash=pin_hash,
            role=DRIVER,
            driver=driver,
        ))

    db.commit()
    print(f"[seed] Demo data loaded: {len(stations)} stations, {len(df)} drivers.")
