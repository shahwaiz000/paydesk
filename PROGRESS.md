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
  - (the old "Send a real copy" button was replaced by automation 1 on 12 Nov)
- **Fixes:**
  - new columns are added to the database automatically on startup
  - the demo database (`paydesk-demo.db`) is now the default
- **Tests:** 26 passing (`pytest`)
- **Automation 1 – station emails (n8n + Gemini + Gmail):** built 12 Nov, see "Where we stopped"

## Where we stopped (13 Nov 2026)
- **Automation 1 works end to end** (tested 13 Nov with October 2026): Approve → PayDesk → n8n → Gemini Arabic →
  50 Gmail emails with Excel → Google Sheet log → PayDesk shows "50 of 50 sent" → summary email. **74 seconds**
  (Gmail sending is ~62 s of it, about 1.3 s per email – Google's speed, fine). Before: 2–3 hours by hand.
- n8n workflow: "PayDesk · 01 Station salary emails (EN + Arabic)", published (v3). File: `n8n/01-station-emails.json`.
- Google Sheet log: "PayDesk - Station email log" (made in shahwaizsulehri098, shared with invoiceautopilot.demo as Editor).
- Demo inbox + n8n Google account: invoiceautopilot.demo@gmail.com
- Fixes learned in the first run (already in the workflow file):
  - n8n must call PayDesk at `127.0.0.1:8001`, not `localhost` (Windows/IPv6 → "connection refused")
  - Sheet columns set explicitly; PayDesk report runs beside the Sheet (a Sheet error never blocks it)
  - Gemini Flash-Lite sometimes says 503 "high demand" → 5 retries; still failing = English-only email
  - After any change in n8n, click **Publish** again
- **To do later (Shahwaiz decided to wait):**
  - Make a new Gemini key (the old one was shown in a chat) → update `.env` and the n8n Gemini credential
  - Google Cloud project "Invoice Autopilot" (owned by the demo account): Google Auth Platform → Audience →
    **Publish app** (Testing → In production), then reconnect Gmail + Sheets in n8n once. Stops the 7-day sign-in expiry.
  - Invoice Autopilot workflows are broken (old Gmail credential deleted) – leave until needed
  - Demo video: record at the end of the project (fresh demo database, empty demo inbox, one clean run)
- Google Cloud project "Invoice Autopilot" is now **In production** (13 Nov) and Gmail + Sheets were reconnected in n8n
  → sign-ins no longer expire every 7 days. (Gemini key change still to do later.)
- **Automation 2 – PayDesk side built (14 Nov, 26 tests passing):**
  - Telegram bot made: **@paydesk_demo_shahwaiz_bot** (token kept private by Shahwaiz – goes only into n8n)
  - new tables: `telegram_links` (chat ↔ driver), `telegram_notices` (salary message sent, once per month),
    `automation_state` (Telegram offset); disputes got `source` (web/telegram) + `telegram_sent_at`
  - new file `backend/app/routers/telegram.py` – all endpoints n8n needs (see the top of that file)
  - bot commands: `/start`, `/link D10001 1234` (PIN message deleted, 5 wrong tries/hour), `/salary`, `/wrong`,
    `/cancel`, `/unlink`, `/help`; any other text = question → n8n asks Gemini (20 questions/hour)
  - "❌ Wrong" button under each deduction → bot asks the reason → dispute opens in PayDesk (source telegram)
  - accountant's answer → `GET /api/automation/telegram/answers` → n8n sends it on Telegram
  - after automation 1 finishes ("done"), PayDesk calls `N8N_SALARY_MESSAGES_URL` (new optional `.env` line)
  - tests no longer read the real `backend\.env` (they had called the real n8n) – `tests/conftest.py` blanks it
  - bot token lives ONLY in `backend\.env` as `TELEGRAM_BOT_TOKEN=...`; n8n gets it from `GET /api/automation/telegram/bot`
- **Automation 2 WORKS end to end (tested 14 Nov ~01:50 on Shahwaiz's own Telegram):**
  /start → /link D10001 1234 (PIN message deleted) → /salary → ❌ Wrong → reason → dispute in PayDesk (source telegram)
  → accountant answered in PayDesk → answer arrived on Telegram within seconds. Gemini answers questions (EN + Arabic).
  - n8n: "PayDesk · 03 Telegram salary bot" **published** (every 3 s, only failed runs saved)
  - n8n: "PayDesk · 02 Telegram salary messages" imported + credentials set, **NOT published yet** – publish it
    before the full demo run (it starts after automation 1 finishes)
  - `.env` has `TELEGRAM_BOT_TOKEN` (new token after /revoke) + `N8N_SALARY_MESSAGES_URL`
  - n8n login was reset on 14 Nov (`npx n8n@2.45.7 user-management:reset`) – new owner password saved in Chrome
  - Note: after tapping ❌ Wrong, the NEXT message is saved as the reason (send /cancel to stop)
- **14 Nov ~02:10 decision:** the post must stay simple – 3 clear problems only. Data-collection idea DROPPED.
  **Automation 3 = "Did the driver get his cash?"** (replaces paper signature sheets; Shahwaiz's own original wish).
- **Automation 3 WORKS end to end (tested 14 Nov ~02:20):** ruh-01 → Payday → Paid D10001 → Telegram question →
  ❌ + "1000 – …" → alert email arrived in the demo Gmail. Workflow 04 imported + **published**.
- Automation 3 details (27 tests passing):
  - table `cash_payments`; `backend/app/routers/payday.py` (Payday page API + n8n endpoints, see top of file)
  - frontend: new **Payday** page (`/payday`): cashier clicks **Paid** / "Mark all as paid";
    accountant sees every station + "wrong amount" problems (page refreshes every 10 s)
  - bot (workflow 03, no change): buttons `cy:<id>` ✅ received / `cn:<id>` ❌ → "how much did you receive?"
  - `n8n/04-cash-received.json`: ask driver (10 s) · 1 reminder after 24 h · Gmail alert on wrong amount ·
    8 pm summary email
- **Website redesigned (14 Nov ~03:00) – professional business look, looks only (no backend change):**
  - Shahwaiz did NOT like the Apple-style front page → removed. Opening PayDesk goes straight to sign-in.
  - normal sign-in page (centered box + demo accounts list)
  - left-side menu (Dashboard · Payroll months · Payday · Drivers · Driver questions; ☰ on phones)
  - dashboards per role: every number has a clear label + a short line under it (`components/StatCard.tsx`)
  - Inter font, white/grey + one blue, no emoji, no technical words on screen
  - checked with screenshots on laptop + phone; 27 tests pass; frontend builds without errors
  - then (Shahwaiz's feedback "too thin", "too many numbers", "no dark colors"): WHITE left menu with blue "P" logo,
    bold headings/numbers; dashboard = one blue banner (month + net) with an AI assistant chat picture +
    only 3 big cards (station emails · AI driver assistant · cash confirmations); same bold style on all pages
    and the sign-in page. Shahwaiz: "Now that looks good."
- **Next action (all 3 automations work):**
  1. Git save.
  2. Publish workflow 02 (salary message after automation 1) – then one FULL demo run: fresh demo database →
     approve October → 50 station emails → salary message on Telegram → question → ❌ Wrong → answer →
     Payday → Paid → ✅/❌. Record the demo video in that run (empty demo inbox first).
  3. Write the LinkedIn post (Sunday).
- **LinkedIn post (Sunday) – 3 problems:** 1) 50 station emails 2–3 h → 74 s · 2) "why was my salary cut?" →
  AI answers on Telegram · 3) paper signature sheets → drivers confirm cash with one tap.

## PowerShell windows (numbered in the order you open them)
- **Window 1 – commands** (`backend` folder): tests, Git, `.env`
- **Window 2 – backend**: `.venv\Scripts\Activate.ps1` → `python -m uvicorn app.main:app --reload --port 8001`
- **Window 3 – frontend** (`frontend` folder): `npm run dev`
- **Window 4 – n8n**: `npx n8n@2.45.7` → http://localhost:5678

## Done today (11 Nov 2026)
- Decided: **no CODesk link**. PayDesk stays separate. Shortages and advances keep coming from the adjustments file.
- Stage 8 – driver payslip page + "Why is my salary this?" AI chat.
- AI chat made faster: it uses the quick flash-lite model first and keeps the Google connection open.
  the backend window prints `[ai] <model> answered in X s` after every AI answer.
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
Rules: discuss each automation's design first, then build. Demo data only. Demo emails: all go to the demo
Gmail (`DEMO_INBOX`, the Invoice Autopilot account) – never to a real station.
Claude writes n8n workflows as JSON files in `paydesk/n8n/` (import in n8n); Shahwaiz connects his own
accounts. Power Automate is built click-by-click together. After each workflow: explain every node simply.

## The main automations (decided 13 Nov 2026 – only real problems, one LinkedIn post each)
The 12-automation list was cut down: people get confused by many small automations. Each one must be a real
pain Shahwaiz knows from iMile, with a true before → after. No made-up "before" times.

| # | Real problem | Tool | Status |
|---|---|---|---|
| 1 | Sending each station its salary list (2–3 h by hand) | n8n + Gemini + Gmail | ✅ done – 74 s |
| 2 | Drivers asking "why was my salary cut?" | n8n + Gemini + Telegram | ✅ done – works on Telegram |
| 3 | Paper signature sheets – "did the driver get his cash?" | n8n + Telegram + Gmail | ✅ done – works |
| – | Monthly data collection / chasing cashiers | – | dropped 14 Nov (keep the post simple) |
| – | Bank salary file (SAB) | ? | only if Shahwaiz learns the real process from the accountant |
| – | Approval by email | – | dropped (approval already works in PayDesk, not a real pain) |

### Automation 2 – "Why was my salary cut?" (agreed design)
Real "before" (Shahwaiz is a cashier): drivers ask the station cashier why salary was deducted; the cashier doesn't
know, says "ask the hub"; the hub doesn't reply; the driver never gets an answer.
1. **Salary message** (n8n workflow 02): after automation 1 finishes, every linked driver gets his salary explained
   on Telegram in English + Arabic – net, how it was earned, every deduction with its reason.
2. **Chat bot** (n8n workflow 03): driver asks "why 300 cut?" → n8n gets ONLY his payslip from PayDesk → Gemini
   answers from those facts, in the language he wrote (English/Arabic).
3. **"This is wrong"** → bot opens a dispute in PayDesk (Stage 9) → accountant answers in PayDesk → n8n sends the
   answer to the driver on Telegram.
- Safety: driver links his chat once with driver ID + PIN, sees only his own salary; no Iqama/IBAN to AI; AI never
  changes money; questions per hour limited.
- Demo: Telegram (free); real life would be WhatsApp (paid Business API). Only Shahwaiz's own Telegram is linked to
  1–2 demo drivers. Local n8n can't receive Telegram webhooks → n8n polls Telegram every few seconds.
- To build in PayDesk: Telegram link (chat id ↔ driver), automation endpoints (link with ID+PIN, payslip facts,
  create dispute, answered disputes to deliver), call n8n after automation 1 / when a dispute is answered.
- For the post: ask the accountant roughly how many deduction questions/calls he gets per month.

Already built inside PayDesk (keep, becomes the data behind the automations): Stages 0–10, Outbox
(station emails saved, Excel per station) – now used by automation 1.

## How to start (open Window 1, 2, 3 in this order; Window 4 = n8n)

**Window 2 – Backend** (leave it running, don't type in it)
```powershell
cd "C:\Users\Best Laptop\Documents\paydesk\backend"
```
```powershell
.venv\Scripts\Activate.ps1
```
```powershell
python -m uvicorn app.main:app --reload --port 8001
```

**Window 3 – Frontend** (leave it running, don't type in it)
```powershell
cd "C:\Users\Best Laptop\Documents\paydesk\frontend"
```
```powershell
npm run dev
```

**Window 1 – Commands** (tests, Git, scripts) – open this one first
```powershell
cd "C:\Users\Best Laptop\Documents\paydesk\backend"
```
```powershell
.venv\Scripts\python.exe -m pytest
```

Open **http://localhost:5174**

## Useful commands (Window 1, backend folder)
- Make demo data: `.venv\Scripts\python.exe scripts\generate_demo_data.py`
- Load September + October and calculate both: `.venv\Scripts\python.exe scripts\load_demo_months.py`
- Fresh demo database:
  1. Stop Window 2.
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
  `GEMINI_API_KEY=...`, `N8N_MONTH_APPROVED_URL=http://localhost:5678/webhook/paydesk-month-approved`,
  `AUTOMATION_KEY=...` (same value as the "PayDesk key" credential in n8n), `DEMO_INBOX=...` (demo Gmail)
- n8n workflows live in `paydesk/n8n/` (see `n8n/README.md` for credentials and the Google Sheet headers).
- Power Automate: planned for Stage 12 (cashier replies "paid" → update Excel/Teams), not for the station email.
- Claude writes code files straight into the paydesk folder (folder access is granted). Shahwaiz runs the commands.
- PowerShell opens as Administrator in `system32`, so always `cd` to the paydesk folder first.
- Working style:
  - simple English, 2–3 steps at a time
  - one command per code block
  - always say which window to use
  - free tools only
