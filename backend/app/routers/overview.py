"""Home page numbers - each role sees only what it is allowed to see."""

from fastapi import APIRouter, Depends
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..database import get_db
from ..deps import get_current_user
from ..models import ACCOUNTANT, CASHIER, DRIVER, FINANCE_MANAGER, Driver, Station, User

router = APIRouter(prefix="/api", tags=["overview"])


def _count(db: Session, stmt) -> int:
    return db.scalar(stmt) or 0


@router.get("/overview")
def overview(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    if user.role in (ACCOUNTANT, FINANCE_MANAGER):
        return {
            "role": user.role,
            "stations": _count(db, select(func.count()).select_from(Station)),
            "cities": _count(db, select(func.count(func.distinct(Station.city)))),
            "drivers": _count(db, select(func.count()).select_from(Driver)),
            "cash_drivers": _count(db, select(func.count()).where(Driver.payment_method == "Cash")),
            "bank_drivers": _count(db, select(func.count()).where(Driver.payment_method == "Bank")),
        }

    if user.role == CASHIER and user.station:
        st = user.station
        return {
            "role": user.role,
            "station": st.name,
            "station_code": st.code,
            "drivers": _count(db, select(func.count()).where(Driver.station_id == st.id)),
            "cash_drivers": _count(
                db,
                select(func.count()).where(Driver.station_id == st.id, Driver.payment_method == "Cash"),
            ),
        }

    if user.role == DRIVER and user.driver:
        d = user.driver
        return {
            "role": user.role,
            "driver_id": d.id,
            "name": d.name,
            "station": d.station.name,
            "joining_date": d.joining_date.isoformat(),
            "payment_method": d.payment_method,
            "iban_last4": d.iban[-4:] if d.iban else None,
        }

    return {"role": user.role}
