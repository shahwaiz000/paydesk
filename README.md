# PayDesk – AI Driver Payroll Automation

> *"Why was my salary cut?"*
> A driver asked me this at my cash desk. I had no answer – I handle cash, not payroll.
> So I built a system that answers him.

PayDesk is a payroll system for a last-mile delivery company with **750 drivers in 50 stations**.
The web app is only the control panel. **The real work is done by automations** (n8n + Gemini AI + Telegram + Gmail).

🎥 **Demo video:** [LinkedIn post](https://www.linkedin.com/feed/update/urn:li:activity:7528065808594341888/)
⚠️ All data in this project is **fake demo data**. No real salaries or driver details.

---

## The 3 problems it solves

| Problem (before) | What PayDesk does (after) |
|---|---|
| Salary emails were sent to 50 stations **by hand, one by one** (2–3 hours) | When the finance manager approves the month, **all 50 station emails go out automatically** – English + Arabic, with an Excel sheet each. About **1 minute**. |
| Drivers asked **"Why was my salary cut?"** and nobody near them could explain | Each driver gets his salary on **Telegram**. He can ask the **AI assistant** any question, in English or Arabic. It explains every deduction from **his own payslip only**. If he says a deduction is wrong, a case opens for the payroll team. |
| Cash salaries were proven with **paper signature sheets** that got lost | When the cashier pays a driver, the driver gets a Telegram message: **"Did you receive your full salary?"** If he says no, finance gets an **alert email within minutes**. |

---

## The automations

### 1. Station salary emails (`n8n/01-station-emails.json`)
Month approved → PayDesk calls n8n → Gemini writes the Arabic text (once) → 50 emails with Excel via Gmail →
every email logged in a Google Sheet → PayDesk shows "50 of 50 sent" → summary email to the accountant.
**Tested: 50 emails in 74 seconds.**

### 2. AI salary assistant on Telegram (`n8n/02-…`, `n8n/03-telegram-bot.json`)
- Driver links his account once (`/link` + PIN – the PIN message is deleted right away).
- After the station emails, every linked driver gets his salary summary.
- Questions go to Gemini with **only that driver's payslip** – no name, Iqama or IBAN is sent to the AI.
- ❌ **Wrong** button under each deduction → the driver writes why → a dispute opens in PayDesk →
  the accountant answers → the answer arrives on Telegram.

### 3. "Did the driver get his cash?" (`n8n/04-cash-received.json`)
Cashier clicks **Paid** → driver is asked on Telegram → ✅ received / ❌ wrong amount →
wrong amount = alert email to finance · one reminder after 24 hours · daily summary email at 8 pm.

---

## Inside the control panel
- Upload monthly files (drivers, vehicles, deliveries, adjustments) with automatic checks and one-click fixes
- Salary engine: pro-rata days, per-delivery pay, bonuses, deductions **capped at 50%** (Saudi Labor Law Art. 93), carry-over
- AI reads traffic-fine PDFs/photos and matches them to the right driver by plate + date
- AI flags salaries that changed more than 30% and explains why
- Approval flow: Calculated → Sent for approval → Approved & locked
- Roles: payroll accountant, finance manager, station cashier, driver

---

## Tools used
| Part | Tool |
|---|---|
| Automations | **n8n** |
| AI | **Google Gemini** |
| Driver chat | **Telegram Bot API** |
| Emails + log | **Gmail**, **Google Sheets** |
| Backend | Python, **FastAPI**, SQLAlchemy, SQLite |
| Control panel | React, TypeScript, Tailwind |
| Tests | pytest (27 tests) |

---

## How a company could start using it
1. **Pilot with 1–2 stations** – run PayDesk next to the current process for one month and compare.
2. **Connect the company's systems** – read deliveries from the TMS instead of uploading files.
3. **Use the company's own channels** – company email (SMTP) or Lark/WhatsApp instead of Gmail/Telegram.
4. **Roll out to all stations** once the pilot numbers match.

---

## Run it locally
```bash
# backend (port 8001)
cd backend
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
uvicorn app.main:app --port 8001

# frontend (port 5174)
cd frontend
npm install
npm run dev

# n8n
npx n8n@2.45.7
```
Import the workflows from the `n8n/` folder – setup notes are in [`n8n/README.md`](n8n/README.md).

---

**Built by Shahwaiz Bilal** – Finance Operations, Riyadh ·
[LinkedIn](https://www.linkedin.com/in/shahwaiz-bilal-360baa302/) · [GitHub](https://github.com/shahwaiz000)
