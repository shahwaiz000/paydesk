"""Upload flow: read file -> match columns -> check -> import (or keep for fixing)."""

from __future__ import annotations

import calendar
import io
from datetime import date
from pathlib import Path

import pandas as pd
from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from ..config import settings
from ..models import (
    FILE_KINDS, Adjustment, DeliveryDay, Driver, FileUpload, PayrollMonth, Station, VehicleAssignment,
)
from .checks import (
    CheckContext, CheckResult, apply_fixes, check_adjustments, check_deliveries, check_drivers,
    check_vehicles,
)
from ..payroll.engine import clear_salaries
from .columns import FILE_FIELDS, match_columns

MAX_ISSUES_SAVED = 300
NEEDS_FIRST = {
    "drivers": [],
    "vehicles": ["drivers"],
    "deliveries": ["drivers"],
    "adjustments": ["drivers", "vehicles"],
}


class UploadBlocked(Exception):
    pass


# ------------------------------------------------------------------ reading

def read_table(filename: str, content: bytes) -> pd.DataFrame:
    name = filename.lower()
    if name.endswith((".xlsx", ".xls")):
        return pd.read_excel(io.BytesIO(content), dtype=str)
    if name.endswith(".csv"):
        for encoding in ("utf-8-sig", "cp1256", "latin-1"):
            try:
                return pd.read_csv(io.BytesIO(content), dtype=str, encoding=encoding)
            except UnicodeDecodeError:
                continue
    raise UploadBlocked("Please upload an Excel (.xlsx) or CSV (.csv) file")


def month_range(period: str) -> tuple[date, date]:
    year, month = map(int, period.split("-"))
    return date(year, month, 1), date(year, month, calendar.monthrange(year, month)[1])


def latest_uploads(month: PayrollMonth) -> dict[str, FileUpload]:
    latest: dict[str, FileUpload] = {}
    for up in month.uploads:  # ordered by id, so later ones win
        latest[up.kind] = up
    return latest


def build_context(db: Session, month: PayrollMonth) -> CheckContext:
    start, end = month_range(month.period)
    ctx = CheckContext(month_start=start, month_end=end)
    for d in db.scalars(select(Driver)):
        ctx.known_driver_ids.add(d.id)
        if d.joining_date <= end and (d.leaving_date is None or d.leaving_date >= start):
            ctx.driver_periods[d.id] = (max(d.joining_date, start), min(d.leaving_date or end, end))
    rows = db.execute(
        select(VehicleAssignment.plate_no, VehicleAssignment.driver_id,
               VehicleAssignment.from_date, VehicleAssignment.to_date)
        .where(VehicleAssignment.month_id == month.id)
    ).all()
    v = pd.DataFrame(rows, columns=["plate_no", "driver_id", "from_date", "to_date"])
    if not v.empty:
        v["from_date"] = pd.to_datetime(v["from_date"])
        v["to_date"] = pd.to_datetime(v["to_date"])
    ctx.vehicles = v
    return ctx


def _pickle_path(upload_id: int) -> Path:
    folder = settings.upload_dir
    folder.mkdir(parents=True, exist_ok=True)
    return folder / f"upload-{upload_id}.pkl"


# ------------------------------------------------------------------ main flow

def handle_upload(db: Session, month: PayrollMonth, kind: str, filename: str,
                  content: bytes, username: str) -> FileUpload:
    if kind not in FILE_KINDS:
        raise UploadBlocked(f"Unknown file type '{kind}'")
    if month.status in ("approved", "locked"):
        raise UploadBlocked("This month is approved/locked - files can't be changed")
    latest = latest_uploads(month)
    for needed in NEEDS_FIRST[kind]:
        if needed not in latest or latest[needed].status != "imported":
            raise UploadBlocked(f"Upload the {needed} file first")

    raw = read_table(filename, content)
    raw.columns = [str(c).strip() for c in raw.columns]
    raw = raw.dropna(how="all")

    layout = kind
    if kind == "deliveries":
        _, missing_totals = match_columns(list(raw.columns), "deliveries_totals")
        layout = "deliveries_totals" if not missing_totals else "deliveries_orders"

    column_map, missing = match_columns(list(raw.columns), layout)
    upload = FileUpload(month_id=month.id, kind=kind, filename=filename, uploaded_by=username,
                        rows=len(raw), column_map=column_map, status="checking")
    db.add(upload)
    db.flush()

    if missing:
        nice = ", ".join(missing)
        upload.status = "has_errors"
        upload.error_count = len(missing)
        upload.issues = [{
            "id": 0, "level": "error", "column": None, "rows": [], "count": len(missing), "fix": None,
            "message": f"Missing column(s): {nice}. Columns found: {', '.join(raw.columns)}",
        }]
        upload.summary = {}
        db.commit()
        return upload

    renamed = raw[list(column_map)].rename(columns=column_map)
    return _check_and_store(db, month, upload, renamed, layout)


def handle_fixes(db: Session, month: PayrollMonth, upload: FileUpload, issue_ids: list[int],
                 username: str) -> FileUpload:
    path = _pickle_path(upload.id)
    if upload.status != "has_errors" or not path.exists():
        raise UploadBlocked("This file has no fixes waiting")
    fixes = [i["fix"] for i in upload.issues if i["id"] in issue_ids and i.get("fix")]
    if not fixes:
        raise UploadBlocked("Choose at least one suggested fix")

    fixed = apply_fixes(pd.read_pickle(path), fixes)
    new_upload = FileUpload(month_id=month.id, kind=upload.kind, uploaded_by=username,
                            filename=upload.filename if upload.filename.endswith("(fixed)")
                            else f"{upload.filename} (fixed)",
                            rows=len(fixed), column_map=upload.column_map, status="checking")
    db.add(new_upload)
    db.flush()
    layout = upload.kind
    if upload.kind == "deliveries":
        layout = "deliveries_totals" if {"prepaid", "cod"} <= set(fixed.columns) else "deliveries_orders"
    return _check_and_store(db, month, new_upload, fixed, layout)


def _check_and_store(db: Session, month: PayrollMonth, upload: FileUpload,
                     data: pd.DataFrame, layout: str) -> FileUpload:
    ctx = build_context(db, month)
    checkers = {
        "drivers": lambda df: check_drivers(df, ctx),
        "vehicles": lambda df: check_vehicles(df, ctx),
        "adjustments": lambda df: check_adjustments(df, ctx),
        "deliveries_orders": lambda df: check_deliveries(df, ctx, layout),
        "deliveries_totals": lambda df: check_deliveries(df, ctx, layout),
    }
    result: CheckResult = checkers[layout](data.copy())

    issues = sorted(result.issues, key=lambda i: (i["level"] != "error", -i["count"]))[:MAX_ISSUES_SAVED]
    for n, issue in enumerate(issues):
        issue["id"] = n
    upload.issues = issues
    upload.error_count = result.error_count
    upload.warning_count = result.warning_count
    upload.summary = result.summary

    if result.error_count:
        upload.status = "has_errors"
        data.to_pickle(_pickle_path(upload.id))   # keep it so suggested fixes can be applied
    else:
        upload.status = "imported"
        STORERS[upload.kind](db, month, result.df)
        clear_salaries(db, month.id)   # files changed -> old salaries are no longer valid

    latest = latest_uploads(month)
    latest[upload.kind] = upload
    all_ok = all(k in latest and latest[k].status == "imported" for k in FILE_KINDS)
    month.status = "ready" if all_ok else "draft"
    db.commit()
    db.refresh(upload)
    return upload


# ------------------------------------------------------------------ saving

def _d(value):
    return None if pd.isna(value) else pd.Timestamp(value).date()


def _s(value):
    return None if value is None or pd.isna(value) else str(value)


def store_drivers(db: Session, month: PayrollMonth, df: pd.DataFrame) -> None:
    stations = {s.code: s for s in db.scalars(select(Station))}
    for code, grp in df.groupby("station_code"):
        name = grp["station"].dropna().iloc[0] if grp["station"].notna().any() else code
        city = grp["city"].dropna().iloc[0] if grp["city"].notna().any() else ""
        if code in stations:
            stations[code].name, stations[code].city = name, city or stations[code].city
        else:
            stations[code] = Station(code=code, name=name, city=city)
            db.add(stations[code])
    db.flush()

    existing = {d.id: d for d in db.scalars(select(Driver))}
    for row in df.itertuples(index=False):
        d = existing.get(row.driver_id) or Driver(id=row.driver_id)
        d.name = row.name
        d.iqama_no = _s(row.iqama_no)
        d.station_id = stations[row.station_code].id
        d.joining_date = _d(row.joining_date)
        d.leaving_date = _d(row.leaving_date)
        d.payment_method = row.payment_method
        d.iban = _s(row.iban)
        d.phone = _s(row.phone)
        if row.driver_id not in existing:
            db.add(d)


def store_vehicles(db: Session, month: PayrollMonth, df: pd.DataFrame) -> None:
    db.execute(delete(VehicleAssignment).where(VehicleAssignment.month_id == month.id))
    db.execute(VehicleAssignment.__table__.insert(), [
        {"month_id": month.id, "plate_no": r.plate_no, "driver_id": r.driver_id,
         "from_date": _d(r.from_date), "to_date": _d(r.to_date)}
        for r in df.itertuples(index=False)
    ])


def store_deliveries(db: Session, month: PayrollMonth, df: pd.DataFrame) -> None:
    db.execute(delete(DeliveryDay).where(DeliveryDay.month_id == month.id))
    if "order_type" in df:
        counts = (df.groupby(["driver_id", "date", "order_type"]).size()
                    .unstack(fill_value=0).reset_index())
        for col in ("Prepaid", "COD"):
            if col not in counts:
                counts[col] = 0
        rows = [{"month_id": month.id, "driver_id": r.driver_id, "day": _d(r.date),
                 "prepaid": int(r.Prepaid), "cod": int(r.COD)} for r in counts.itertuples(index=False)]
    else:
        rows = [{"month_id": month.id, "driver_id": r.driver_id, "day": None,
                 "prepaid": int(r.prepaid), "cod": int(r.cod)} for r in df.itertuples(index=False)]
    if rows:
        db.execute(DeliveryDay.__table__.insert(), rows)


def store_adjustments(db: Session, month: PayrollMonth, df: pd.DataFrame) -> None:
    db.execute(delete(Adjustment).where(Adjustment.month_id == month.id))
    rows = [{
        "month_id": month.id, "driver_id": r.driver_id, "plate_no": _s(r.plate_no),
        "matched_by_plate": bool(r.matched_by_plate), "kind": r.kind, "type": r.type,
        "amount": float(r.amount), "day": _d(r.date), "reference": _s(r.reference), "note": _s(r.note),
    } for r in df.itertuples(index=False)]
    if rows:
        db.execute(Adjustment.__table__.insert(), rows)


STORERS = {
    "drivers": store_drivers,
    "vehicles": store_vehicles,
    "deliveries": store_deliveries,
    "adjustments": store_adjustments,
}

__all__ = ["FILE_FIELDS", "UploadBlocked", "handle_upload", "handle_fixes", "latest_uploads", "month_range"]
