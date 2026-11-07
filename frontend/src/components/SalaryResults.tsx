import { useCallback, useEffect, useState } from "react";
import { api } from "../api";
import { FLAG_LABELS, FlagChip, sar } from "../format";
import PayslipModal from "./PayslipModal";

interface StationTotal {
  code: string;
  name: string;
  drivers: number;
  net: number;
  cash_needed: number;
  cash_drivers: number;
}

interface Summary {
  drivers: number;
  gross: number;
  deductions: number;
  carried_forward: number;
  net: number;
  fixed: number;
  prepaid: number;
  cod: number;
  bonuses: number;
  cash_net: number;
  bank_net: number;
  flags: Record<string, number>;
  stations: StationTotal[];
}

interface SalaryRow {
  driver_id: string;
  name: string;
  station: string;
  station_code: string;
  payment_method: string;
  days_worked: number;
  fixed_pay: number;
  prepaid_count: number;
  cod_count: number;
  bonuses: number;
  gross: number;
  deductions_applied: number;
  carried_forward: number;
  net: number;
  flags: string[];
}

const PAGE_SIZE = 50;

function Card({ label, value, sub }: { label: string; value: string; sub?: string }) {
  return (
    <div className="rounded-2xl border border-slate-200 bg-white p-4 shadow-sm">
      <p className="text-sm text-slate-500">{label}</p>
      <p className="mt-1 text-2xl font-bold text-slate-800">{value}</p>
      {sub && <p className="text-xs text-slate-400">{sub}</p>}
    </div>
  );
}

export default function SalaryResults({ monthId, refreshKey }: { monthId: number; refreshKey: number }) {
  const [summary, setSummary] = useState<Summary | null>(null);
  const [rows, setRows] = useState<SalaryRow[]>([]);
  const [total, setTotal] = useState(0);
  const [page, setPage] = useState(1);
  const [station, setStation] = useState("");
  const [payment, setPayment] = useState("");
  const [flag, setFlag] = useState("");
  const [q, setQ] = useState("");
  const [open, setOpen] = useState<string | null>(null);
  const [tab, setTab] = useState<"drivers" | "stations">("drivers");

  useEffect(() => {
    api<Summary>(`/api/months/${monthId}/summary`).then(setSummary).catch(() => setSummary(null));
  }, [monthId, refreshKey]);

  const loadRows = useCallback(() => {
    const params = new URLSearchParams({ page: String(page), size: String(PAGE_SIZE) });
    if (station) params.set("station", station);
    if (payment) params.set("payment", payment);
    if (flag) params.set("flag", flag);
    if (q.trim()) params.set("q", q.trim());
    api<{ total: number; items: SalaryRow[] }>(`/api/months/${monthId}/salaries?${params}`)
      .then((d) => {
        setRows(d.items);
        setTotal(d.total);
      })
      .catch(() => setRows([]));
  }, [monthId, page, station, payment, flag, q]);

  useEffect(() => {
    loadRows();
  }, [loadRows, refreshKey]);

  if (!summary || !summary.drivers) return null;
  const pages = Math.max(1, Math.ceil(total / PAGE_SIZE));
  const select = "rounded-lg border border-slate-300 bg-white px-3 py-2 text-sm";

  return (
    <div className="mt-8">
      <h2 className="text-xl font-bold text-slate-800">Salaries</h2>
      <div className="mt-4 grid grid-cols-2 gap-3 lg:grid-cols-5">
        <Card label="Drivers paid" value={summary.drivers.toLocaleString()} />
        <Card label="Gross" value={`SAR ${sar(summary.gross)}`}
              sub={`fixed ${sar(summary.fixed)} · deliveries ${sar(summary.prepaid + summary.cod)}`} />
        <Card label="Deducted" value={`SAR ${sar(summary.deductions)}`} sub={`${sar(summary.carried_forward)} carried to next month`} />
        <Card label="Net to pay" value={`SAR ${sar(summary.net)}`} />
        <Card label="Cash / Bank" value={`${sar(summary.cash_net)} / ${sar(summary.bank_net)}`} sub="cash at stations / SAB file" />
      </div>

      {Object.keys(summary.flags).length > 0 && (
        <div className="mt-4 flex flex-wrap gap-2">
          {Object.entries(summary.flags).map(([f, n]) => (
            <button
              key={f}
              onClick={() => { setFlag(flag === f ? "" : f); setPage(1); setTab("drivers"); }}
              className={`rounded-full ring-1 ${flag === f ? "ring-indigo-500" : "ring-transparent"}`}
            >
              <FlagChip flag={f} />
              <span className="mr-2 text-xs text-slate-500">{n}</span>
            </button>
          ))}
        </div>
      )}

      <div className="mt-6 flex gap-2 border-b border-slate-200">
        {(["drivers", "stations"] as const).map((t) => (
          <button
            key={t}
            onClick={() => setTab(t)}
            className={`-mb-px border-b-2 px-4 py-2 text-sm font-medium ${tab === t ? "border-indigo-600 text-indigo-700" : "border-transparent text-slate-500"}`}
          >
            {t === "drivers" ? "By driver" : "Station cash plan"}
          </button>
        ))}
      </div>

      {tab === "stations" && (
        <div className="mt-4 overflow-x-auto rounded-2xl border border-slate-200 bg-white">
          <table className="w-full text-sm">
            <thead className="bg-slate-50 text-left text-xs uppercase text-slate-500">
              <tr><th className="p-3">Station</th><th>Drivers</th><th>Cash drivers</th><th className="text-right">Cash needed</th><th className="p-3 text-right">Total net</th></tr>
            </thead>
            <tbody>
              {summary.stations.map((s) => (
                <tr key={s.code} className="border-t border-slate-100">
                  <td className="p-3"><b>{s.name}</b> <span className="text-slate-400">{s.code}</span></td>
                  <td>{s.drivers}</td>
                  <td>{s.cash_drivers}</td>
                  <td className="text-right font-semibold">SAR {sar(s.cash_needed)}</td>
                  <td className="p-3 text-right">SAR {sar(s.net)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      {tab === "drivers" && (
        <>
          <div className="mt-4 flex flex-wrap gap-2">
            <input
              placeholder="Search name or driver ID"
              value={q}
              onChange={(e) => { setQ(e.target.value); setPage(1); }}
              className="w-64 rounded-lg border border-slate-300 px-3 py-2 text-sm"
            />
            <select value={station} onChange={(e) => { setStation(e.target.value); setPage(1); }} className={select}>
              <option value="">All stations</option>
              {summary.stations.map((s) => <option key={s.code} value={s.code}>{s.name}</option>)}
            </select>
            <select value={payment} onChange={(e) => { setPayment(e.target.value); setPage(1); }} className={select}>
              <option value="">Cash & Bank</option>
              <option value="Cash">Cash</option>
              <option value="Bank">Bank</option>
            </select>
            <select value={flag} onChange={(e) => { setFlag(e.target.value); setPage(1); }} className={select}>
              <option value="">All drivers</option>
              {Object.entries(FLAG_LABELS).map(([k, v]) => <option key={k} value={k}>{v.label}</option>)}
            </select>
          </div>

          <div className="mt-3 overflow-x-auto rounded-2xl border border-slate-200 bg-white">
            <table className="w-full text-sm">
              <thead className="bg-slate-50 text-left text-xs uppercase text-slate-500">
                <tr>
                  <th className="p-3">Driver</th><th>Station</th><th>Pay</th><th>Days</th><th className="text-right">Fixed</th>
                  <th className="text-right">Prepaid</th><th className="text-right">COD</th><th className="text-right">Gross</th>
                  <th className="text-right">Deducted</th><th className="text-right">Net</th><th className="p-3">Flags</th>
                </tr>
              </thead>
              <tbody>
                {rows.map((r) => (
                  <tr key={r.driver_id} onClick={() => setOpen(r.driver_id)} className="cursor-pointer border-t border-slate-100 hover:bg-indigo-50/50">
                    <td className="p-3"><b>{r.name}</b><div className="text-xs text-slate-400">{r.driver_id}</div></td>
                    <td className="text-slate-600">{r.station}</td>
                    <td>{r.payment_method}</td>
                    <td>{r.days_worked}</td>
                    <td className="text-right">{sar(r.fixed_pay)}</td>
                    <td className="text-right">{r.prepaid_count}</td>
                    <td className="text-right">{r.cod_count}</td>
                    <td className="text-right">{sar(r.gross)}</td>
                    <td className="text-right text-red-600">{r.deductions_applied ? `− ${sar(r.deductions_applied)}` : ""}</td>
                    <td className="text-right font-semibold">{sar(r.net)}</td>
                    <td className="p-3"><div className="flex flex-wrap gap-1">{r.flags.map((f) => <FlagChip key={f} flag={f} />)}</div></td>
                  </tr>
                ))}
                {rows.length === 0 && (
                  <tr><td colSpan={11} className="p-6 text-center text-slate-500">No drivers match.</td></tr>
                )}
              </tbody>
            </table>
          </div>

          <div className="mt-3 flex items-center justify-between text-sm text-slate-600">
            <span>{total.toLocaleString()} drivers</span>
            <div className="flex items-center gap-2">
              <button disabled={page <= 1} onClick={() => setPage(page - 1)} className="rounded-lg border px-3 py-1 disabled:opacity-40">Previous</button>
              <span>Page {page} of {pages}</span>
              <button disabled={page >= pages} onClick={() => setPage(page + 1)} className="rounded-lg border px-3 py-1 disabled:opacity-40">Next</button>
            </div>
          </div>
        </>
      )}

      {open && <PayslipModal monthId={monthId} driverId={open} onClose={() => setOpen(null)} />}
    </div>
  );
}
