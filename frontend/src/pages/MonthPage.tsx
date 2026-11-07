import { useCallback, useEffect, useState } from "react";
import { Link, useParams } from "react-router-dom";
import { api } from "../api";
import { useAuth } from "../auth";
import UploadCard from "../components/UploadCard";
import { monthLabel, type FileKind, type MonthDetail } from "../types";

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

  const load = useCallback(() => {
    api<MonthDetail>(`/api/months/${id}`).then(setMonth).catch((e: Error) => setError(e.message));
  }, [id]);
  useEffect(load, [load]);

  if (error) return <p className="text-red-600">{error}</p>;
  if (!month) return <p className="text-slate-500">Loading…</p>;

  const imported = (k: FileKind) => month.files[k]?.status === "imported";

  async function upload(kind: FileKind, file: File) {
    const form = new FormData();
    form.append("file", file);
    setMonth(await api<MonthDetail>(`/api/months/${id}/upload/${kind}`, { method: "POST", body: form }));
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
        {month.status === "ready" && (
          <span className="rounded-full bg-emerald-50 px-4 py-2 text-sm font-semibold text-emerald-700">
            ✓ All files clean – ready to calculate salaries
          </span>
        )}
      </div>

      <div className="mt-6 grid gap-4">
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
              canEdit={user?.role === "accountant" && month.status !== "locked"}
              onUpload={(f) => upload(s.kind, f)}
              onFix={fix}
            />
          );
        })}
      </div>
    </div>
  );
}
