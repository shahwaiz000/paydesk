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


def test_fines_from_documents(client, monkeypatch):
    """AI reading is faked here (no internet in tests) - we test matching, duplicates and adding."""
    import app.routers.fines as fines_router

    answers = {
        "a.pdf": {"fine_number": "TV-1", "plate_no": "ABC-1234", "date": "2026-10-20", "amount": "500",
                  "violation": "Speeding", "confidence": "high"},
        "b.png": {"fine_number": "TV-2", "plate_no": "9999 ZZZ", "date": "2026-10-20", "amount": 300},
        "c.pdf": {"fine_number": "TF-1", "plate_no": "1234 ABC", "date": "2026-10-12", "amount": 300},
    }
    monkeypatch.setattr(fines_router, "read_document", lambda name, data: answers[name])

    h = login(client, "accountant", "demo123")
    res = client.post("/api/months/1/fines/read", headers=h,
                      files=[("files", (n, b"x")) for n in answers])
    assert res.status_code == 200, res.text
    r = {x["filename"]: x for x in res.json()["results"]}
    assert r["a.pdf"]["driver"]["id"] == "D1" and r["a.pdf"]["problem"] is None   # 'ABC-1234' == '1234 ABC'
    assert "No driver had this plate" in r["b.png"]["problem"]
    assert r["c.pdf"]["duplicate"] is True                                           # TF-1 already in File 3

    res = client.post("/api/months/1/fines/add", headers=h, json={"fines": [
        {"filename": "a.pdf", "fine_number": "TV-1", "plate_no": "ABC-1234", "date": "2026-10-20",
         "amount": 500, "violation": "Speeding", "driver_id": "D1"},
        {"filename": "b.png", "fine_number": "TV-2", "plate_no": "9999 ZZZ", "date": "2026-10-20",
         "amount": 300, "driver_id": "D2"},          # wrong on purpose - server must refuse it
    ]})
    data = res.json()
    assert data["added"] == 1 and len(data["skipped"]) == 1
    assert data["month"]["status"] == "ready"        # needs recalculation now

    client.post("/api/months/1/calculate", headers=h)
    d1 = client.get("/api/months/1/salaries/D1", headers=h).json()
    assert d1["deductions_applied"] == 800           # 300 (file) + 500 (from document)
    assert any("read by AI" in (l["note"] or "") for l in d1["lines"])


def test_driver_search(client):
    h = login(client, "accountant", "demo123")
    res = client.get("/api/drivers?q=two", headers=h).json()
    assert [d["id"] for d in res["items"]] == ["D2"]
    assert client.get("/api/drivers?q=d3", headers=h).json()["items"][0]["name"] == "Test Driver Three"
    profile = client.get("/api/drivers/d1", headers=h).json()
    assert profile["months"][0]["period"] == "2026-10"

    cashier = login(client, "ruh-01", "demo123")       # Riyadh cashier
    ids = [d["id"] for d in client.get("/api/drivers", headers=cashier).json()["items"]]
    assert sorted(ids) == ["D1", "D2"]                 # D3 is in Jeddah - not visible
    assert client.get("/api/drivers/D3", headers=cashier).status_code == 403


# ------------------------------------------------------------------ Stage 8: driver payslip page

def test_driver_sees_own_payslips(client):
    h = login(client, "d1", "1234")
    data = client.get("/api/me/payslips", headers=h).json()
    assert data["driver"]["id"] == "D1"
    assert [m["period"] for m in data["months"]] == ["2026-10"]
    m = data["months"][0]
    assert m["final"] is False                      # calculated but not approved yet
    assert m["net"] == 1900 and m["deliveries"] == 500

    slip = client.get(f"/api/me/payslips/{m['month_id']}", headers=h).json()
    assert slip["driver_id"] == "D1" and slip["net"] == 1900
    words = " ".join(slip["in_words"])
    assert "SAR 1,900" in words and "not final yet" in words
    assert "Traffic fine SAR 300" in words and "Traffic fine SAR 500" in words


def test_driver_page_is_private(client):
    staff = login(client, "accountant", "demo123")
    assert client.get("/api/me/payslips", headers=staff).status_code == 403

    h = login(client, "d3", "1234")
    slip = client.get("/api/me/payslips/1", headers=h).json()
    assert slip["driver_id"] == "D3"                # never another driver's payslip
    assert "moves to next month" in " ".join(slip["in_words"])   # capped at 50%
    assert client.get("/api/me/payslips/999", headers=h).status_code == 404


def test_driver_cannot_see_month_before_calculation(client):
    from app.database import SessionLocal
    from app.models import PayrollMonth

    with SessionLocal() as db:
        db.get(PayrollMonth, 1).status = "ready"      # accountant is still working on it
        db.commit()
    h = login(client, "d1", "1234")
    try:
        assert client.get("/api/me/payslips", headers=h).json()["months"] == []
        assert client.get("/api/me/payslips/1", headers=h).status_code == 404
    finally:
        with SessionLocal() as db:
            db.get(PayrollMonth, 1).status = "calculated"
            db.commit()


def test_payslip_chat(client, monkeypatch):
    """AI is faked (no internet in tests). We check what is sent to it - and what is NOT."""
    import app.routers.me as me_router
    from app.ai import payslip_chat

    sent = {}

    def fake_generate(prompt, fast=False):
        assert fast is True                         # driver chat uses the quick models
        sent["prompt"] = prompt
        return "Your fixed salary is 1,500 for the full month."

    monkeypatch.setattr(payslip_chat, "generate", fake_generate)
    me_router._asked.clear()
    h = login(client, "d1", "1234")
    res = client.post("/api/me/payslips/1/ask", headers=h, json={
        "question": "Why is my salary 1900?",
        "history": [{"role": "driver", "text": "hi"}, {"role": "assistant", "text": "Hello!"}],
    })
    assert res.status_code == 200, res.text
    assert "1,500" in res.json()["answer"]
    prompt = sent["prompt"]
    assert "Why is my salary 1900?" in prompt and '"net_salary": 1900' in prompt
    assert "Test Driver One" not in prompt          # no name
    assert "SA03" not in prompt                     # no IBAN
    assert '"D2"' not in prompt and '"D3"' not in prompt   # no other drivers

    too_long = client.post("/api/me/payslips/1/ask", headers=h, json={"question": "x" * 301})
    assert too_long.status_code == 422

    monkeypatch.setattr(me_router, "QUESTIONS_PER_HOUR", 1)
    assert client.post("/api/me/payslips/1/ask", headers=h, json={"question": "again?"}).status_code == 429


# ------------------------------------------------------------------ Stage 9: disputes

def test_driver_reports_a_deduction(client):
    h = login(client, "d2", "1234")
    slip = client.get("/api/me/payslips/1", headers=h).json()
    advance = next(l for l in slip["lines"] if l["type"] == "Advance")
    assert slip["disputes"] == []

    res = client.post("/api/me/payslips/1/disputes", headers=h,
                      json={"topic": "deduction", "line_key": advance["key"], "message": "I already paid this back"})
    assert res.status_code == 200, res.text
    assert res.json()["dispute"]["status"] == "open"
    assert res.json()["dispute"]["line"]["reference"] == "ADV-1"

    again = client.post("/api/me/payslips/1/disputes", headers=h,
                        json={"topic": "deduction", "line_key": advance["key"], "message": "please check"})
    assert again.status_code == 400                                  # one open report per line
    fake = client.post("/api/me/payslips/1/disputes", headers=h,
                       json={"topic": "deduction", "line_key": "Deduction|Traffic fine|TF-1|2026-10-12|300.00|",
                             "message": "not mine"})
    assert fake.status_code == 400                                   # D1's line, not his

    other = login(client, "d1", "1234")
    assert client.get("/api/me/payslips/1", headers=other).json()["disputes"] == []   # private


def test_accountant_answers_and_removes_deduction(client, monkeypatch):
    from app.ai import disputes as ai_disputes

    sent = {}

    def fake_generate(prompt, fast=False):
        sent["prompt"] = prompt
        return "Hello, you are right. We removed the advance."

    monkeypatch.setattr(ai_disputes, "generate", fake_generate)
    cashier = login(client, "ruh-01", "demo123")
    assert client.get("/api/disputes", headers=cashier).status_code == 403

    h = login(client, "accountant", "demo123")
    inbox = client.get("/api/disputes", headers=h).json()
    assert inbox["counts"]["open"] == 1
    d = inbox["items"][0]
    assert d["driver_id"] == "D2" and d["can_remove"] is True
    assert client.get("/api/disputes/count", headers=h).json() == {"open": 1}

    draft = client.post(f"/api/disputes/{d['id']}/draft", headers=h, json={"decision": "accepted"}).json()["draft"]
    assert draft.startswith("Hello")
    assert "I already paid this back" in sent["prompt"] and "Test Driver Two" not in sent["prompt"]

    manager = login(client, "manager", "demo123")
    assert client.post(f"/api/disputes/{d['id']}/answer", headers=manager,
                       json={"decision": "accepted", "reply": "ok"}).status_code == 403   # can read, not answer

    res = client.post(f"/api/disputes/{d['id']}/answer", headers=h,
                      json={"decision": "accepted", "reply": draft, "remove_deduction": True})
    assert res.status_code == 200, res.text
    assert "Calculate salaries" in res.json()["note"]
    assert client.get("/api/months/1", headers=h).json()["status"] == "ready"
    assert client.post(f"/api/disputes/{d['id']}/answer", headers=h,
                       json={"decision": "rejected", "reply": "again"}).status_code == 400

    client.post("/api/months/1/calculate", headers=h)
    assert client.get("/api/months/1/salaries/D2", headers=h).json()["net"] == 1200   # advance gone

    driver = login(client, "d2", "1234")
    mine = client.get("/api/me/payslips/1", headers=driver).json()["disputes"]
    assert mine[0]["status"] == "accepted" and mine[0]["reply"].startswith("Hello")
    assert mine[0]["deduction_removed"] is True


def test_reject_keeps_deduction(client):
    h = login(client, "d3", "1234")
    slip = client.get("/api/me/payslips/1", headers=h).json()
    parcel = next(l for l in slip["lines"] if l["type"] == "Lost parcel")
    d = client.post("/api/me/payslips/1/disputes", headers=h,
                    json={"topic": "deduction", "line_key": parcel["key"], "message": "I delivered that parcel"}
                    ).json()["dispute"]
    acc = login(client, "accountant", "demo123")
    res = client.post(f"/api/disputes/{d['id']}/answer", headers=acc,
                      json={"decision": "rejected", "reply": "Hello, the customer did not receive it.",
                            "remove_deduction": True})
    assert res.status_code == 400                                    # can't remove when rejecting
    res = client.post(f"/api/disputes/{d['id']}/answer", headers=acc,
                      json={"decision": "rejected", "reply": "Hello, the customer did not receive it."})
    assert res.json()["dispute"]["status"] == "rejected"
    assert client.get("/api/months/1/salaries/D3", headers=acc).json()["deductions_applied"] == 785
