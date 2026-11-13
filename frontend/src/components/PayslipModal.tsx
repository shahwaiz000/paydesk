import { useEffect, useState } from "react";
import { api } from "../api";
import { FlagChip, sar } from "../format";
import { lineReason, monthLabel, type Payslip } from "../types";

function Row({ label, detail, amount, bold, minus }: { label: string; detail?: string; amount: number; bold?: boolean; minus?: boolean }) {
  return (
    <div className={`flex justify-between gap-4 py-1.5 ${bold ? "font-semibold text-slate-900" : "text-slate-700"}`}>
      <span>
        {label}
        {detail && <span className="ml-2 text-xs text-slate-400">{detail}</span>}
      </span>
      <span className={minus ? "text-red-600" : ""}>
        {minus ? "− " : ""}
        {sar(amount)}
      </span>
    </div>
  );
}

export default function PayslipModal({ monthId, driverId, onClose }: { monthId: number; driverId: string; onClose: () => void }) {
  const [p, setP] = useState<Payslip | null>(null);
  const [error, setError] = useState("");

  useEffect(() => {
    api<Payslip>(`/api/months/${monthId}/salaries/${driverId}`).then(setP).catch((e: Error) => setError(e.message));
  }, [monthId, driverId]);

  const deductions = p?.lines.filter((l) => l.kind === "Deduction") ?? [];
  const bonuses = p?.lines.filter((l) => l.kind === "Bonus") ?? [];

  return (
    <div className="fixed inset-0 z-50 flex justify-end bg-slate-900/40" onClick={onClose}>
      <div className="h-full w-full max-w-lg overflow-y-auto bg-white p-6 shadow-xl" onClick={(e) => e.stopPropagation()}>
        <div className="flex items-start justify-between">
          <div>
            <p className="text-sm text-slate-500">Payslip · {p ? monthLabel(p.period) : ""}</p>
            <h2 className="text-xl font-bold text-slate-800">{p?.name ?? driverId}</h2>
            {p && (
              <p className="text-sm text-slate-500">
                {p.driver_id} · {p.station} · {p.payment_method === "Bank" ? "Bank transfer" : "Cash at station"}
              </p>
            )}
          </div>
          <button onClick={onClose} className="rounded-lg px-2 py-1 text-slate-500 hover:bg-slate-100"aria-label="Close">✕</button>
        </div>

        {error && <p className="mt-4 text-red-600">{error}</p>}
        {!p && !error && <p className="mt-4 text-slate-500">Loading…</p>}

        {p && (
          <>
            {p.flags.length > 0 && (
              <div className="mt-3 flex flex-wrap gap-1">{p.flags.map((f) => <FlagChip key={f} flag={f} />)}</div>
            )}

            <div className="mt-5 rounded-xl border border-slate-200 p-4">
              <p className="mb-1 text-xs font-semibold uppercase tracking-wide text-slate-400">Earnings</p>
              <Row
                label="Fixed salary"
                detail={p.full_month ? "full month" : `${sar(p.rates.fixed_salary)} ÷ ${p.rates.proration_days} × ${p.days_worked} days`}
                amount={p.fixed_pay}
              />
              <Row label="Prepaid deliveries" detail={`${p.prepaid_count} × ${p.rates.prepaid_rate}`} amount={p.prepaid_pay} />
              <Row label="COD deliveries" detail={`${p.cod_count} × ${p.rates.cod_rate}`} amount={p.cod_pay} />
              {bonuses.map((b, i) => (
                <Row key={i} label={b.note || "Bonus"} detail={b.reference ?? undefined} amount={b.amount_applied} />
              ))}
              <div className="mt-1 border-t border-slate-100 pt-1">
                <Row label="Gross" amount={p.gross} bold />
              </div>
            </div>

            <div className="mt-4 rounded-xl border border-slate-200 p-4">
              <p className="mb-1 text-xs font-semibold uppercase tracking-wide text-slate-400">Deductions</p>
              {deductions.length === 0 && <p className="py-1.5 text-sm text-slate-500">No deductions this month</p>}
              {deductions.map((d, i) => (
                <div key={i} className="py-1.5">
                  <div className="flex justify-between gap-4 text-slate-700">
                    <span>{d.type}</span>
                    <span className="text-red-600">− {sar(d.amount_applied)}</span>
                  </div>
                  <p className="text-xs text-slate-400">{lineReason(d)}</p>
                  {d.carried > 0 && (
                    <p className="text-xs text-amber-700">
                      {sar(d.amount_due)} due · {sar(d.carried)} moved to next month (deduction limit {p.rates.deduction_cap_pct}%)
                    </p>
                  )}
                </div>
              ))}
              <div className="mt-1 border-t border-slate-100 pt-1">
                <Row label="Total deducted" amount={p.deductions_applied} bold minus={p.deductions_applied > 0} />
              </div>
            </div>

            <div className="mt-4 flex items-center justify-between rounded-xl bg-indigo-600 p-4 text-white">
              <span className="font-semibold">Net salary</span>
              <span className="text-2xl font-semibold">SAR {sar(p.net)}</span>
            </div>
            {p.carried_forward > 0 && (
              <p className="mt-2 text-sm text-amber-700">SAR {sar(p.carried_forward)} will be deducted next month.</p>
            )}

            {p.daily.length > 0 && p.daily[0].day && (
              <details className="mt-5">
                <summary className="cursor-pointer text-sm font-medium text-indigo-700">
                  Daily deliveries ({p.daily.length} working days)
                </summary>
                <table className="mt-2 w-full text-sm">
                  <thead className="text-left text-xs text-slate-400">
                    <tr><th className="py-1">Date</th><th>Prepaid</th><th>COD</th></tr>
                  </thead>
                  <tbody>
                    {p.daily.map((d) => (
                      <tr key={d.day} className="border-t border-slate-100">
                        <td className="py-1">{d.day}</td><td>{d.prepaid}</td><td>{d.cod}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </details>
            )}
          </>
        )}
      </div>
    </div>
  );
}
