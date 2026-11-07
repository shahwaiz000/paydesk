"""Shared checks: who is logged in, and are they allowed here?"""

import jwt
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session

from .database import get_db
from .models import User
from .security import decode_token

bearer = HTTPBearer(auto_error=False)


def get_current_user(
    creds: HTTPAuthorizationCredentials | None = Depends(bearer),
    db: Session = Depends(get_db),
) -> User:
    not_logged_in = HTTPException(status.HTTP_401_UNAUTHORIZED, "Please log in again")
    if creds is None:
        raise not_logged_in
    try:
        payload = decode_token(creds.credentials)
    except jwt.PyJWTError:
        raise not_logged_in
    user = db.get(User, int(payload["sub"]))
    if user is None or not user.is_active:
        raise not_logged_in
    return user


def require_roles(*roles: str):
    """Use as: Depends(require_roles("accountant", "finance_manager"))"""

    def checker(user: User = Depends(get_current_user)) -> User:
        if user.role not in roles:
            raise HTTPException(status.HTTP_403_FORBIDDEN, "You don't have access to this page")
        return user

    return checker
