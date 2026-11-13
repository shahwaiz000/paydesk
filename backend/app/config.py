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
    # Automation 1 (station emails): PayDesk calls this n8n webhook when a month is approved
    n8n_month_approved_url: str = ""   # e.g. http://localhost:5678/webhook/paydesk-month-approved
    # Secret that n8n sends in the X-PayDesk-Key header when it reads data / reports back
    automation_key: str = ""
    # Demo safety: n8n sends EVERY station email to this inbox, never to a real station cashier
    demo_inbox: str = ""
    # Automation 2 (Telegram): PayDesk calls this n8n webhook after the station emails are done,
    # so every linked driver gets his salary message. Empty = no salary messages.
    n8n_salary_messages_url: str = ""   # e.g. http://localhost:5678/webhook/paydesk-salary-messages
    # Token of the Telegram bot (from @BotFather). Only here - never in code, n8n files or Git.
    telegram_bot_token: str = ""


settings = Settings()
