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
