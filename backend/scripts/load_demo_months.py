"""Load the demo files for September AND October and calculate both months.

Saves you uploading 8 files by hand. Run from the backend folder:
    .venv\\Scripts\\python.exe scripts\\load_demo_months.py

Uses the demo database (paydesk-demo.db) unless DATABASE_URL is set.
Make the files first with: scripts\\generate_demo_data.py
"""

import os
import sys
from pathlib import Path

os.environ.setdefault("DATABASE_URL", "sqlite:///./paydesk-demo.db")
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from sqlalchemy import select  # noqa: E402

from app import models  # noqa: E402,F401
from app.config import settings  # noqa: E402
from app.database import Base, SessionLocal, engine  # noqa: E402
from app.importing.service import UploadBlocked, handle_upload  # noqa: E402
from app.models import FILE_KINDS, PayrollMonth  # noqa: E402
from app.payroll.engine import calculate_month, get_settings  # noqa: E402

DEMO = settings.demo_data_dir
MONTHS = [("2026-09", DEMO / "2026-09"), ("2026-10", DEMO)]
FILES = {"drivers": "drivers.xlsx", "vehicles": "vehicles.xlsx",
         "deliveries": "deliveries.csv", "adjustments": "adjustments.xlsx"}


def main():
    Base.metadata.create_all(bind=engine)
    with SessionLocal() as db:
        get_settings(db)
        for period, folder in MONTHS:
            month = db.scalar(select(PayrollMonth).where(PayrollMonth.period == period))
            if month is None:
                month = PayrollMonth(period=period)
                db.add(month)
                db.commit()
            if month.status in ("submitted", "approved"):
                print(f"{period}: sent for approval / approved - skipped")
                continue
            print(f"{period}:")
            for kind in FILE_KINDS:
                path = folder / FILES[kind]
                if not path.exists():
                    sys.exit(f"  Missing {path} - run scripts\\generate_demo_data.py first")
                try:
                    up = handle_upload(db, month, kind, path.name, path.read_bytes(), "demo-loader")
                except UploadBlocked as e:
                    sys.exit(f"  {kind}: {e}")
                print(f"  {kind:12} {up.status:10} {up.rows:>8,} rows  {up.error_count} errors")
                if up.status != "imported":
                    sys.exit("  Stopped - fix the file errors first")
            totals = calculate_month(db, month)
            print(f"  salaries: {totals['drivers']} drivers, net {totals['net']:,.0f} SAR")
    print("Done. Refresh PayDesk in your browser.")


if __name__ == "__main__":
    main()
