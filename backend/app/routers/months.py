"""Payroll months and file uploads (Stage 3)."""

import re

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile, status
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..database import get_db
from ..deps import require_roles
from ..importing.service import UploadBlocked, handle_fixes, handle_upload, latest_uploads
from ..models import ACCOUNTANT, FILE_KINDS, FINANCE_MANAGER, FileUpload, PayrollMonth, User

router = APIRouter(prefix="/api/months", tags=["months"])
can_view = require_roles(ACCOUNTANT, FINANCE_MANAGER)
can_edit = require_roles(ACCOUNTANT)

MAX_UPLOAD_MB = 50


class NewMonth(BaseModel):
    period: str  # "2026-11"


class FixRequest(BaseModel):
    issue_ids: list[int]


def upload_out(up: FileUpload | None) -> dict | None:
    if up is None:
        return None
    return {
        "id": up.id, "kind": up.kind, "filename": up.filename, "status": up.status,
        "uploaded_by": up.uploaded_by, "uploaded_at": up.uploaded_at.isoformat() if up.uploaded_at else None,
        "rows": up.rows, "error_count": up.error_count, "warning_count": up.warning_count,
        "column_map": up.column_map, "issues": up.issues, "summary": up.summary,
    }


def month_out(month: PayrollMonth, with_files: bool = True) -> dict:
    latest = latest_uploads(month)
    data = {
        "id": month.id, "period": month.period, "status": month.status,
        "returned_note": month.returned_note,
        "files_imported": sum(1 for k in FILE_KINDS if k in latest and latest[k].status == "imported"),
    }
    if with_files:
        data["files"] = {k: upload_out(latest.get(k)) for k in FILE_KINDS}
    return data


def get_month(db: Session, month_id: int) -> PayrollMonth:
    month = db.get(PayrollMonth, month_id)
    if month is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Month not found")
    return month


@router.get("")
def list_months(db: Session = Depends(get_db), _: User = Depends(can_view)):
    months = db.scalars(select(PayrollMonth).order_by(PayrollMonth.period.desc()))
    return [month_out(m, with_files=False) for m in months]


@router.post("")
def create_month(body: NewMonth, db: Session = Depends(get_db), _: User = Depends(can_edit)):
    if not re.fullmatch(r"20\d\d-(0[1-9]|1[0-2])", body.period):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Month must look like 2026-11")
    if db.scalar(select(PayrollMonth).where(PayrollMonth.period == body.period)):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, f"{body.period} already exists")
    month = PayrollMonth(period=body.period)
    db.add(month)
    db.commit()
    return month_out(month)


@router.get("/{month_id}")
def month_detail(month_id: int, db: Session = Depends(get_db), _: User = Depends(can_view)):
    return month_out(get_month(db, month_id))


@router.post("/{month_id}/upload/{kind}")
async def upload_file(month_id: int, kind: str, file: UploadFile = File(...),
                      db: Session = Depends(get_db), user: User = Depends(can_edit)):
    month = get_month(db, month_id)
    content = await file.read()
    if len(content) > MAX_UPLOAD_MB * 1024 * 1024:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, f"File is bigger than {MAX_UPLOAD_MB} MB")
    try:
        handle_upload(db, month, kind, file.filename or "file", content, user.username)
    except UploadBlocked as e:
        db.rollback()
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(e))
    db.refresh(month)
    return month_out(month)


@router.post("/{month_id}/uploads/{upload_id}/fix")
def fix_upload(month_id: int, upload_id: int, body: FixRequest,
               db: Session = Depends(get_db), user: User = Depends(can_edit)):
    month = get_month(db, month_id)
    upload = db.get(FileUpload, upload_id)
    if upload is None or upload.month_id != month.id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Upload not found")
    try:
        handle_fixes(db, month, upload, body.issue_ids, user.username)
    except UploadBlocked as e:
        db.rollback()
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(e))
    db.refresh(month)
    return month_out(month)
