import io

import pandas as pd

from conftest import login


def xlsx(rows: list[dict]) -> bytes:
    buf = io.BytesIO()
    pd.DataFrame(rows).to_excel(buf, index=False)
    return buf.getvalue()


def csv(rows: list[dict]) -> bytes:
    return pd.DataFrame(rows).to_csv(index=False).encode()


DRIVERS = [
    {"Driver No": "D1", "Driver Name": "Test Driver One", "Station Code": "RUH-01", "Station": "Riyadh - Azizia",
     "City": "Riyadh", "Date of Joining": "2025-01-10", "Payment": "Bank", "IBAN": "SA03 4500 0000 0000 0000 0001"},
    {"Driver No": "D2", "Driver Name": "Test Driver Two", "Station Code": "RUH-01", "Station": "Riyadh - Azizia",
     "City": "Riyadh", "Date of Joining": "15/10/2026", "Payment": "csah", "IBAN": None},
    {"Driver No": "D3", "Driver Name": "Test Driver Three", "Station Code": "JED-01", "Station": "Jeddah - Al Safa",
     "City": "Jeddah", "Date of Joining": "2024-05-01", "Leave Date": "2026-10-20", "Payment": "cash", "IBAN": None},
]


def upload(client, headers, month_id, kind, name, content):
    res = client.post(f"/api/months/{month_id}/upload/{kind}", headers=headers, files={"file": (name, content)})
    assert res.status_code == 200, res.text
    return res.json()["files"][kind]


def test_full_upload_flow(client):
    h = login(client, "accountant", "demo123")
    month_id = client.get("/api/months", headers=h).json()[0]["id"]

    # Order matters: vehicles need drivers first
    res = client.post(f"/api/months/{month_id}/upload/vehicles", headers=h,
                      files={"file": ("v.xlsx", xlsx([{"plate_no": "1234 ABC"}]))})
    assert res.status_code == 400

    # Drivers: different column names + a typo that has a suggested fix
    f = upload(client, h, month_id, "drivers", "drivers.xlsx", xlsx(DRIVERS))
    assert f["column_map"]["Driver No"] == "driver_id"
    assert f["column_map"]["Date of Joining"] == "joining_date"
    assert f["status"] == "has_errors"
    typo = next(i for i in f["issues"] if "Csah" in i["message"] or "csah" in i["message"])
    assert typo["fix"]["to"] == "Cash"

    res = client.post(f"/api/months/{month_id}/uploads/{f['id']}/fix", headers=h, json={"issue_ids": [typo["id"]]})
    f = res.json()["files"]["drivers"]
    assert f["status"] == "imported", f["issues"]
    assert f["summary"]["joiners_this_month"] == 1
    assert f["summary"]["leavers_this_month"] == 1

    # Vehicles: D1 drives one plate all month
    f = upload(client, h, month_id, "vehicles", "vehicles.xlsx", xlsx([
        {"Plate": "1234 ABC", "Driver ID": "D1", "From": "2026-10-01", "To": "2026-10-31"},
        {"Plate": "5678 XYZ", "Driver ID": "D2", "From": "2026-10-15", "To": "2026-10-31"},
    ]))
    assert f["status"] == "imported", f["issues"]

    # Deliveries in the "totals per driver" layout
    f = upload(client, h, month_id, "deliveries", "deliveries.csv", csv([
        {"Employee ID": "D1", "Prepaid Orders": 300, "COD Orders": 200},
        {"Employee ID": "D2", "Prepaid Orders": 100, "COD Orders": 50},
        {"Employee ID": "D3", "Prepaid Orders": 150, "COD Orders": 90},
    ]))
    assert f["status"] == "imported", f["issues"]
    assert f["summary"]["layout"] == "totals per driver"

    # Adjustments: a fine with only a plate gets matched to D1
    f = upload(client, h, month_id, "adjustments", "adj.xlsx", xlsx([
        {"plate_no": "1234 ABC", "type": "Traffic fine", "amount": 300, "date": "2026-10-12", "reference": "TF-1"},
        {"driver_id": "D2", "type": "Advance", "amount": 200, "date": "2026-10-20", "reference": "ADV-1"},
        {"driver_id": "D3", "type": "Other", "amount": 50, "date": "2026-10-05"},   # no note -> error
    ]))
    assert f["status"] == "has_errors"
    assert any("needs a note" in i["message"] for i in f["issues"])

    f = upload(client, h, month_id, "adjustments", "adj.xlsx", xlsx([
        {"plate_no": "1234 ABC", "type": "Traffic fine", "amount": 300, "date": "2026-10-12", "reference": "TF-1"},
        {"driver_id": "D2", "type": "Advance", "amount": 200, "date": "2026-10-20", "reference": "ADV-1"},
        {"driver_id": "D3", "type": "Lost parcel", "amount": 1000, "date": "2026-10-08", "reference": "SA1"},
    ]))
    assert f["status"] == "imported", f["issues"]
    assert f["summary"]["fines_matched_by_plate"] == 1

    month = client.get(f"/api/months/{month_id}", headers=h).json()
    assert month["status"] == "ready"


def test_cashier_cannot_upload(client):
    h = login(client, "ruh-01", "demo123")
    assert client.get("/api/months", headers=h).status_code == 403


def test_salary_calculation(client):
    """Worked examples - checked by hand."""
    h = login(client, "accountant", "demo123")
    month_id = client.get("/api/months", headers=h).json()[0]["id"]
    res = client.post(f"/api/months/{month_id}/calculate", headers=h)
    assert res.status_code == 200, res.text
    assert res.json()["drivers"] == 3

    def slip(driver):
        return client.get(f"/api/months/{month_id}/salaries/{driver}", headers=h).json()

    # D1: full month. 1,500 + 300x2 + 200x3 = 2,700. Fine 300 (matched by plate) -> 2,400
    d1 = slip("D1")
    assert (d1["fixed_pay"], d1["prepaid_pay"], d1["cod_pay"], d1["gross"]) == (1500, 600, 600, 2700)
    assert d1["deductions_applied"] == 300 and d1["net"] == 2400
    assert d1["lines"][0]["plate_no"] == "1234 ABC"

    # D2: joined 15 Oct -> 17 days. 1,500/30x17 = 850 + 200 + 150 = 1,200. Advance 200 -> 1,000
    d2 = slip("D2")
    assert d2["days_worked"] == 17 and d2["fixed_pay"] == 850
    assert d2["gross"] == 1200 and d2["net"] == 1000
    assert "joiner" in d2["flags"]

    # D3: left 20 Oct -> 20 days. 1,000 + 300 + 270 = 1,570. Lost parcel 1,000 but cap is 50% = 785
    d3 = slip("D3")
    assert d3["gross"] == 1570
    assert d3["deductions_applied"] == 785 and d3["carried_forward"] == 215 and d3["net"] == 785
    assert "capped" in d3["flags"] and "leaver" in d3["flags"]

    summary = client.get(f"/api/months/{month_id}/summary", headers=h).json()
    assert summary["net"] == 2400 + 1000 + 785
    assert summary["bank_net"] == 2400
    assert summary["stations"][0]["cash_needed"] == 785  # JED-01: D3 is cash


def test_cashier_sees_own_station_payslip_only(client):
    h = login(client, "ruh-01", "demo123")
    month_id = 1
    assert client.get(f"/api/months/{month_id}/salaries/D2", headers=h).status_code == 200
    assert client.get(f"/api/months/{month_id}/salaries/D3", headers=h).status_code == 403


def test_driver_sees_only_own_payslip(client):
    h = login(client, "d2", "1234")
    assert client.get("/api/months/1/salaries/D2", headers=h).json()["net"] == 1000
    assert client.get("/api/months/1/salaries/D1", headers=h).status_code == 403
