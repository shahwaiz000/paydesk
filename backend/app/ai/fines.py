"""Read traffic fine documents (PDF or photo) with Gemini, then find the driver by plate + date.

AI only READS the document. Matching to the driver is done by PayDesk's own rules
(vehicle assignment table), and the accountant confirms before anything is added.
"""

from __future__ import annotations

import re
from datetime import date

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..models import Adjustment, Driver, PayrollMonth, VehicleAssignment
from ..payroll.engine import month_range
from .gemini import AIError, generate_json

MIME = {".pdf": "application/pdf", ".png": "image/png", ".jpg": "image/jpeg",
        ".jpeg": "image/jpeg", ".webp": "image/webp"}

PROMPT = """This is a traffic violation notice for a company delivery vehicle in Saudi Arabia.
Read it and return JSON with exactly these keys:
  "fine_number": the violation / notice / reference number (string),
  "plate_no": the vehicle plate exactly as written (string),
  "date": the date of the violation as YYYY-MM-DD (convert Hijri or other formats if needed),
  "amount": the fine amount in SAR (number only),
  "violation": short description of the violation in English (max 6 words),
  "confidence": "high", "medium" or "low" - how sure you are about plate, date and amount.
If a value is not on the document, use null. Do not guess."""


def plate_key(plate: str | None) -> str:
    """'1234 ABC', 'ABC-1234' and 'abc1234' all become '1234ABC'."""
    if not plate:
        return ""
    text = str(plate).upper()
    return "".join(re.findall(r"\d", text)) + "".join(re.findall(r"[A-Z]", text))


def _pdf_text(data: bytes) -> str:
    try:
        import pymupdf
    except ImportError:  # pragma: no cover
        return ""
    with pymupdf.open(stream=data, filetype="pdf") as doc:
        return "\n".join(page.get_text() for page in doc)[:6000]


def _pdf_first_page_png(data: bytes) -> bytes:
    import pymupdf
    with pymupdf.open(stream=data, filetype="pdf") as doc:
        return doc[0].get_pixmap(dpi=150).tobytes("png")


def read_document(filename: str, data: bytes) -> dict:
    ext = "." + filename.lower().rsplit(".", 1)[-1] if "." in filename else ""
    if ext not in MIME:
        raise AIError("Only PDF, PNG, JPG or WEBP files")
    if ext == ".pdf":
        text = _pdf_text(data)
        if len(text.strip()) > 40:     # digital PDF: send the text (faster, cheaper)
            return generate_json(PROMPT + "\n\nDocument text:\n" + text)
        return generate_json(PROMPT, files=[(_pdf_first_page_png(data), "image/png")])  # scanned PDF
    return generate_json(PROMPT, files=[(data, MIME[ext])])


def _to_date(value) -> date | None:
    try:
        return date.fromisoformat(str(value)[:10])
    except (TypeError, ValueError):
        return None


def _to_amount(value) -> float | None:
    try:
        amount = float(str(value).replace(",", "").replace("SAR", "").strip())
        return amount if amount > 0 else None
    except (TypeError, ValueError):
        return None


def match_fine(db: Session, month: PayrollMonth, fine: dict) -> dict:
    """Clean the AI's answer and find who drove the vehicle that day."""
    start, end = month_range(month.period)
    day = _to_date(fine.get("date"))
    amount = _to_amount(fine.get("amount"))
    number = (str(fine.get("fine_number")).strip() if fine.get("fine_number") else None)
    plate = (str(fine.get("plate_no")).strip().upper() if fine.get("plate_no") else None)

    result = {
        "fine_number": number, "plate_no": plate, "date": day.isoformat() if day else None,
        "amount": amount, "violation": fine.get("violation"), "confidence": fine.get("confidence"),
        "driver": None, "problem": None, "duplicate": False,
    }
    if not plate or not day or not amount:
        missing = [n for n, v in (("plate", plate), ("date", day), ("amount", amount)) if not v]
        result["problem"] = f"Couldn't read the {', '.join(missing)} - please check the document"
        return result
    if not (start <= day <= end):
        result["problem"] = f"Fine date {day} is not in this payroll month"
        return result

    key = plate_key(plate)
    hits = [v for v in db.scalars(select(VehicleAssignment).where(VehicleAssignment.month_id == month.id))
            if plate_key(v.plate_no) == key and v.from_date <= day <= v.to_date]
    if len(hits) != 1:
        result["problem"] = ("No driver had this plate on that day" if not hits
                             else "More than one driver had this plate that day")
        return result

    driver = db.get(Driver, hits[0].driver_id)
    result["plate_no"] = hits[0].plate_no
    result["driver"] = {"id": driver.id, "name": driver.name, "station": driver.station.name} if driver else None
    if number and db.scalar(select(Adjustment.id).where(Adjustment.month_id == month.id,
                                                        Adjustment.reference == number)):
        result["duplicate"] = True
        result["problem"] = f"Fine {number} is already on this month's deductions"
    return result
