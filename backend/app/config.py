"""App settings. Values can be changed with environment variables or a .env file."""

from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

BACKEND_DIR = Path(__file__).resolve().parents[1]
PROJECT_DIR = BACKEND_DIR.parent


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    database_url: str = "sqlite:///./paydesk-demo.db"   # the demo database is the default
    secret_key: str = "paydesk-dev-secret-change-me-32-chars-min"
    token_minutes: int = 480                 # login lasts 8 hours
    seed_demo_data: bool = False             # fill the database with demo users/drivers
    demo_data_dir: Path = PROJECT_DIR / "samples" / "generated"
    upload_dir: Path = BACKEND_DIR / "uploads"         # files waiting for fixes
    frontend_origin: str = "http://localhost:5174"
    gemini_api_key: str = ""                           # put it in backend/.env - never in code
    gemini_model: str = ""                              # empty = pick the newest flash model automatically


settings = Settings()
