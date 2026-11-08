"""AI endpoints (Gemini). Everything here is optional - PayDesk works without a key."""

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from ..ai.gemini import AIError, is_enabled
from ..ai.review import explain_unusual, month_summary
from ..database import get_db
from ..deps import get_current_user, require_roles
from ..models import ACCOUNTANT, FINANCE_MANAGER, User
from .months import get_month

router = APIRouter(prefix="/api", tags=["ai"])
can_review = require_roles(ACCOUNTANT, FINANCE_MANAGER)


@router.get("/ai/status")
def ai_status(_: User = Depends(get_current_user)):
    return {"enabled": is_enabled()}


@router.post("/months/{month_id}/ai/explain")
def ai_explain(month_id: int, db: Session = Depends(get_db), _: User = Depends(can_review)):
    month = get_month(db, month_id)
    try:
        return {"explained": explain_unusual(db, month)}
    except AIError as e:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(e))


@router.post("/months/{month_id}/ai/summary")
def ai_summary(month_id: int, db: Session = Depends(get_db), _: User = Depends(can_review)):
    month = get_month(db, month_id)
    try:
        return {"summary": month_summary(db, month)}
    except AIError as e:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(e))
