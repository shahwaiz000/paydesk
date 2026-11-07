import { useRef, useState } from "react";
import type { FileInfo, Issue } from "../types";

interface Props {
  step: number;
  title: string;
  hint: string;
  file: FileInfo | null;
  blockedReason: string | null;
  canEdit: boolean;
  onUpload: (file: File) => Promise<void>;
  onFix: (uploadId: number, issueIds: number[]) => Promise<void>;
}

const NICE_FIELD: Record<string, string> = {
  driver_id: "Driver ID", name: "Name", station_code: "Station code", station: "Station", city: "City",
  iqama_no: "Iqama no", joining_date: "Joining date", leaving_date: "Leaving date",
  payment_method: "Payment method", iban: "IBAN", phone: "Phone", plate_no: "Plate no",
  from_date: "From date", to_date: "To date", date: "Date", tracking_no: "Tracking no",
  order_type: "Order type", prepaid: "Prepaid", cod: "COD", kind: "Kind", type: "Type",
  amount: "Amount", reference: "Reference", note: "Note",
};

function SummaryChips({ summary }: { summary: Record<string, unknown> }) {
  const entries = Object.entries(summary).filter(([, v]) => typeof v !== "object");
  return (
    <div className="flex flex-wrap gap-2">
      {entries.map(([k, v]) => (
        <span key={k} className="rounded-lg bg-slate-100 px-2.5 py-1 text-xs text-slate-700">
          {k.replaceAll("_", " ")}: <b>{typeof v === "number" ? v.toLocaleString() : String(v)}</b>
        </span>
      ))}
    </div>
  );
}

function IssueRow({ issue, checked, onToggle }: { issue: Issue; checked: boolean; onToggle: () => void }) {
  const isError = issue.level === "error";
  const rows = issue.rows.length
    ? `Row ${issue.rows.slice(0, 5).join(", ")}${issue.count > 5 ? ` … (${issue.count.toLocaleString()} rows)` : ""}`
    : "";
  return (
    <div className={`flex gap-3 rounded-lg p-3 text-sm ${isError ? "bg-red-50" : "bg-amber-50"}`}>
      <span className={`mt-0.5 h-2 w-2 shrink-0 rounded-full ${isError ? "bg-red-500" : "bg-amber-500"}`} />
      <div className="flex-1">
        <p className={isError ? "text-red-800" : "text-amber-800"}>{issue.message}</p>
        {rows && <p className="text-xs text-slate-500 mt-0.5">{rows}</p>}
        {issue.fix && (
          <label className="mt-2 inline-flex cursor-pointer items-center gap-2 rounded-md bg-white px-2 py-1 text-xs font-medium text-indigo-700 ring-1 ring-indigo-200">
            <input type="checkbox" checked={checked} onChange={onToggle} />
            Suggested fix: {issue.fix.label}
          </label>
        )}
      </div>
    </div>
  );
}

export default function UploadCard({ step, title, hint, file, blockedReason, canEdit, onUpload, onFix }: Props) {
  const input = useRef<HTMLInputElement>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [selected, setSelected] = useState<number[]>([]);
  const [showAll, setShowAll] = useState(false);

  async function run(action: () => Promise<void>) {
    setBusy(true);
    setError("");
    try {
      await action();
      setSelected([]);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Something went wrong");
    } finally {
      setBusy(false);
    }
  }

  const status = file?.status;
  const badge =
    status === "imported"
      ? "bg-emerald-50 text-emerald-700"
      : status === "has_errors"
        ? "bg-red-50 text-red-700"
        : "bg-slate-100 text-slate-500";
  const badgeText = status === "imported" ? "Imported" : status === "has_errors" ? "Needs fixing" : "Not uploaded";

  const renamed = file ? Object.entries(file.column_map).filter(([orig, f]) => orig !== f) : [];
  const issues = file?.issues ?? [];
  const visible = showAll ? issues : issues.slice(0, 6);
  const fixable = issues.filter((i) => i.fix).map((i) => i.id);

  return (
    <div className={`rounded-2xl border bg-white p-5 shadow-sm ${blockedReason ? "border-slate-200 opacity-60" : "border-slate-200"}`}>
      <div className="flex items-start justify-between gap-4">
        <div className="flex gap-3">
          <span className="flex h-8 w-8 items-center justify-center rounded-full bg-indigo-600 text-sm font-bold text-white">
            {step}
          </span>
          <div>
            <h3 className="font-semibold text-slate-800">{title}</h3>
            <p className="text-sm text-slate-500">{hint}</p>
          </div>
        </div>
        <span className={`shrink-0 rounded-full px-3 py-1 text-xs font-medium ${badge}`}>{badgeText}</span>
      </div>

      {file && (
        <div className="mt-4 space-y-3">
          <p className="text-sm text-slate-600">
            <b>{file.filename}</b> · {file.rows.toLocaleString()} rows · by {file.uploaded_by}
            {file.error_count > 0 && <span className="text-red-600"> · {file.error_count.toLocaleString()} errors</span>}
            {file.warning_count > 0 && <span className="text-amber-600"> · {file.warning_count.toLocaleString()} warnings</span>}
          </p>
          <SummaryChips summary={file.summary} />
          {renamed.length > 0 && (
            <p className="text-xs text-slate-500">
              Columns matched automatically:{" "}
              {renamed.map(([orig, f]) => `"${orig}" → ${NICE_FIELD[f] ?? f}`).join(" · ")}
            </p>
          )}
          {issues.length > 0 && (
            <div className="space-y-2">
              {visible.map((i) => (
                <IssueRow
                  key={i.id}
                  issue={i}
                  checked={selected.includes(i.id)}
                  onToggle={() =>
                    setSelected((s) => (s.includes(i.id) ? s.filter((x) => x !== i.id) : [...s, i.id]))
                  }
                />
              ))}
              {issues.length > 6 && (
                <button onClick={() => setShowAll(!showAll)} className="text-sm text-indigo-600 hover:underline">
                  {showAll ? "Show less" : `Show all ${issues.length} problems`}
                </button>
              )}
            </div>
          )}
        </div>
      )}

      {error && <p className="mt-3 text-sm text-red-600">{error}</p>}

      {canEdit && (
        <div className="mt-4 flex flex-wrap gap-2">
          <input
            ref={input}
            type="file"
            accept=".xlsx,.xls,.csv"
            className="hidden"
            onChange={(e) => {
              const f = e.target.files?.[0];
              e.target.value = "";
              if (f) run(() => onUpload(f));
            }}
          />
          <button
            disabled={busy || !!blockedReason}
            onClick={() => input.current?.click()}
            className="rounded-lg bg-indigo-600 px-4 py-2 text-sm font-semibold text-white hover:bg-indigo-700 disabled:opacity-50"
          >
            {busy ? "Checking…" : file ? "Upload again" : "Upload file"}
          </button>
          {file?.status === "has_errors" && fixable.length > 0 && (
            <>
              <button
                disabled={busy}
                onClick={() => setSelected(selected.length === fixable.length ? [] : fixable)}
                className="rounded-lg border border-slate-300 px-3 py-2 text-sm hover:bg-slate-50"
              >
                {selected.length === fixable.length ? "Unselect fixes" : "Select all fixes"}
              </button>
              <button
                disabled={busy || selected.length === 0}
                onClick={() => run(() => onFix(file.id, selected))}
                className="rounded-lg bg-emerald-600 px-4 py-2 text-sm font-semibold text-white hover:bg-emerald-700 disabled:opacity-50"
              >
                Apply {selected.length || ""} fix{selected.length === 1 ? "" : "es"} & re-check
              </button>
            </>
          )}
          {blockedReason && <span className="self-center text-sm text-slate-500">{blockedReason}</span>}
        </div>
      )}
    </div>
  );
}
