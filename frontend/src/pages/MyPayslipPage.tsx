import { useEffect, useState } from "react";
import { Link, useParams } from "react-router-dom";
import { api } from "../api";
import PayslipChat from "../components/PayslipChat";
import { StatusBadge, sar } from "../format";
import { lineReason, monthLabel, type MyPayslip } from "../types";

function Row({ label, detail, amount, bold, minus }: { label: string; detail?: string; amount: number; bold?: boolean; minus?: boolean }) {
  return (
    <div className={`flex justify-between gap-4 py-2 ${bold ? "font-semibold text-slate-900" : "text-slate-700"}`}>
      <span>
        {label}
        {detail && <span className="block text-xs font-normal text-slate-400 sm:ml-2 sm:inline">{detail}</span>}
      </span>
      <span className={`whitespace-nowrap ${minus ? "text-red-600" : ""}`}>
        {minus ? "− " : ""}
        {sar(amount)}
      </span>
    </div>
  );
}

function shortDate(iso: string): string {
  return new Date(iso + "T00:00:00").toLocaleDateString("en-GB", { weekday: "short", day: "numeric", month: "short" });
}

// The driver's full payslip for one month.
export default function MyPayslipPage() {
  const { monthId } = useParams();
  const [p, setP] = useState<MyPayslip | null>(null);
  const [error, setError] = useState("");

  useEffect(() => {
    api<MyPayslip>(`/api/me/payslips/${monthId}`).then(setP).catch((e: Error) => setError(e.message));
  }, [monthId]);

  if (error)
    return (
      <div className="mx-auto max-w-xl">
        <Link to="/" className="text-sm text-indigo-600 hover:underline">← My payslips</Link>
        <p className="mt-4 text-red-600">{error}</p>
      </div>
    );
  if (!p || p.month_id !== Number(monthId)) return <p className="text-slate-500">Loading…</p>;

  const deductions = p.lines.filter((l) => l.kind === "Deduction");
  const bonuses = p.lines.filter((l) => l.kind === "Bonus");
  const daily = p.daily.filter((d) => d.day);
  const best = daily.reduce((m, d) => Math.max(m, d.prepaid + d.cod), 0);

  return (
    <div className="mx-auto max-w-xl">
      <Link to="/" className="text-sm text-indigo-600 hover:underline">← My payslips</Link>

      <div className="mt-3 rounded-2xl bg-indigo-600 p-6 text-white shadow-sm">
        <div className="flex items-center justify-between">
          <span className="text-sm text-indigo-100">Payslip · {monthLabel(p.period)}</span>
          <StatusBadge final={p.final} light />
        </div>
        <p className="mt-2 text-4xl font-bold">SAR {sar(p.net)}</p>
        <p className="mt-1 text-sm text-indigo-100">
          {p.driver_id} · {p.station} · {p.payment_method === "Bank" ? "Bank transfer" : "Cash at your station"}
        </p>
        {p.previous_net !== null && (
          <p className="mt-2 text-sm text-indigo-100">Last month: SAR {sar(p.previous_net)}</p>
        )}
      </div>

      {!p.final && (
        <p className="mt-3 rounded-lg bg-amber-50 p-3 text-sm text-amber-800">
          This salary is not final yet. The payroll team may still change it before it is approved.
        </p>
      )}

      <div className="mt-6 rounded-2xl border border-slate-200 bg-white p-5">
        <h2 className="font-bold text-slate-800">Your salary in simple words</h2>
        <ul className="mt-2 space-y-1.5 text-sm text-slate-700">
          {p.in_words.map((s, i) => (
            <li key={i} className="flex gap-2">
              <span className="text-indigo-400">•</span>
              <span>{s}</span>
            </li>
          ))}
        </ul>
      </div>

      <div className="mt-4 rounded-2xl border border-slate-200 bg-white p-5">
        <p className="text-xs font-semibold uppercase tracking-wide text-slate-400">Earnings</p>
        <Row
          label="Fixed salary"
          detail={
            p.full_month
              ? "full month"
              : `${sar(p.rates.fixed_salary)} ÷ ${p.rates.proration_days} × ${p.days_worked} days`
          }
          amount={p.fixed_pay}
        />
        <Row label="Prepaid deliveries" detail={`${p.prepaid_count} × ${sar(p.rates.prepaid_rate)}`} amount={p.prepaid_pay} />
        <Row label="COD deliveries" detail={`${p.cod_count} × ${sar(p.rates.cod_rate)}`} amount={p.cod_pay} />
        {bonuses.map((b, i) => (
          <Row key={i} label={b.note || "Bonus"} detail={b.reference ?? undefined} amount={b.amount_applied} />
        ))}
        <div className="mt-1 border-t border-slate-100">
          <Row label="Total earned" amount={p.gross} bold />
        </div>
      </div>

      <div className="mt-4 rounded-2xl border border-slate-200 bg-white p-5">
        <p className="text-xs font-semibold uppercase tracking-wide text-slate-400">Deductions</p>
        {deductions.length === 0 && <p className="py-2 text-sm text-slate-500">No deductions this month 🎉</p>}
        {deductions.map((d, i) => (
          <div key={i} className="border-b border-slate-100 py-3 last:border-0">
            <div className="flex justify-between gap-4 text-slate-800">
              <span className="font-medium">{d.type}</span>
              <span className="whitespace-nowrap text-red-600">− {sar(d.amount_applied)}</span>
            </div>
            {lineReason(d) && <p className="mt-0.5 text-xs text-slate-500">{lineReason(d)}</p>}
            {d.carried > 0 && (
              <p className="mt-1 text-xs text-amber-700">
                {sar(d.amount_due)} due · {sar(d.amount_applied)} taken now · {sar(d.carried)} moves to next month
              </p>
            )}
          </div>
        ))}
        {deductions.length > 0 && (
          <div className="border-t border-slate-200">
            <Row label="Total deducted" amount={p.deductions_applied} bold minus={p.deductions_applied > 0} />
          </div>
        )}
        {p.carried_forward > 0 && (
          <p className="mt-2 rounded-lg bg-amber-50 p-3 text-xs text-amber-800">
            By law, at most {p.rates.deduction_cap_pct}% of what you earn can be deducted in one month. The rest (SAR{" "}
            {sar(p.carried_forward)}) will be deducted next month.
          </p>
        )}
      </div>

      <div className="mt-4 flex items-center justify-between rounded-2xl bg-slate-900 p-5 text-white">
        <span className="font-semibold">You receive</span>
        <span className="text-2xl font-bold">SAR {sar(p.net)}</span>
      </div>

      <PayslipChat key={p.month_id} monthId={p.month_id} enabled={p.ai_enabled} />

      {daily.length > 0 && (
        <details className="mt-6 rounded-2xl border border-slate-200 bg-white p-5">
          <summary className="cursor-pointer font-bold text-slate-800">
            Day by day <span className="text-sm font-normal text-slate-500">({daily.length} days with deliveries)</span>
          </summary>
          <table className="mt-3 w-full text-sm">
            <thead className="text-left text-xs uppercase text-slate-400">
              <tr>
                <th className="py-1">Date</th>
                <th className="text-right">Prepaid</th>
                <th className="text-right">COD</th>
                <th className="text-right">Earned</th>
              </tr>
            </thead>
            <tbody>
              {daily.map((d) => (
                <tr key={d.day} className="border-t border-slate-100">
                  <td className="py-1.5">
                    {shortDate(d.day!)}
                    {best > 0 && d.prepaid + d.cod === best && <span className="ml-1 text-xs text-emerald-600">best day</span>}
                  </td>
                  <td className="text-right">{d.prepaid}</td>
                  <td className="text-right">{d.cod}</td>
                  <td className="text-right">{sar(d.earned)}</td>
                </tr>
              ))}
            </tbody>
            <tfoot className="border-t-2 border-slate-200 font-semibold">
              <tr>
                <td className="py-1.5">Total</td>
                <td className="text-right">{p.prepaid_count}</td>
                <td className="text-right">{p.cod_count}</td>
                <td className="text-right">{sar(p.prepaid_pay + p.cod_pay)}</td>
              </tr>
            </tfoot>
          </table>
          <p className="mt-2 text-xs text-slate-400">Earned = delivery pay only. The fixed salary is added once for the month.</p>
        </details>
      )}
    </div>
  );
}
