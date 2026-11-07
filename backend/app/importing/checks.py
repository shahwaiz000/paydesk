"""Checks for each uploaded file.

Every problem becomes an "issue":
    level    - "error" (must fix before import) or "warning" (allowed, but look at it)
    message  - plain English
    rows     - Excel row numbers (header is row 1)
    fix      - an optional one-click suggested fix

Big files (300,000 deliveries) are checked column-by-column, and the same
problem is reported once with a count - not 5,000 times.
"""

from __future__ import annotations

import difflib
from dataclasses import dataclass, field
from datetime import date

import pandas as pd

PAYMENT_METHODS = ["Cash", "Bank"]
ORDER_TYPES = ["Prepaid", "COD"]
ADJUSTMENT_TYPES = ["Traffic fine", "Lost parcel", "Shortage", "Advance", "Other", "Bonus"]
MAX_ROWS_LISTED = 20


@dataclass
class CheckContext:
    month_start: date
    month_end: date
    known_driver_ids: set[str] = field(default_factory=set)
    driver_periods: dict[str, tuple[date, date]] = field(default_factory=dict)  # active this month
    vehicles: pd.DataFrame | None = None   # plate_no, driver_id, from_date, to_date


@dataclass
class CheckResult:
    df: pd.DataFrame
    issues: list[dict]
    summary: dict

    @property
    def error_count(self) -> int:
        return sum(i["count"] for i in self.issues if i["level"] == "error")

    @property
    def warning_count(self) -> int:
        return sum(i["count"] for i in self.issues if i["level"] == "warning")


# ------------------------------------------------------------------ helpers

def excel_rows(index) -> list[int]:
    """DataFrame index -> Excel row numbers (row 1 is the header)."""
    return [int(i) + 2 for i in list(index)[:MAX_ROWS_LISTED]]


def make_issue(level, message, index=(), column=None, fix=None) -> dict:
    index = list(index)
    return {
        "level": level,
        "message": message,
        "column": column,
        "rows": excel_rows(index),
        "count": max(1, len(index)),
        "fix": fix,
    }


def replace_fix(column: str, old, new, index=None, why: str = "") -> dict:
    return {
        "action": "replace",
        "column": column,
        "from": old,
        "to": new,
        "index": None if index is None else [int(i) for i in index],
        "label": f"Change '{old}' to '{new}'" + (f" ({why})" if why else ""),
    }


def drop_fix(index, label: str) -> dict:
    return {"action": "drop_rows", "index": [int(i) for i in index], "label": label}


def clean_text(series: pd.Series) -> pd.Series:
    s = series.astype("string").str.strip()
    return s.mask(s == "", pd.NA)


def parse_dates(series: pd.Series) -> pd.Series:
    """ISO dates (2026-10-05) first, then day-first (05/10/2026)."""
    s = clean_text(series)
    parsed = pd.to_datetime(s, errors="coerce", format="ISO8601")
    retry = parsed.isna() & s.notna()
    if retry.any():
        parsed[retry] = pd.to_datetime(s[retry], errors="coerce", format="%d/%m/%Y")
    return parsed.dt.normalize()


def pick(value: str, options: list[str], cutoff: float = 0.6) -> tuple[str | None, bool]:
    """Returns (best option, exact_ignoring_case)."""
    for opt in options:
        if str(value).strip().lower() == opt.lower():
            return opt, True
    close = difflib.get_close_matches(str(value).strip().lower(), [o.lower() for o in options], n=1, cutoff=cutoff)
    if close:
        return next(o for o in options if o.lower() == close[0]), False
    return None, False


def suggest_driver_id(bad: str, known: set[str]) -> str | None:
    """Catches typing mistakes: swapped digits (D10032 -> D10023) or missing letter (10023 -> D10023)."""
    candidates = set()
    for i in range(len(bad) - 1):
        swapped = bad[:i] + bad[i + 1] + bad[i] + bad[i + 2:]
        if swapped in known:
            candidates.add(swapped)
    if not bad.startswith("D") and "D" + bad in known:
        candidates.add("D" + bad)
    return candidates.pop() if len(candidates) == 1 else None


def iban_is_valid(iban: str) -> bool:
    if len(iban) != 24 or not iban.startswith("SA") or not iban[2:].isdigit():
        return False
    rearranged = iban[4:] + iban[:4]
    digits = "".join(str(int(c, 36)) for c in rearranged)
    return int(digits) % 97 == 1


def check_unknown_drivers(df, ctx: CheckContext, issues: list, required: bool = True) -> None:
    ids = df["driver_id"]
    unknown = ids.notna() & ~ids.isin(ctx.known_driver_ids)
    for bad, idx in df[unknown].groupby("driver_id").groups.items():
        guess = suggest_driver_id(bad, ctx.known_driver_ids)
        issues.append(make_issue(
            "error",
            f"Driver '{bad}' is not in the driver list"
            + (f" - did you mean {guess}?" if guess else ""),
            idx, "driver_id",
            replace_fix("driver_id", bad, guess,
                        why="missing 'D'" if guess == "D" + bad else "digits swapped") if guess else None,
        ))
    if required:
        missing = df.index[ids.isna()]
        if len(missing):
            issues.append(make_issue("error", "Driver ID is empty", missing, "driver_id"))


def check_choice(df, column, options, issues, label) -> None:
    """Value must be one of the options. Case is fixed silently; typos get a suggestion."""
    values = df[column]
    for value, idx in df[values.notna()].groupby(column).groups.items():
        best, exact = pick(value, options)
        if exact:
            df.loc[idx, column] = best
        elif best:
            issues.append(make_issue(
                "error", f"{label} '{value}' is not valid - did you mean '{best}'?",
                idx, column, replace_fix(column, value, best),
            ))
        else:
            issues.append(make_issue(
                "error", f"{label} '{value}' is not valid (allowed: {', '.join(options)})", idx, column,
            ))
    missing = df.index[values.isna()]
    if len(missing):
        issues.append(make_issue("error", f"{label} is empty", missing, column))


def check_dates(df, column, issues, label, required=True) -> None:
    raw = clean_text(df[column])
    df[column] = parse_dates(df[column])
    bad = df.index[raw.notna() & df[column].isna()]
    if len(bad):
        issues.append(make_issue("error", f"{label} is not a valid date (use 2026-10-05 or 05/10/2026)", bad, column))
    if required:
        empty = df.index[raw.isna()]
        if len(empty):
            issues.append(make_issue("error", f"{label} is empty", empty, column))


def duplicate_rows_issue(df, key, issues, label) -> None:
    dup_mask = df[key].notna() & df.duplicated(subset=[key], keep="first")
    if not dup_mask.any():
        return
    exact = df.index[dup_mask & df.duplicated(keep="first")]
    different = df.index[dup_mask & ~df.duplicated(keep="first")]
    if len(exact):
        issues.append(make_issue(
            "error", f"{label} appears twice (exact copy of an earlier row)", exact, key,
            drop_fix(exact, f"Remove {len(exact)} duplicate row(s)"),
        ))
    if len(different):
        issues.append(make_issue(
            "error", f"Same {label} used twice with different details - check which one is right",
            different, key,
        ))


# ------------------------------------------------------------------ File 1: drivers

def check_drivers(df: pd.DataFrame, ctx: CheckContext) -> CheckResult:
    issues: list[dict] = []
    for col in df.columns:
        df[col] = clean_text(df[col])
    df["driver_id"] = df["driver_id"].str.upper()
    if "iban" in df:
        df["iban"] = df["iban"].str.replace(" ", "", regex=False).str.upper()
    for col in ("station", "city", "iqama_no", "leaving_date", "iban", "phone"):
        if col not in df:
            df[col] = pd.NA

    missing_id = df.index[df["driver_id"].isna()]
    if len(missing_id):
        issues.append(make_issue("error", "Driver ID is empty", missing_id, "driver_id"))
    duplicate_rows_issue(df, "driver_id", issues, "Driver ID")

    for col, label in (("name", "Name"), ("station_code", "Station code")):
        empty = df.index[df[col].isna()]
        if len(empty):
            issues.append(make_issue("error", f"{label} is empty", empty, col))
    if df["station"].isna().any() and df["station"].notna().any():
        issues.append(make_issue("warning", "Station name is empty (station code will be used)",
                                 df.index[df["station"].isna()], "station"))

    check_choice(df, "payment_method", PAYMENT_METHODS, issues, "Payment method")
    check_dates(df, "joining_date", issues, "Joining date")
    check_dates(df, "leaving_date", issues, "Leaving date", required=False)

    both = df["joining_date"].notna() & df["leaving_date"].notna()
    backwards = df.index[both & (df["leaving_date"] < df["joining_date"])]
    if len(backwards):
        issues.append(make_issue("error", "Leaving date is before joining date", backwards, "leaving_date"))

    bank = df["payment_method"] == "Bank"
    no_iban = df.index[bank & df["iban"].isna()]
    if len(no_iban):
        issues.append(make_issue("error", "Bank driver has no IBAN - salary can't be transferred", no_iban, "iban"))
    has_iban = bank & df["iban"].notna()
    bad_iban = df.index[has_iban & ~df["iban"].fillna("").map(iban_is_valid)]
    if len(bad_iban):
        issues.append(make_issue("error", "IBAN is not a valid Saudi IBAN (SA + 22 digits)", bad_iban, "iban"))

    # Station code used with two different names
    named = df[df["station_code"].notna() & df["station"].notna()]
    for code, names in named.groupby("station_code")["station"].unique().items():
        if len(names) > 1:
            idx = named.index[named["station_code"] == code]
            issues.append(make_issue("warning", f"Station {code} has different names: {', '.join(names)}",
                                     idx, "station"))

    ms, me = pd.Timestamp(ctx.month_start), pd.Timestamp(ctx.month_end)
    future = df.index[df["joining_date"] > me]
    if len(future):
        issues.append(make_issue("warning", "Joins after this month - no salary this month", future, "joining_date"))
    gone = df.index[df["leaving_date"] < ms]
    if len(gone):
        issues.append(make_issue("warning", "Left before this month - no salary this month", gone, "leaving_date"))

    jd, ld = df["joining_date"], df["leaving_date"]
    summary = {
        "drivers": int(df["driver_id"].nunique()),
        "stations": int(df["station_code"].nunique()),
        "cash_drivers": int((df["payment_method"] == "Cash").sum()),
        "bank_drivers": int((df["payment_method"] == "Bank").sum()),
        "joiners_this_month": int(((jd >= ms) & (jd <= me)).sum()),
        "leavers_this_month": int(((ld >= ms) & (ld <= me)).sum()),
    }
    return CheckResult(df, issues, summary)


# ------------------------------------------------------------------ File 4: vehicles

def check_vehicles(df: pd.DataFrame, ctx: CheckContext) -> CheckResult:
    issues: list[dict] = []
    for col in df.columns:
        df[col] = clean_text(df[col])
    df["driver_id"] = df["driver_id"].str.upper()
    df["plate_no"] = df["plate_no"].str.upper().str.replace(r"\s+", " ", regex=True)

    empty_plate = df.index[df["plate_no"].isna()]
    if len(empty_plate):
        issues.append(make_issue("error", "Plate number is empty", empty_plate, "plate_no"))
    check_unknown_drivers(df, ctx, issues)
    check_dates(df, "from_date", issues, "From date")
    check_dates(df, "to_date", issues, "To date")

    ok = df["from_date"].notna() & df["to_date"].notna()
    backwards = df.index[ok & (df["to_date"] < df["from_date"])]
    if len(backwards):
        issues.append(make_issue("error", "'To date' is before 'from date'", backwards, "to_date"))

    # Same plate given to two drivers on the same day
    valid = df[ok & df["plate_no"].notna()].sort_values(["plate_no", "from_date"])
    overlap_idx = []
    for _, grp in valid.groupby("plate_no"):
        prev_to, prev_driver = None, None
        for idx, row in grp.iterrows():
            if prev_to is not None and row["from_date"] <= prev_to and row["driver_id"] != prev_driver:
                overlap_idx.append(idx)
            prev_to, prev_driver = row["to_date"], row["driver_id"]
    if overlap_idx:
        issues.append(make_issue("error", "Same vehicle given to two drivers on the same day",
                                 overlap_idx, "plate_no"))

    summary = {
        "assignments": len(df),
        "vehicles": int(df["plate_no"].nunique()),
        "drivers_with_vehicle": int(df["driver_id"].nunique()),
        "drivers_who_changed_vehicle": int((df.groupby("driver_id")["plate_no"].nunique() > 1).sum()),
    }
    return CheckResult(df, issues, summary)


# ------------------------------------------------------------------ File 2: deliveries

def check_deliveries(df: pd.DataFrame, ctx: CheckContext, layout: str) -> CheckResult:
    issues: list[dict] = []
    df["driver_id"] = clean_text(df["driver_id"]).str.upper()
    check_unknown_drivers(df, ctx, issues)

    if layout == "deliveries_totals":
        for col in ("prepaid", "cod"):
            nums = pd.to_numeric(clean_text(df[col]), errors="coerce")
            bad = df.index[nums.isna() | (nums < 0)]
            if len(bad):
                issues.append(make_issue("error", f"'{col}' must be a number 0 or more", bad, col))
            df[col] = nums.fillna(0).astype(int)
        duplicate_rows_issue(df, "driver_id", issues, "Driver ID")
        summary = {
            "layout": "totals per driver",
            "drivers_with_deliveries": int(df["driver_id"].nunique()),
            "prepaid": int(df["prepaid"].sum()),
            "cod": int(df["cod"].sum()),
        }
        _zero_delivery_warning(df, ctx, issues)
        return CheckResult(df, issues, summary)

    # One row per order
    df["order_type"] = clean_text(df["order_type"])
    check_choice(df, "order_type", ORDER_TYPES, issues, "Order type")

    raw_date = clean_text(df["date"])
    df["date"] = parse_dates(df["date"])
    bad = raw_date.notna() & df["date"].isna()
    if bad.any():
        bad_values = raw_date[bad]
        for value, idx in bad_values.groupby(bad_values).groups.items():
            issues.append(make_issue("error", f"'{value}' is not a valid date", idx, "date"))
    empty = df.index[raw_date.isna()]
    if len(empty):
        issues.append(make_issue("error", "Delivery date is empty", empty, "date"))

    dated = df["date"].notna()
    ms, me = pd.Timestamp(ctx.month_start), pd.Timestamp(ctx.month_end)
    outside = df[(df["date"] < ms) | (df["date"] > me)]
    for day, idx in outside.groupby("date").groups.items():
        issues.append(make_issue("error", f"Delivery on {day.date()} is not in this payroll month", idx, "date"))

    if "tracking_no" in df:
        df["tracking_no"] = clean_text(df["tracking_no"])
        duplicate_rows_issue(df, "tracking_no", issues, "Tracking number")

    # Deliveries on days the driver was not employed
    if ctx.driver_periods:
        start = pd.to_datetime(df["driver_id"].map(lambda d: ctx.driver_periods.get(d, (None, None))[0]))
        end = pd.to_datetime(df["driver_id"].map(lambda d: ctx.driver_periods.get(d, (None, None))[1]))
        off = df[(df["date"] < start) | (df["date"] > end)]
        for driver, idx in off.groupby("driver_id").groups.items():
            s, e = ctx.driver_periods[driver]
            issues.append(make_issue(
                "warning", f"{driver} has deliveries outside his working days ({s} to {e})", idx, "date",
            ))

    _zero_delivery_warning(df, ctx, issues)
    summary = {
        "layout": "one row per order",
        "orders": len(df),
        "drivers_with_deliveries": int(df["driver_id"].nunique()),
        "prepaid": int((df["order_type"] == "Prepaid").sum()),
        "cod": int((df["order_type"] == "COD").sum()),
    }
    return CheckResult(df, issues, summary)


def _zero_delivery_warning(df, ctx, issues) -> None:
    active = set(ctx.driver_periods)
    none = sorted(active - set(df["driver_id"].dropna()))
    if none:
        issue = make_issue("warning", f"{len(none)} active driver(s) have zero deliveries "
                                      f"(e.g. {', '.join(none[:5])}) - absent or missing from export?")
        issue["count"] = len(none)
        issues.append(issue)


# ------------------------------------------------------------------ File 3: adjustments

def check_adjustments(df: pd.DataFrame, ctx: CheckContext) -> CheckResult:
    issues: list[dict] = []
    for col in ("driver_id", "plate_no", "kind", "date", "reference", "note"):
        if col not in df:
            df[col] = pd.NA
    for col in df.columns:
        df[col] = clean_text(df[col])
    df["driver_id"] = df["driver_id"].str.upper()
    df["plate_no"] = df["plate_no"].str.upper().str.replace(r"\s+", " ", regex=True)
    df["matched_by_plate"] = False

    check_choice(df, "type", ADJUSTMENT_TYPES, issues, "Type")
    df["kind"] = df["type"].map(lambda t: "Bonus" if t == "Bonus" else "Deduction")

    amounts = pd.to_numeric(df["amount"], errors="coerce")
    bad_amount = df.index[amounts.isna() | (amounts <= 0)]
    if len(bad_amount):
        issues.append(make_issue("error", "Amount must be a number above 0", bad_amount, "amount"))
    df["amount"] = amounts

    other_no_note = df.index[(df["type"] == "Other") & df["note"].isna()]
    if len(other_no_note):
        issues.append(make_issue("error", "Type 'Other' needs a note explaining the reason", other_no_note, "note"))
    no_ref = df.index[df["type"].isin(["Traffic fine", "Lost parcel"]) & df["reference"].isna()]
    if len(no_ref):
        issues.append(make_issue("warning", "No reference (fine number / tracking number) - "
                                            "the driver won't know what this is for", no_ref, "reference"))

    raw_date = df["date"].copy()
    df["date"] = parse_dates(df["date"])
    bad_date = df.index[raw_date.notna() & df["date"].isna()]
    if len(bad_date):
        issues.append(make_issue("error", "Date is not a valid date", bad_date, "date"))
    ms, me = pd.Timestamp(ctx.month_start), pd.Timestamp(ctx.month_end)
    outside = df.index[(df["date"] < ms) | (df["date"] > me)]
    if len(outside):
        issues.append(make_issue("warning", "Date is outside this payroll month", outside, "date"))

    nobody = df.index[df["driver_id"].isna() & df["plate_no"].isna()]
    if len(nobody):
        issues.append(make_issue("error", "Needs a driver ID or a plate number", nobody, "driver_id"))

    check_unknown_drivers(df, ctx, issues, required=False)

    # Plate only (traffic fines) -> find who drove that vehicle on that day
    plate_only = df[df["driver_id"].isna() & df["plate_no"].notna()]
    if len(plate_only):
        if ctx.vehicles is None or ctx.vehicles.empty:
            issues.append(make_issue("error", "Upload the vehicle file first - needed to match fines by plate",
                                     plate_only.index, "plate_no"))
        else:
            no_date = plate_only.index[plate_only["date"].isna()]
            if len(no_date):
                issues.append(make_issue("error", "Plate-only lines need a date to find the driver", no_date, "date"))
            not_found = []
            for idx, row in plate_only[plate_only["date"].notna()].iterrows():
                v = ctx.vehicles
                hit = v[(v["plate_no"] == row["plate_no"]) & (v["from_date"] <= row["date"]) & (v["to_date"] >= row["date"])]
                if len(hit) == 1:
                    df.at[idx, "driver_id"] = hit.iloc[0]["driver_id"]
                    df.at[idx, "matched_by_plate"] = True
                else:
                    not_found.append(idx)
            if not_found:
                issues.append(make_issue("error", "No driver had this plate on that date", not_found, "plate_no"))

    deductions = df[df["kind"] == "Deduction"]
    summary = {
        "lines": len(df),
        "deductions_total": round(float(deductions["amount"].sum(skipna=True)), 2),
        "bonuses_total": round(float(df.loc[df["kind"] == "Bonus", "amount"].sum(skipna=True)), 2),
        "by_type": {str(k): int(v) for k, v in df["type"].value_counts().items()},
        "fines_matched_by_plate": int(df["matched_by_plate"].sum()),
        "drivers_affected": int(df["driver_id"].nunique()),
    }
    return CheckResult(df, issues, summary)


# ------------------------------------------------------------------ fixes

def apply_fixes(df: pd.DataFrame, fixes: list[dict]) -> pd.DataFrame:
    df = df.copy()
    drop: list[int] = []
    for fix in fixes:
        if fix["action"] == "replace":
            col = fix["column"]
            target = df.index if fix.get("index") is None else pd.Index(fix["index"]).intersection(df.index)
            mask = df.loc[target, col].astype("string").str.strip().str.lower() == str(fix["from"]).lower()
            df.loc[mask[mask].index, col] = fix["to"]
        elif fix["action"] == "drop_rows":
            drop.extend(fix["index"])
    if drop:
        df = df.drop(index=[i for i in drop if i in df.index])
    return df
