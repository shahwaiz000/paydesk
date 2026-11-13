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


# ------------------------------------------------------------------ Stage 10: approve & lock

def test_approve_and_lock(client):
    acc = login(client, "accountant", "demo123")
    mgr = login(client, "manager", "demo123")
    drv = login(client, "d1", "1234")

    # An open dispute blocks sending
    slip = client.get("/api/me/payslips/1", headers=drv).json()
    fine = next(l for l in slip["lines"] if l["type"] == "Traffic fine")
    client.post("/api/me/payslips/1/disputes", headers=drv,
                json={"topic": "deduction", "line_key": fine["key"], "message": "I was not driving that day"})
    res = client.post("/api/months/1/submit", headers=acc, json={})
    assert res.status_code == 400 and "dispute" in res.json()["detail"]
    d = client.get("/api/disputes", headers=acc).json()["items"][0]
    client.post(f"/api/disputes/{d['id']}/answer", headers=acc,
                json={"decision": "rejected", "reply": "Hello, the plate was with you that day."})

    assert client.post("/api/months/1/submit", headers=mgr, json={}).status_code == 403   # manager can't send
    res = client.post("/api/months/1/submit", headers=acc, json={"note": "October ready"})
    assert res.status_code == 200, res.text
    assert res.json()["status"] == "submitted"

    # Locked while waiting: no uploads, no recalculation, no fines
    assert client.post("/api/months/1/calculate", headers=acc).status_code == 400
    up = client.post("/api/months/1/upload/adjustments", headers=acc, files={"file": ("a.csv", b"x")})
    assert up.status_code == 400
    assert client.get("/api/me/payslips/1", headers=drv).json()["final"] is False

    # Manager sends it back with a reason -> accountant can work again
    assert client.post("/api/months/1/send-back", headers=mgr, json={"reason": "no"}).status_code == 422
    res = client.post("/api/months/1/send-back", headers=mgr, json={"reason": "Check the D3 lost parcel"})
    assert res.json()["status"] == "calculated" and res.json()["returned_note"] == "Check the D3 lost parcel"
    assert client.get("/api/months/1", headers=acc).json()["returned_note"] == "Check the D3 lost parcel"

    # Send again and approve
    client.post("/api/months/1/submit", headers=acc, json={})
    assert client.post("/api/months/1/approve", headers=acc).status_code == 403          # accountant can't approve
    res = client.post("/api/months/1/approve", headers=mgr)
    assert res.status_code == 200, res.text
    data = res.json()
    assert data["status"] == "approved" and data["approved_by"] == "manager"
    assert [e["action"] for e in data["events"]] == ["submitted", "sent_back", "submitted", "approved"]
    assert data["events"][-1]["totals"]["net"] == data["totals"]["net"]

    # Final for drivers; still locked; can't be sent back any more
    assert client.get("/api/me/payslips/1", headers=drv).json()["final"] is True
    assert client.get("/api/me/payslips", headers=drv).json()["months"][0]["final"] is True
    assert client.post("/api/months/1/calculate", headers=acc).status_code == 400
    assert client.post("/api/months/1/send-back", headers=mgr, json={"reason": "too late now"}).status_code == 400


def test_previous_month_must_be_approved_first(client):
    acc = login(client, "accountant", "demo123")
    mgr = login(client, "manager", "demo123")
    from app.database import SessionLocal
    from app.models import PayrollMonth

    with SessionLocal() as db:
        nov = PayrollMonth(period="2026-12", status="submitted")
        nov2 = PayrollMonth(period="2026-11", status="calculated")
        db.add_all([nov, nov2])
        db.commit()
        dec_id = nov.id
    res = client.post(f"/api/months/{dec_id}/approve", headers=mgr)
    assert res.status_code == 400 and "Approve 2026-11 first" in res.json()["detail"]
    checks = client.get(f"/api/months/{dec_id}/approval", headers=acc).json()["checks"]
    assert any(c["key"] == "previous" and not c["ok"] for c in checks)


# ------------------------------------------------------------------ Stage 11 + Automation 1: station emails

def test_station_emails_prepared_on_approval(client):
    acc = login(client, "accountant", "demo123")
    mgr = login(client, "manager", "demo123")
    cashier = login(client, "ruh-01", "demo123")

    # Month 2026-11 is only calculated -> nothing to send yet
    months = {m["period"]: m["id"] for m in client.get("/api/months", headers=acc).json()}
    res = client.post(f"/api/months/{months['2026-11']}/outbox/run", headers=acc)
    assert res.status_code == 400 and "approve" in res.json()["detail"]

    # October was approved (test above) -> the emails were prepared automatically.
    # n8n is not set up in tests -> "not_connected", with the missing .env lines named
    assert client.get("/api/months/1/outbox", headers=cashier).status_code == 403
    box = client.get("/api/months/1/outbox", headers=acc).json()
    assert box["prepared"] == 2 and box["delivered"] == 0 and box["waiting"] == 2
    assert box["run"]["status"] == "not_connected" and "N8N_MONTH_APPROVED_URL" in box["run"]["note"]
    assert box["can_run"] is True and box["n8n_ready"] is False
    assert [e["station_code"] for e in box["emails"]] == ["JED-01", "RUH-01"]
    ruh = box["emails"][1]
    assert ruh["to"] == "ruh-01@stations.paydesk.demo" and ruh["status"] == "prepared"
    assert ruh["drivers"] == 2 and ruh["cash_drivers"] == 1 and ruh["bank_drivers"] == 1

    # Totals match the approved month
    totals = client.get("/api/months/1/approval", headers=acc).json()["totals"]
    assert round(box["cash_total"], 2) == totals["cash_net"]
    assert round(box["bank_total"], 2) == totals["bank_net"]

    # Open one email (manager can read) and download its Excel file
    full = client.get(f"/api/months/1/outbox/{ruh['id']}", headers=mgr).json()
    assert "D2" in full["body"] and "D1" not in full["body"].split("pay these drivers:")[1].split("Pay each")[0]
    xl = client.get(f"/api/months/1/outbox/{ruh['id']}/attachment", headers=acc)
    assert xl.status_code == 200 and xl.content[:2] == b"PK"
    sheet = pd.read_excel(io.BytesIO(xl.content), header=None)
    assert "D2" in sheet.astype(str).values and "D1" in sheet.astype(str).values


def test_automation_1_with_n8n(client, monkeypatch):
    acc = login(client, "accountant", "demo123")
    mgr = login(client, "manager", "demo123")
    from app.config import settings
    from app.routers import distribution

    called = []

    class FakeResponse:
        status_code = 200

    def fake_post(url, json, timeout):
        called.append((url, json))
        return FakeResponse()

    monkeypatch.setattr(settings, "n8n_month_approved_url", "http://n8n.test/webhook/paydesk-month-approved")
    monkeypatch.setattr(settings, "automation_key", "test-key-123")
    monkeypatch.setattr(settings, "demo_inbox", "demo.inbox@gmail.com")
    monkeypatch.setattr(distribution.httpx, "post", fake_post)

    # Accountant starts it again (it was "not connected") -> n8n webhook called with the month
    assert client.post("/api/months/1/outbox/run", headers=mgr).status_code == 403
    res = client.post("/api/months/1/outbox/run", headers=acc)
    assert res.status_code == 200, res.text
    assert len(called) == 1 and called[0][1]["month_id"] == 1 and called[0][1]["stations_to_send"] == 2
    box = client.get("/api/months/1/outbox", headers=acc).json()
    assert box["run"]["status"] == "running" and box["can_run"] is False
    assert client.post("/api/months/1/outbox/run", headers=acc).status_code == 400    # already running

    # The automation API needs the key
    assert client.get("/api/automation/months/1/station-emails").status_code == 401
    assert client.get("/api/automation/months/1/station-emails",
                      headers={"X-PayDesk-Key": "wrong"}).status_code == 401
    key = {"X-PayDesk-Key": "test-key-123"}

    data = client.get("/api/automation/months/1/station-emails", headers=key).json()
    assert data["count"] == 2 and data["send_to"] == "demo.inbox@gmail.com"
    jed, ruh = data["stations"]
    assert ruh["send_to"] == "demo.inbox@gmail.com" and ruh["cashier_email"] == "ruh-01@stations.paydesk.demo"
    assert [d["driver_id"] for d in ruh["cash_list"]] == ["D2"]          # bank driver D1 not in the cash list
    xl = client.get(f"/api/automation/outbox/{ruh['email_id']}/attachment", headers=key)
    assert xl.status_code == 200 and xl.content[:2] == b"PK"

    # n8n reports: JED sent, RUH failed
    r = client.post(f"/api/automation/outbox/{jed['email_id']}/result", headers=key,
                    json={"status": "sent", "gmail_id": "abc123"})
    assert r.json()["status"] == "sent"
    client.post(f"/api/automation/outbox/{ruh['email_id']}/result", headers=key,
                json={"status": "failed", "note": "Gmail quota"})
    fin = client.post("/api/automation/months/1/run-finished", headers=key).json()
    assert fin["sent"] == 1 and fin["failed"] == 1 and fin["status"] == "failed"
    assert fin["notify_to"] == "demo.inbox@gmail.com" and fin["seconds"] is not None

    # A "sent" email can never go back to failed
    r = client.post(f"/api/automation/outbox/{jed['email_id']}/result", headers=key, json={"status": "failed"})
    assert r.json()["status"] == "sent"

    # Run again -> n8n only gets the failed one (no station gets the same email twice)
    assert client.post("/api/months/1/outbox/run", headers=acc).status_code == 200
    data = client.get("/api/automation/months/1/station-emails", headers=key).json()
    assert [s["station_code"] for s in data["stations"]] == ["RUH-01"]
    client.post(f"/api/automation/outbox/{ruh['email_id']}/result", headers=key, json={"status": "sent"})
    fin = client.post("/api/automation/months/1/run-finished", headers=key).json()
    assert fin["sent"] == 2 and fin["status"] == "done"
    box = client.get("/api/months/1/outbox", headers=acc).json()
    assert box["delivered"] == 2 and box["can_run"] is False
    assert box["emails"][0]["delivered_to"] == "demo.inbox@gmail.com" and box["emails"][0]["gmail_id"] == "abc123"

    # n8n down -> the run shows a clear message
    def down(url, json, timeout):
        raise distribution.httpx.ConnectError("no")

    monkeypatch.setattr(distribution.httpx, "post", down)
    from app.database import SessionLocal
    from app.models import PayrollMonth
    distribution.call_n8n(1)
    with SessionLocal() as db:
        m = db.get(PayrollMonth, 1)
        assert m.emails_run_status == "failed" and "Can't reach n8n" in m.emails_run_note



def test_automation_2_telegram_bot(client, monkeypatch):
    from app.config import settings
    from app.routers import automation, telegram

    monkeypatch.setattr(settings, "automation_key", "test-key-123")
    key = {"X-PayDesk-Key": "test-key-123"}
    acc = login(client, "accountant", "demo123")

    def say(text=None, chat="555", callback=None, message_id=None):
        res = client.post("/api/automation/telegram/message", headers=key,
                          json={"chat_id": chat, "text": text, "callback_data": callback, "message_id": message_id})
        assert res.status_code == 200, res.text
        return res.json()

    # Needs the key
    assert client.post("/api/automation/telegram/message", json={"chat_id": "1", "text": "hi"}).status_code == 401

    # Not linked -> nothing about any salary
    assert "Welcome" in say("/start")["telegram"]["text"]
    r = say("why was my salary cut?")
    assert r["action"] == "reply" and "not linked" in r["telegram"]["text"]

    # Wrong PIN -> refused, and the PIN message is deleted; 5 wrong tries an hour
    r = say("/link D3 9999", message_id=11)
    assert "wrong" in r["telegram"]["text"] and r["delete_message_id"] == 11
    for _ in range(4):
        say("/link D3 0000")
    assert "Too many" in say("/link D3 1234")["telegram"]["text"]
    telegram._bad_links.clear()

    # Right PIN -> linked
    r = say("/link d3 1234", message_id=12)
    assert "Linked to driver D3" in r["telegram"]["text"] and r["delete_message_id"] == 12

    # /salary -> rule-based message with a "wrong" button per deduction
    r = say("/salary")
    text = r["telegram"]["text"]
    assert "Net salary: SAR 785" in text and "Lost parcel" in text and "SA1" in text
    buttons = r["telegram"]["reply_markup"]["inline_keyboard"]
    assert buttons[0][0]["callback_data"] == "w:1:0" and buttons[-1][0]["callback_data"] == "o:1"

    # A question -> ask_ai with ONLY his numbers (no name / Iqama / IBAN / phone)
    r = say("ليش انخصم مني ١٠٠٠؟")
    assert r["action"] == "ask_ai" and r["language"] == "ar"
    facts = str(r["facts"])
    assert r["facts"]["driver_id"] == "D3" and r["facts"]["net_salary"] == 785
    assert "Test Driver Three" not in facts and "2000000003" not in facts and "0500000003" not in facts
    assert r["fallback_text"] and r["telegram"]["chat_id"] == "555"

    # Another chat can't see D3 - and can't use D3's buttons
    assert say("/salary", chat="777")["telegram"]["text"].startswith("🔒")
    assert say(callback="w:1:0", chat="777")["telegram"]["text"].startswith("🔒")

    # "This is wrong" -> asks the reason -> next message opens a dispute in PayDesk
    open_before = client.get("/api/disputes/count", headers=acc).json()["open"]
    assert "ONE message" in say(callback="w:1:0")["telegram"]["text"]
    r = say("I never lost this parcel, I delivered it")
    assert "report #" in r["telegram"]["text"]
    assert client.get("/api/disputes/count", headers=acc).json()["open"] == open_before + 1
    item = client.get("/api/disputes", headers=acc).json()["items"][-1]
    assert item["source"] == "telegram" and item["driver_id"] == "D3" and item["line"]["reference"] == "SA1"
    # Same line twice -> clear message, no second dispute
    say(callback="w:1:0")
    assert "already reported" in say("still wrong!!")["telegram"]["text"]
    # Old / made-up buttons
    assert "old" in say(callback="w:1:9")["telegram"]["text"]
    assert "old" in say(callback="w:999:0")["telegram"]["text"]

    # Accountant answers in PayDesk -> n8n gets it to deliver on Telegram, once
    assert client.get("/api/automation/telegram/answers", headers=key).json()["count"] == 0
    res = client.post(f"/api/disputes/{item['id']}/answer", headers=acc,
                      json={"decision": "rejected", "reply": "The parcel SA1 was signed as lost by the hub on 8 Oct."})
    assert res.status_code == 200, res.text
    ans = client.get("/api/automation/telegram/answers", headers=key).json()
    assert ans["count"] == 1 and ans["answers"][0]["telegram"]["chat_id"] == "555"
    assert "signed as lost" in ans["answers"][0]["telegram"]["text"]
    client.post(f"/api/automation/telegram/answers/{item['id']}/delivered", headers=key)
    assert client.get("/api/automation/telegram/answers", headers=key).json()["count"] == 0

    # Salary messages (workflow 02): only linked drivers, only approved months, never twice
    assert client.get("/api/automation/months/3/telegram-salary-messages", headers=key).status_code == 400
    msgs = client.get("/api/automation/months/1/telegram-salary-messages", headers=key).json()
    assert msgs["count"] == 1 and msgs["messages"][0]["driver_id"] == "D3"
    assert "SAR 785" in msgs["messages"][0]["text_en"]
    client.post("/api/automation/months/1/telegram-salary-messages/D3/result", headers=key, json={"status": "sent"})
    assert client.get("/api/automation/months/1/telegram-salary-messages", headers=key).json()["count"] == 0

    # Station emails finished -> PayDesk starts workflow 02 in n8n
    called = []

    class Ok:
        status_code = 200

    monkeypatch.setattr(settings, "n8n_salary_messages_url", "http://n8n.test/webhook/paydesk-salary-messages")
    monkeypatch.setattr(automation.httpx, "post", lambda url, json, timeout: called.append(json) or Ok())
    assert client.post("/api/automation/months/1/run-finished", headers=key).json()["status"] == "done"
    assert called and called[0]["month_id"] == 1 and called[0]["linked_drivers"] == 1

    # Bot address comes from .env (token never in n8n files)
    assert client.get("/api/automation/telegram/bot", headers=key).status_code == 503
    monkeypatch.setattr(settings, "telegram_bot_token", "123:ABC")
    bot = client.get("/api/automation/telegram/bot", headers=key).json()
    assert bot["api"] == "https://api.telegram.org/bot123:ABC" and bot["offset"] == 0

    # Telegram offset only moves forward
    assert client.put("/api/automation/telegram/offset", headers=key, json={"offset": 50}).json()["offset"] == 50
    assert client.put("/api/automation/telegram/offset", headers=key, json={"offset": 10}).json()["offset"] == 50

    # Unlink -> nothing any more
    assert "no longer linked" in say("/unlink")["telegram"]["text"]
    assert say("/salary")["telegram"]["text"].startswith("🔒")
