# PayDesk – Progress

**Project:** Driver Payroll & Salary Distribution System (sister to CODesk: CODesk = money in, PayDesk = money out)
**Folder:** `C:\Users\Best Laptop\Documents\paydesk` · **GitHub:** `shahwaiz000/paydesk`
**Stack:** FastAPI + SQLAlchemy + SQLite (backend, port **8001**) · React + TypeScript + Vite + Tailwind 3 (frontend, port **5174**) · Gemini (free tier) for AI
**Data:** fake/demo only. Real salaries only with manager approval.

## Salary rules
- 1,500 SAR fixed for a full month. Joiners/leavers get 1,500 ÷ 30 × days worked.
- Plus prepaid × 2 SAR + COD × 3 SAR + bonuses, minus deductions.
- Deductions are capped at 50% of gross (Labor Law Art. 93). The rest is carried to next month.
- Cash drivers (not company-sponsored) are paid by the station cashier. Bank drivers (company-sponsored) go in a SAB bank file.

## Done
- **Stage 0 – Setup:** folders, venv, React app, Git/GitHub
- **Stage 1 – Demo data:** `scripts/generate_demo_data.py`
  - 50 stations, real city/district names, e.g. "Riyadh - Azizia"
  - 750 drivers, September + October 2026
  - error test files and 6 fake fine documents
- **Stage 2 – Logins & roles:** accountant, finance manager, cashier, driver
- **Stage 3 – Upload & checks:**
  - 4 files in order: drivers → vehicles → deliveries → adjustments
  - automatic column matching, row checks, one-click fixes
  - traffic fines matched to drivers by plate + date
- **Stage 4 – Salary engine:**
  - proration, 50% cap, carry-over between months, flags
  - salary table, station cash plan, payslip view
- **Stage 5 – Review + AI:**
  - more-than-30% change vs last month, with a rule-based reason
  - Gemini one-line reasons and a month summary for the finance manager
  - Gemini code picks the model automatically, retries when Google is busy, and times out (45 s per request, 90 s total)
- **Stage 6 – Fines from documents:**
  - Gemini reads fine PDFs/photos; PayDesk matches the driver by plate + date
  - the accountant confirms before anything is added
  - catches duplicates and plates nobody had that day
- **Extra – Driver search:**
  - search box in the header and a Drivers page
  - driver profile with salary history
  - cashiers see only their own station
- **Fixes:**
  - new columns are added to the database automatically on startup
  - the demo database (`paydesk-demo.db`) is now the default
- **Tests:** 14 passing (`pytest`)

## Where we stopped
- Driver search is built and tested.
- The login problem is fixed: default database is now `paydesk-demo.db`.
- **Next action:** check that the latest work is pushed to Git, then start **Stage 7**.

## Next (in order)
7. **CODesk link:** COD shortages and driver advances come into PayDesk automatically from CODesk (port 8000)
8. **Driver payslip page:** driver login view, daily breakdown, past months, "Why is my salary this?" AI chat (driver's own data only)
9. **Disputes:** driver taps "I don't agree" on a deduction line; accountant inbox; AI-drafted replies
10. **Approve & lock:** accountant prepares → finance manager approves → month locked
11. **Distribution:** one click sends 50 station emails (Outbox page in demo); SAB-style bank Excel file with column mapping; station cash plan
12. **Cashier page:** mark Paid, driver confirms with PIN, unclaimed salaries, AI cashier help
13. **Dashboard + AI insights:** paid / unpaid / disputed per station; Ask PayDesk; pattern alerts; payroll forecast; earnings-drop alerts
14. **Reports:** accounting journal export; AI monthly manager report email
15. **Driver changes:** final settlement for leavers; switching a driver from cash to bank
16. **Polish & launch:** design polish, README, demo video, LinkedIn post

## How to start (3 PowerShell windows)

**Window 3 – Backend** (leave it running, don't type in it)
```powershell
cd "C:\Users\Best Laptop\Documents\paydesk\backend"
```
```powershell
.venv\Scripts\Activate.ps1
```
```powershell
python -m uvicorn app.main:app --reload --port 8001
```

**Window 4 – Frontend** (leave it running, don't type in it)
```powershell
cd "C:\Users\Best Laptop\Documents\paydesk\frontend"
```
```powershell
npm run dev
```

**Window 5 – Commands** (tests, Git, scripts)
```powershell
cd "C:\Users\Best Laptop\Documents\paydesk\backend"
```
```powershell
.venv\Scripts\python.exe -m pytest
```

Open **http://localhost:5174**

## Useful commands (Window 5, backend folder)
- Make demo data: `.venv\Scripts\python.exe scripts\generate_demo_data.py`
- Load September + October and calculate both: `.venv\Scripts\python.exe scripts\load_demo_months.py`
- Fresh demo database:
  1. Stop Window 3.
  2. `Remove-Item paydesk-demo.db`
  3. `$env:SEED_DEMO_DATA="true"`
  4. Start uvicorn.
  5. Run `load_demo_months.py`.
- Save to Git (run from the `paydesk` folder):
  1. `git add .`
  2. `git commit -m "..."`
  3. `git push`

## Demo logins
| Role | Username | Password |
|---|---|---|
| Accountant | `accountant` | `demo123` |
| Finance manager | `manager` | `demo123` |
| Cashier (any station code) | `ruh-01` | `demo123` |
| Driver (any driver ID) | `d10001` | PIN `1234` |

## Notes
- The Gemini key is in `backend\.env` as `GEMINI_API_KEY=...`. Git ignores it; never share it.
- Claude writes code files straight into the paydesk folder (folder access is granted). Shahwaiz runs the commands.
- PowerShell opens as Administrator in `system32`, so always `cd` to the paydesk folder first.
- Working style:
  - simple English, 2–3 steps at a time
  - one command per code block
  - always say which window to use
  - free tools only
