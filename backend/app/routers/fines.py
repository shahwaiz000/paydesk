"""Traffic fines from documents (Stage 6): read with AI -> accountant confirms -> added as deductions."""

from concurrent.futures import ThreadPoolExecutor
from datetime import date

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile, status
from pydantic import BaseModel
from sqlalchemy.orm import Session

from ..ai.fines import match_fine, read_document
from ..ai.gemini import AIError
from ..database import get_db
from ..deps import require_roles
from ..models import ACCOUNTANT, Adjustment, User
from ..payroll.engine import clear_salaries
from .months import get_month, month_out

router = APIRouter(prefix="/api/months/{month_id}/fines", tags=["fines"])
MAX_FILES = 10
MAX_MB = 10


class FineIn(BaseModel):
    filename: str
    fine_number: str | None = None
    plate_no: str
    date: str
    amount: float
    violation: str | None = None
    driver_id: str


class AddFines(BaseModel):
    fines: list[FineIn]


def _editable(month):
    if month.status in ("approved", "locked"):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "This month is approved/locked")
    if month.status == "draft":
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Import all 4 month files first")


@router.post("/read")
def read_fines(month_id: int, files: list[UploadFile] = File(...),
               db: Session = Depends(get_db), _: User = Depends(require_roles(ACCOUNTANT))):
    # Plain "def" (not async): FastAPI runs it in a background thread, so a slow AI call
    # never freezes the rest of PayDesk for other users.
    month = get_month(db, month_id)
    _editable(month)
    if len(files) > MAX_FILES:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, f"Up to {MAX_FILES} documents at a time")

    docs = []
    for f in files:
        data = f.file.read()
        docs.append((f.filename or "document", data))

    def read_one(doc):
        name, data = doc
        if len(data) > MAX_MB * 1024 * 1024:
            return name, None, f"Bigger than {MAX_MB} MB"
        try:
            fine = read_document(name, data)
            if not isinstance(fine, dict):
                return name, None, "AI answer was not in the expected format"
            return name, fine, None
        except AIError as e:
            return name, None, str(e)

    # Read up to 3 documents at the same time (6 documents ~ 2 rounds instead of 6)
    with ThreadPoolExecutor(max_workers=3) as pool:
        read = list(pool.map(read_one, docs))

    results = []
    for name, fine, error in read:
        if error:
            results.append({"filename": name, "error": error})
        else:
            results.append({"filename": name, "error": None, **match_fine(db, month, fine)})
    return {"results": results}


@router.post("/add")
def add_fines(month_id: int, body: AddFines, db: Session = Depends(get_db),
              user: User = Depends(require_roles(ACCOUNTANT))):
    month = get_month(db, month_id)
    _editable(month)
    added, skipped = 0, []
    for fine in body.fines:
        # Never trust the browser: check the match again on the server
        check = match_fine(db, month, fine.model_dump())
        if check["problem"] or not check["driver"] or check["driver"]["id"] != fine.driver_id:
            skipped.append(f"{fine.filename}: {check['problem'] or 'driver does not match'}")
            continue
        db.add(Adjustment(
            month_id=month.id, driver_id=fine.driver_id, plate_no=check["plate_no"], matched_by_plate=True,
            kind="Deduction", type="Traffic fine", amount=check["amount"],
            day=date.fromisoformat(check["date"]),
            reference=check["fine_number"], source="ai_document",
            note=f"{(fine.violation or 'Traffic violation')[:80]} - read by AI from {fine.filename[:60]}",
        ))
        db.flush()
        added += 1
    if added:
        clear_salaries(db, month.id)       # deductions changed -> salaries must be recalculated
        month.status = "ready"
    db.commit()
    db.refresh(month)
    return {"added": added, "skipped": skipped, "month": month_out(month)}
