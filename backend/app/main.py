from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from . import models  # noqa: F401  (registers the tables)
from .config import settings
from .database import Base, SessionLocal, engine
from .payroll.engine import get_settings
from .routers import auth, months, overview, salaries
from .seed import seed_demo


@asynccontextmanager
async def lifespan(app: FastAPI):
    Base.metadata.create_all(bind=engine)
    with SessionLocal() as db:
        get_settings(db)   # make sure the salary rules row exists
        db.commit()
    if settings.seed_demo_data:
        with SessionLocal() as db:
            seed_demo(db)
    yield


app = FastAPI(title="PayDesk API", version="0.4.0", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[settings.frontend_origin],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth.router)
app.include_router(overview.router)
app.include_router(months.router)
app.include_router(salaries.router)


@app.get("/api/health")
def health():
    return {"status": "ok", "app": "PayDesk"}
