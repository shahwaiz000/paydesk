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
- **Stage 8 – Driver payslip page:**
  - driver home: latest salary card + past months
  - full payslip: earnings, deductions with reasons, 50% rule, day-by-day deliveries
  - "Your salary in simple words" (no AI, always works)
  - "Why is my salary this?" AI chat: sees only that driver's payslip, no name/Iqama/IBAN sent, 20 questions an hour
  - drivers see a month once it is calculated, marked "Not final yet" until approved (Stage 10)
  - works on a phone screen
- **Stage 9 – Disputes:**
  - driver taps "I don't agree" on a deduction, or "Report a problem" (deliveries, days, other)
  - one open report per line, max 5 open per month; server checks the line is on his own payslip
  - accountant inbox (Disputes page, red badge with waiting count); finance manager can read only
  - "Driver is right" / "Keep it – explain why"; AI drafts the reply, accountant edits and sends
  - "Driver is right" can remove the deduction from this month (then recalculate)
  - driver sees the answer under the line on his payslip
- **Stage 10 – Approve & lock:**
  - month steps: Calculated → Sent for approval → Approved & locked
  - accountant "Send for approval" (blocked while driver disputes are waiting)
  - finance manager "Approve & lock" (blocked until the previous month is approved) or "Send back" with a reason
  - sent / approved months are locked: no uploads, fixes, fines, recalculation or deduction removal
  - drivers see "✓ Final" once approved; history of who sent / approved / sent back, with the net at that moment
  - home page shows months waiting for the manager, and months sent back to the accountant
- **Stage 11 – Distribution (part 1 of 3): station emails ✅**
  - month page, after approval: "Send 50 station emails" (accountant only, once per month)
  - one email per station: cash to prepare, list of cash drivers, bank drivers for info
  - Excel attachment per station: all drivers, net, "Paid on" + "Driver signature" columns for cash drivers
  - Outbox page (`/months/<id>/outbox`): list of stations, read each email, download its Excel
  - demo mode: emails are saved in the Outbox, not really sent
  - "📧 Send a real copy to my Gmail" (Outbox, accountant): sends ONE station email to an **n8n webhook**;
    n8n adds an Arabic version with Gemini and sends it with Gmail to Shahwaiz's own inbox (never to a station).
    Max 10 real copies a day. Needs `N8N_WEBHOOK_URL=...` in `backend\.env`.
- **Fixes:**
  - new columns are added to the database automatically on startup
  - the demo database (`paydesk-demo.db`) is now the default
- **Tests:** 25 passing (`pytest`)

## Where we stopped (12 Nov 2026)
- Stages 8, 9, 10 and Stage 11 part 1 (station emails + Outbox + "real copy" button) are built and tested (25 tests passing).
- **12 Nov:** direction changed to automation-first – see "DIRECTION" and "The 12 automations" below.
- **Next action:** agree the design of automation 1 (station emails), then build it.
  n8n runs locally: `npx n8n@2.45.7` → http://localhost:5678.
- Push to GitHub if not done yet:
  `git add .` → `git commit -m "Stage 11 part 1: station salary emails and Outbox"` → `git push`

## Done today (11 Nov 2026)
- Decided: **no CODesk link**. PayDesk stays separate. Shortages and advances keep coming from the adjustments file.
- Stage 8 – driver payslip page + "Why is my salary this?" AI chat.
- AI chat made faster: it uses the quick flash-lite model first and keeps the Google connection open.
  Window 3 prints `[ai] <model> answered in X s` after every AI answer.
- Fixed `.env`: it had been overwritten by an old progress note, so AI was off.
  Never paste notes or other text into `.env` (see Notes for the lines it holds).
- Stage 9 – driver disputes + accountant inbox + AI-drafted replies.
- Fix: choosing "Driver is right" now ticks "Remove this deduction" automatically. If the deduction is not removed,
  the driver sees "the payroll team will correct it".
  (Sohel D10001 was not a bug: 300 = September advance, 500 = October advance.)
- Stage 10 – approve & lock (accountant sends → finance manager approves or sends back).
- Approved months can't be unlocked. To start the demo again, make a fresh demo database (see Useful commands).

## DIRECTION (decided 12 Nov 2026) – read this first
PayDesk is an **AI automation project, not a web project**. The web app is only the control panel
(where data lives, people look and click). **n8n, Power Automate and Gemini do the visible work.**
LinkedIn story: "Monthly driver payroll for 50 stations took hours of files, checks, emails and follow-ups.
Now the accountant clicks 2 buttons – 12 automations do the rest." (use real iMile "before" times)
Rules: discuss each automation's design first, then build. Demo data only. Demo emails: only ONE real email
to Shahwaiz's own inbox; the other stations are logged (n8n run history / Google Sheet), never sent.
Claude writes n8n workflows as JSON files in `paydesk/n8n/` (import in n8n); Shahwaiz connects his own
accounts. Power Automate is built click-by-click together. After each workflow: explain every node simply.

## The 12 automations (build order)
| # | Automation | Tool | Status |
|---|---|---|---|
| 1 | Station emails EN + Arabic on approval (demo: 1 real email, rest logged) | n8n + Gemini + Gmail | **NEXT** |
| 2 | Approval by email: summary + Approve / Send back buttons | n8n | |
| 3 | Cashier replies "paid" → tracker updated + Teams/notice | Power Automate | |
| 4 | Traffic fine PDF/photo by email → Gemini reads → matched to driver | n8n + Gemini | |
| 5 | Month-end report: paid/unpaid/disputed + AI summary email + Power BI | n8n + Gemini + Power BI | |
| 6 | Month files arrive by email → uploaded + checked → accountant told | n8n | |
| 7 | SAB bank transfer file built + emailed to finance | n8n / Power Automate | |
| 8 | "Your salary is ready" message to drivers (demo: Telegram bot) | n8n | |
| 9 | AI payroll check: Gemini briefing on unusual salaries | n8n + Gemini | |
| 10 | Driver complaint triage: Gemini sorts + drafts reply | Power Automate / n8n + Gemini | |
| 11 | Missing-file chaser (file not in by the 2nd → reminder) | n8n schedule | |
| 12 | Daily reminder to stations that haven't confirmed paid | n8n schedule | |

Already built inside PayDesk (keep, becomes the data behind the automations): Stages 0–10, Outbox
(station emails saved, Excel per station), "Send a real copy" button + `N8N_WEBHOOK_URL` (will be reworked in automation 1).

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
- `backend\.env` has only these lines (Git ignores it; never share it, never paste other text into it):
  `GEMINI_API_KEY=...` and `N8N_WEBHOOK_URL=http://localhost:5678/webhook/paydesk-station-email`
- Power Automate: planned for Stage 12 (cashier replies "paid" → update Excel/Teams), not for the station email.
- Claude writes code files straight into the paydesk folder (folder access is granted). Shahwaiz runs the commands.
- PowerShell opens as Administrator in `system32`, so always `cd` to the paydesk folder first.
- Working style:
  - simple English, 2–3 steps at a time
  - one command per code block
  - always say which window to use
  - free tools only
