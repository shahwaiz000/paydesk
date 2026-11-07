"""Shapes of the data the API sends and receives."""

from pydantic import BaseModel

from .models import User


class LoginRequest(BaseModel):
    username: str
    password: str


class UserOut(BaseModel):
    id: int
    username: str
    full_name: str
    role: str
    station_code: str | None = None
    station_name: str | None = None
    driver_id: str | None = None

    @classmethod
    def from_user(cls, user: User) -> "UserOut":
        station = user.station or (user.driver.station if user.driver else None)
        return cls(
            id=user.id,
            username=user.username,
            full_name=user.full_name,
            role=user.role,
            station_code=station.code if station else None,
            station_name=station.name if station else None,
            driver_id=user.driver_id,
        )


class TokenOut(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user: UserOut
