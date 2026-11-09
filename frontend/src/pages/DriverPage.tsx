import { useEffect, useState } from "react";
import { Link, useParams } from "react-router-dom";
import { api } from "../api";
import PayslipModal from "../components/PayslipModal";
import { FlagChip, sar } from "../format";
import { monthLabel } from "../types";
import type { DriverInfo } from "./DriversPage";

interface MonthRow {
  month_id: number;
  period: string;
  days_worked: number;
  prepaid_count: number;
  cod_count: number;
  gross: number;
  deductions: number;
  carried_forward: number;
  net: number;
  flags: string[];
}

function Field({ label, value }: { label: string; value: string | null }) {
  return (
    <div>
      <p className="text-xs uppercase tracking-wide text-slate-400">{label}</p>
      <p className="font-medium text-slate-800">{value ?? "—"}</p>
    </div>
  );
}

export default function DriverPage() {
  const { id } = useParams();
  const [d, setD] = useState<(DriverInfo & { months: MonthRow[] }) | null>(null);
  const [error, setError] = useState("");
  const [open, setOpen] = useState<number | null>(null);

  useEffect(() => {
    api<DriverInfo & { months: MonthRow[] }>(`/api/drivers/${id}`).then(setD).catch((e: Error) => setError(e.message));
  }, [id]);

  if (error) return <p className="text-red-600">{error}</p>;
  if (!d) return <p className="text-slate-500">Loading…</p>;

  return (
    <div>
      <Link to="/drivers" className="text-sm text-indigo-600 hover:underline">← Driver search</Link>
      <div className="mt-2 flex flex-wrap items-center gap-3">
        <h1 className="text-2xl font-bold text-slate-800">{d.name}</h1>
        {d.leaving_date ? (
          <span className="rounded-full bg-slate-100 px-3 py-1 text-sm text-slate-600">Left {d.leaving_date}</span>
        ) : (
          <span className="rounded-full bg-emerald-50 px-3 py-1 text-sm text-emerald-700">Active</span>
        )}
      </div>

      <div className="mt-5 grid grid-cols-2 gap-5 rounded-2xl border border-slate-200 bg-white p-5 shadow-sm md:grid-cols-4">
        <Field label="Driver ID" value={d.id} />
        <Field label="Station" value={`${d.station} (${d.station_code})`} />
        <Field label="Joined" value={d.joining_date} />
        <Field label="Salary paid by" value={d.payment_method === "Bank" ? `Bank ···· ${d.iban_last4 ?? ""}` : "Cash at station"} />
        <Field label="Phone" value={d.phone} />
        <Field label="City" value={d.city} />
      </div>

      <h2 className="mt-8 text-lg font-bold text-slate-800">Salary history</h2>
      <div className="mt-3 overflow-x-auto rounded-2xl border border-slate-200 bg-white">
        <table className="w-full text-sm">
          <thead className="bg-slate-50 text-left text-xs uppercase text-slate-500">
            <tr>
              <th className="p-3">Month</th><th>Days</th><th className="text-right">Prepaid</th><th className="text-right">COD</th>
              <th className="text-right">Gross</th><th className="text-right">Deducted</th><th className="text-right">Net</th>
              <th className="p-3">Flags</th>
            </tr>
          </thead>
          <tbody>
            {d.months.map((m) => (
              <tr key={m.month_id} onClick={() => setOpen(m.month_id)} className="cursor-pointer border-t border-slate-100 hover:bg-indigo-50/50">
                <td className="p-3 font-medium text-indigo-700">{monthLabel(m.period)}</td>
                <td>{m.days_worked}</td>
                <td className="text-right">{m.prepaid_count}</td>
                <td className="text-right">{m.cod_count}</td>
                <td className="text-right">{sar(m.gross)}</td>
                <td className="text-right text-red-600">{m.deductions ? `− ${sar(m.deductions)}` : ""}</td>
                <td className="text-right font-semibold">{sar(m.net)}</td>
                <td className="p-3"><div className="flex flex-wrap gap-1">{m.flags.map((f) => <FlagChip key={f} flag={f} />)}</div></td>
              </tr>
            ))}
            {d.months.length === 0 && (
              <tr><td colSpan={8} className="p-6 text-center text-slate-500">No salaries calculated yet.</td></tr>
            )}
          </tbody>
        </table>
      </div>
      <p className="mt-2 text-xs text-slate-400">Click a month to open the payslip.</p>

      {open !== null && <PayslipModal monthId={open} driverId={d.id} onClose={() => setOpen(null)} />}
    </div>
  );
}
