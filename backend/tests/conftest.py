"""Test setup: a separate test database and a tiny fake driver file.

Environment variables must be set BEFORE the app is imported.
"""

import os
import tempfile
from pathlib import Path

import pandas as pd
import pytest

TEST_DIR = Path(tempfile.mkdtemp(prefix="paydesk-test-"))

pd.DataFrame([
    {"driver_id": "D1", "name": "Test Driver One", "iqama_no": "2000000001", "city": "Riyadh",
     "station": "Riyadh - Azizia", "station_code": "RUH-01", "joining_date": "2025-01-10",
     "leaving_date": None, "payment_method": "Bank", "iban": "SA0345000000000000000001", "phone": "0500000001"},
    {"driver_id": "D2", "name": "Test Driver Two", "iqama_no": "2000000002", "city": "Riyadh",
     "station": "Riyadh - Azizia", "station_code": "RUH-01", "joining_date": "2026-10-15",
     "leaving_date": None, "payment_method": "Cash", "iban": None, "phone": "0500000002"},
    {"driver_id": "D3", "name": "Test Driver Three", "iqama_no": "2000000003", "city": "Jeddah",
     "station": "Jeddah - Al Safa", "station_code": "JED-01", "joining_date": "2024-05-01",
     "leaving_date": "2026-10-20", "payment_method": "Cash", "iban": None, "phone": "0500000003"},
]).to_excel(TEST_DIR / "drivers.xlsx", index=False)

os.environ["DATABASE_URL"] = f"sqlite:///{(TEST_DIR / 'test.db').as_posix()}"
os.environ["SEED_DEMO_DATA"] = "true"
os.environ["DEMO_DATA_DIR"] = str(TEST_DIR)

from fastapi.testclient import TestClient  # noqa: E402

from app.main import app  # noqa: E402


@pytest.fixture(scope="session")
def client():
    with TestClient(app) as c:
        yield c


def login(client, username: str, password: str) -> dict:
    res = client.post("/api/auth/login", json={"username": username, "password": password})
    assert res.status_code == 200, res.text
    return {"Authorization": f"Bearer {res.json()['access_token']}"}
