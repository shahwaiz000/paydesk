// Shapes of payroll month data from the backend.

export type FileKind = "drivers" | "vehicles" | "deliveries" | "adjustments";

export interface Fix {
  action: "replace" | "drop_rows";
  label: string;
}

export interface Issue {
  id: number;
  level: "error" | "warning";
  message: string;
  column: string | null;
  rows: number[];
  count: number;
  fix: Fix | null;
}

export interface FileInfo {
  id: number;
  kind: FileKind;
  filename: string;
  status: "imported" | "has_errors" | "checking";
  uploaded_by: string;
  uploaded_at: string | null;
  rows: number;
  error_count: number;
  warning_count: number;
  column_map: Record<string, string>;
  issues: Issue[];
  summary: Record<string, unknown>;
}

export interface MonthSummary {
  id: number;
  period: string;
  status: string;
  files_imported: number;
  returned_note: string | null;
}

// ------------------------------------------------------------------ Approve & lock (Stage 10)

export const MONTH_STATUS: Record<string, { label: string; style: string }> = {
  draft: { label: "Uploading files", style: "bg-amber-50 text-amber-700" },
  ready: { label: "Ready to calculate", style: "bg-emerald-50 text-emerald-700" },
  calculated: { label: "Calculated", style: "bg-indigo-50 text-indigo-700" },
  submitted: { label: "Waiting for approval", style: "bg-violet-50 text-violet-700" },
  approved: { label: "Approved", style: "bg-slate-800 text-white" },
};

export const EDITABLE_MONTH = ["draft", "ready", "calculated"];

export interface ApprovalCheck {
  key: string;
  ok: boolean;
  blocking: boolean;
  approve_only?: boolean;
  text: string;
}

export interface Approval {
  status: string;
  submitted_by: string | null;
  submitted_at: string | null;
  approved_by: string | null;
  approved_at: string | null;
  returned_note: string | null;
  totals: { drivers: number; net: number; deductions: number; cash_net: number; bank_net: number };
  checks: ApprovalCheck[];
  events: { action: "submitted" | "approved" | "sent_back"; by: string; at: string | null; note: string | null; totals: { net?: number } }[];
}

export interface MonthDetail extends MonthSummary {
  files: Record<FileKind, FileInfo | null>;
}

export function monthLabel(period: string): string {
  const [y, m] = period.split("-").map(Number);
  return new Date(y, m - 1, 1).toLocaleString("en-GB", { month: "long", year: "numeric" });
}

// ------------------------------------------------------------------ Payslips

export interface PayslipLine {
  key: string;
  kind: "Deduction" | "Bonus";
  type: string;
  amount_due: number;
  amount_applied: number;
  carried: number;
  day: string | null;
  reference: string | null;
  note: string | null;
  plate_no: string | null;
  carried_from: string | null;
}

export interface Payslip {
  month_id: number;
  period: string;
  month_status: string;
  final: boolean;
  driver_id: string;
  name: string;
  station: string;
  payment_method: string;
  days_worked: number;
  full_month: boolean;
  fixed_pay: number;
  prepaid_count: number;
  prepaid_pay: number;
  cod_count: number;
  cod_pay: number;
  bonuses: number;
  gross: number;
  deductions_due: number;
  deductions_applied: number;
  carried_forward: number;
  net: number;
  previous_net: number | null;
  change_reason: string | null;
  flags: string[];
  joining_date: string;
  leaving_date: string | null;
  rates: { fixed_salary: number; prepaid_rate: number; cod_rate: number; proration_days: number; deduction_cap_pct: number };
  lines: PayslipLine[];
  daily: { day: string | null; prepaid: number; cod: number; earned: number }[];
}

/** What a driver gets on his own payslip page. */
export interface MyPayslip extends Payslip {
  in_words: string[];
  ai_enabled: boolean;
  disputes: Dispute[];
}

// ------------------------------------------------------------------ Disputes (Stage 9)

export type DisputeTopic = "deduction" | "deliveries" | "days" | "other";

export const TOPIC_LABELS: Record<DisputeTopic, string> = {
  deduction: "Deduction",
  deliveries: "Number of deliveries",
  days: "Days worked",
  other: "Something else",
};

export interface Dispute {
  id: number;
  month_id: number;
  period: string;
  topic: DisputeTopic;
  line_key: string | null;
  line: {
    type: string;
    amount: number;
    day: string | null;
    reference: string | null;
    note: string | null;
    carried_from: string | null;
  } | null;
  message: string;
  status: "open" | "accepted" | "rejected";
  reply: string | null;
  deduction_removed: boolean;
  created_at: string | null;
  answered_at: string | null;
}

/** What the accountant / finance manager sees in the inbox. */
export interface InboxDispute extends Dispute {
  driver_id: string;
  driver_name: string;
  station: string;
  station_code: string;
  answered_by: string | null;
  ai_draft: string | null;
  can_remove: boolean;
}

export interface MyPayslips {
  driver: {
    id: string;
    name: string;
    station: string;
    joining_date: string;
    payment_method: string;
    iban_last4: string | null;
  };
  months: {
    month_id: number;
    period: string;
    final: boolean;
    net: number;
    gross: number;
    deductions: number;
    carried_forward: number;
    days_worked: number;
    deliveries: number;
  }[];
  ai_enabled: boolean;
}

export function lineReason(l: PayslipLine): string {
  const bits = [l.reference, l.plate_no ? `plate ${l.plate_no}` : null, l.day, l.note].filter(Boolean);
  if (l.carried_from) bits.unshift(`carried from ${monthLabel(l.carried_from)}`);
  return bits.join(" · ");
}

// ------------------------------------------------------------------ Distribution (Stage 11)

export interface OutboxEmail {
  id: number;
  station_code: string;
  station: string;
  to: string;
  subject: string;
  attachment_name: string;
  drivers: number;
  cash_drivers: number;
  cash_total: number;
  bank_drivers: number;
  bank_total: number;
  status: "prepared" | "sent" | "failed";
  prepared_at: string | null;
  delivered_to: string | null;
  delivered_at: string | null;
  gmail_id: string | null;
  delivery_note: string | null;
  body?: string;
}

// Automation 1: n8n sends the station emails after approval
export interface EmailRun {
  status: "running" | "done" | "failed" | "not_connected" | null;
  by: string | null;
  started_at: string | null;
  finished_at: string | null;
  seconds: number | null;
  note: string | null;
}

export interface Outbox {
  period: string;
  month_status: string;
  stations: number;
  prepared: number;
  delivered: number;
  failed: number;
  waiting: number;
  cash_total: number;
  bank_total: number;
  run: EmailRun;
  can_run: boolean;
  n8n_ready: boolean;
  missing_setup: string[];
  demo_inbox: string | null;
  emails: OutboxEmail[];
}
