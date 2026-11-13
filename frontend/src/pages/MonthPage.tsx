import { useCallback, useEffect, useState } from "react";
import { Link, useParams } from "react-router-dom";
import { api } from "../api";
import { useAuth } from "../auth";
import ApprovalCard from "../components/ApprovalCard";
import DistributionCard from "../components/DistributionCard";
import FinesCard from "../components/FinesCard";
import SalaryResults from "../components/SalaryResults";
import UploadCard from "../components/UploadCard";
import { EDITABLE_MONTH, MONTH_STATUS, monthLabel, type FileKind, type MonthDetail } from "../types";

const STEPS: { kind: FileKind; title: string; hint: string; needs: FileKind[] }[] = [
  { kind: "drivers", title: "Driver list", hint: "ID, name, station, joining date, Cash/Bank, IBAN", needs: [] },
  { kind: "vehicles", title: "Vehicle assignments", hint: "Who drove which plate, and when (for traffic fines)", needs: ["drivers"] },
  { kind: "deliveries", title: "Delivery export", hint: "One row per order, or prepaid/COD totals per driver", needs: ["drivers"] },
  { kind: "adjustments", title: "Deductions & bonuses", hint: "Fines, lost parcels, shortage, advances, other, bonus", needs: ["drivers", "vehicles"] },
];

const NAMES: Record<FileKind, string> = {
  drivers: "driver list", vehicles: "vehicle file", deliveries: "delivery export", adjustments: "deductions file",
};

export default function MonthPage() {
  const { id } = useParams();
  const { user } = useAuth();
  const [month, setMonth] = useState<MonthDetail | null>(null);
  const [error, setError] = useState("");
  const [calcBusy, setCalcBusy] = useState(false);
  const [calcError, setCalcError] = useState("");
  const [refreshKey, setRefreshKey] = useState(0);

  const load = useCallback(() => {
    api<MonthDetail>(`/api/months/${id}`).then(setMonth).catch((e: Error) => setError(e.message));
  }, [id]);
  useEffect(load, [load]);

  if (error) return <p className="text-red-600">{error}</p>;
  if (!month) return <p className="text-slate-500">Loading…</p>;

  const imported = (k: FileKind) => month.files[k]?.status === "imported";
  const editable = EDITABLE_MONTH.includes(month.status);
  const hasSalaries = ["calculated", "submitted", "approved"].includes(month.status);

  async function upload(kind: FileKind, file: File) {
    const form = new FormData();
    form.append("file", file);
    setMonth(await api<MonthDetail>(`/api/months/${id}/upload/${kind}`, { method: "POST", body: form }));
  }

  async function calculate() {
    setCalcBusy(true);
    setCalcError("");
    try {
      await api(`/api/months/${id}/calculate`, { method: "POST" });
      load();
      setRefreshKey((k) => k + 1);
    } catch (e) {
      setCalcError(e instanceof Error ? e.message : "Calculation failed");
    } finally {
      setCalcBusy(false);
    }
  }

  async function fix(uploadId: number, issueIds: number[]) {
    setMonth(
      await api<MonthDetail>(`/api/months/${id}/uploads/${uploadId}/fix`, {
        method: "POST",
        body: JSON.stringify({ issue_ids: issueIds }),
      }),
    );
  }

  return (
    <div>
      <Link to="/months" className="text-sm text-indigo-600 hover:underline">← All months</Link>
      <div className="mt-2 flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold text-slate-800">{monthLabel(month.period)}</h1>
          <p className="text-slate-500 mt-1">{month.files_imported} of 4 files imported</p>
        </div>
        {!editable && (
          <span className={`rounded-full px-4 py-2 text-sm font-semibold ${MONTH_STATUS[month.status]?.style ?? ""}`}>
            {MONTH_STATUS[month.status]?.label ?? month.status}
          </span>
        )}
        {(month.status === "ready" || month.status === "calculated") && (
          <div className="flex items-center gap-3">
            <span className="rounded-full bg-emerald-50 px-4 py-2 text-sm font-semibold text-emerald-700">
              {month.status === "ready" ? "All files are clean – ready to calculate" : "Salaries calculated"}
            </span>
            {user?.role === "accountant" && (
              <button
                onClick={calculate}
                disabled={calcBusy}
                className="rounded-lg bg-indigo-600 px-4 py-2 font-semibold text-white hover:bg-indigo-700 disabled:opacity-50"
              >
                {calcBusy ? "Calculating…" : month.status === "ready" ? "Calculate salaries" : "Recalculate"}
              </button>
            )}
          </div>
        )}
      </div>

      {calcError && <p className="mt-3 text-red-600">{calcError}</p>}

      {hasSalaries && (
        <ApprovalCard
          monthId={month.id}
          refreshKey={refreshKey}
          onChanged={() => {
            load();
            setRefreshKey((k) => k + 1);
          }}
        />
      )}

      {month.status === "approved" && <DistributionCard monthId={month.id} refreshKey={refreshKey} />}

      {hasSalaries && <SalaryResults monthId={month.id} refreshKey={refreshKey} />}

      {user?.role === "accountant" && (month.status === "ready" || month.status === "calculated") && (
        <FinesCard monthId={month.id} onAdded={load} />
      )}

      <h2 className="mt-10 text-xl font-bold text-slate-800">Month files</h2>
      <div className="mt-4 grid gap-4">
        {STEPS.map((s, i) => {
          const missing = s.needs.filter((n) => !imported(n));
          return (
            <UploadCard
              key={s.kind}
              step={i + 1}
              title={s.title}
              hint={s.hint}
              file={month.files[s.kind]}
              blockedReason={missing.length ? `Upload the ${missing.map((m) => NAMES[m]).join(" and ")} first` : null}
              canEdit={user?.role === "accountant" && editable}
              onUpload={(f) => upload(s.kind, f)}
              onFix={fix}
            />
          );
        })}
      </div>
    </div>
  );
}
