# PayDesk – n8n workflows

Import a file in n8n: **Overview → ⋮ (top right) → Import from File**.
Each workflow needs these credentials (pick them in the node after import):

| Credential | Type | Value |
|---|---|---|
| PayDesk key | Header Auth | Name `X-PayDesk-Key`, Value = `AUTOMATION_KEY` from `backend\.env` |
| Google Gemini(PaLM) Api | Google Gemini(PaLM) Api | your Gemini API key (the same one Invoice Autopilot uses) |
| Gmail | Gmail OAuth2 | the Invoice Autopilot demo Gmail |
| Google Sheets | Google Sheets OAuth2 | the same demo Google account |

## 01 – Station salary emails (`01-station-emails.json`)
Trigger: PayDesk calls `POST /webhook/paydesk-month-approved` when the finance manager approves a month.

Month approved → Get station emails → Prepare Arabic request → Gemini (Arabic, once) → Build emails →
for each station: Download Excel → Send with Gmail → Result per station → Log to Google Sheet → Report to PayDesk →
Run finished (once) → Summary to accountant.

Google Sheet "PayDesk – Station email log", row 1 headers:
`time | period | station_code | station | cashier_email | sent_to | drivers | cash_drivers | cash_total | bank_drivers | bank_total | arabic | status | gmail_id | error | email_id`

Notes (learned in the first real run, 13 Nov 2026):
- PayDesk URLs use `http://127.0.0.1:8001`, not `localhost` – on Windows n8n tried the IPv6 address and got "connection refused".
- The Sheet must be owned by / shared with the n8n Google account (invoiceautopilot.demo@gmail.com).
- Gemini Flash-Lite sometimes answers 503 "high demand": the node retries 5 times; if it still fails the emails go out in English only.
- After any change in n8n, click **Publish** again – the webhook only runs the published version.

## 03 – Telegram salary bot (`03-telegram-bot.json`) – automation 2
Trigger: every 3 seconds (local n8n can't receive Telegram webhooks, so it asks Telegram for new messages).
Credentials: **PayDesk key** + **Google Gemini(PaLM) Api**. No Telegram credential – the bot token stays in
`backend\.env` (`TELEGRAM_BOT_TOKEN=...`) and n8n gets it from PayDesk (`GET /api/automation/telegram/bot`).

Every 3 seconds → PayDesk: bot info → Telegram: new messages → Split messages → PayDesk: save offset (first, so no
message is answered twice) → PayDesk: what to answer → question? Gemini answers from HIS payslip only : PayDesk's
reply → Telegram: send. Side jobs: stop the button spinner, delete the `/link` message (PIN).
Second branch: PayDesk: answers to send → Telegram → PayDesk: answer delivered.

Settings: successful runs are NOT saved (it runs ~1,200 times an hour); failed runs are. To see every run while
testing: workflow **⋮ → Settings → Save successful production executions → Save**.

## 02 – Telegram salary messages (`02-telegram-salary-messages.json`) – automation 2
Trigger: PayDesk calls `POST /webhook/paydesk-salary-messages` when automation 1 finished all station emails
(`.env`: `N8N_SALARY_MESSAGES_URL=http://localhost:5678/webhook/paydesk-salary-messages`).
For every linked driver: Gemini writes the Arabic → one Telegram message (English + Arabic + "❌ Wrong" buttons) →
PayDesk marks it sent (never sent twice). Credentials: PayDesk key + Gemini.

## 04 – Cash received? (`04-cash-received.json`) – automation 3
Replaces the paper signature sheet. Credentials: PayDesk key + Gmail (already set in the file for this laptop).
- Every 10 s: PayDesk: drivers to ask (cashier clicked **Paid** on the Payday page) → Telegram "Did you receive
  SAR X?" with ✅ / ❌ buttons → PayDesk: mark asked. One reminder after 24 h (`CASH_REMINDER_HOURS`).
  The ✅ / ❌ taps come back through workflow 03 (the bot) – no change needed there.
- Every 10 s: drivers who said "wrong amount" → Gmail alert to the accountant → PayDesk: mark alerted.
- Every evening 8 pm (Riyadh): payday summary email (stations paid, confirmed, wrong amount, not started).
Successful runs are not saved (runs every 10 s); failed runs are.
