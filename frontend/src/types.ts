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
