from conftest import login


def test_health(client):
    assert client.get("/api/health").json()["status"] == "ok"


def test_accountant_login_and_overview(client):
    headers = login(client, "accountant", "demo123")
    me = client.get("/api/auth/me", headers=headers).json()
    assert me["role"] == "accountant"

    data = client.get("/api/overview", headers=headers).json()
    assert data["stations"] == 2
    assert data["drivers"] == 3
    assert data["cash_drivers"] == 2


def test_username_is_not_case_sensitive(client):
    login(client, "  Accountant ", "demo123")


def test_wrong_password_is_rejected(client):
    res = client.post("/api/auth/login", json={"username": "accountant", "password": "nope"})
    assert res.status_code == 401


def test_cashier_sees_only_own_station(client):
    headers = login(client, "ruh-01", "demo123")
    data = client.get("/api/overview", headers=headers).json()
    assert data["station"] == "Riyadh - Azizia"
    assert data["drivers"] == 2
    assert data["cash_drivers"] == 1


def test_driver_login_with_pin(client):
    headers = login(client, "d1", "1234")
    data = client.get("/api/overview", headers=headers).json()
    assert data["driver_id"] == "D1"
    assert data["iban_last4"] == "0001"   # never the full IBAN


def test_no_token_means_401(client):
    assert client.get("/api/overview").status_code == 401
