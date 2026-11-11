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
