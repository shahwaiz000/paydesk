import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { api } from "../api";
import { StatusBadge, sar } from "../format";
import { monthLabel, type MyPayslips } from "../types";

// The driver's home page: his details and one card per month.
export default function MyPayslipsPage() {
  const [data, setData] = useState<MyPayslips | null>(null);
  const [error, setError] = useState("");

  useEffect(() => {
    api<MyPayslips>("/api/me/payslips").then(setData).catch((e: Error) => setError(e.message));
  }, []);

  if (error) return <p className="text-red-600">{error}</p>;
  if (!data) return <p className="text-slate-500">Loading…</p>;

  const d = data.driver;
  const [latest, ...older] = data.months;

  return (
    <div className="mx-auto max-w-xl">
      <h1 className="text-2xl font-bold text-slate-800">Hello, {d.name}</h1>
      <p className="mt-1 text-sm text-slate-500">
        {d.id} · {d.station} · {d.payment_method === "Bank" ? `Bank ···· ${d.iban_last4 ?? ""}` : "Cash at station"}
      </p>

      {!latest && (
        <div className="mt-6 rounded-2xl border border-dashed border-slate-300 bg-white p-6 text-slate-500">
          No payslips yet. Your payslip appears here when the payroll team has calculated the month.
        </div>
      )}

      {latest && (
        <Link
          to={`/payslips/${latest.month_id}`}
          className="mt-6 block rounded-2xl bg-indigo-600 p-6 text-white shadow-sm hover:bg-indigo-700"
        >
          <div className="flex items-center justify-between">
            <span className="text-sm text-indigo-100">{monthLabel(latest.period)}</span>
            <StatusBadge final={latest.final} light />
          </div>
          <p className="mt-2 text-4xl font-bold">SAR {sar(latest.net)}</p>
          <p className="mt-2 text-sm text-indigo-100">
            Earned {sar(latest.gross)} · Deducted {sar(latest.deductions)} · {latest.deliveries} deliveries in{" "}
            {latest.days_worked} days
          </p>
          {latest.carried_forward > 0 && (
            <p className="mt-1 text-sm text-amber-200">SAR {sar(latest.carried_forward)} moves to next month</p>
          )}
          <p className="mt-4 text-sm font-semibold">See full payslip →</p>
        </Link>
      )}

      {older.length > 0 && (
        <>
          <h2 className="mt-8 text-lg font-bold text-slate-800">Past months</h2>
          <div className="mt-3 divide-y divide-slate-100 rounded-2xl border border-slate-200 bg-white">
            {older.map((m) => (
              <Link
                key={m.month_id}
                to={`/payslips/${m.month_id}`}
                className="flex items-center justify-between px-5 py-4 hover:bg-slate-50"
              >
                <div>
                  <p className="font-medium text-slate-800">{monthLabel(m.period)}</p>
                  <p className="text-xs text-slate-500">
                    {m.deliveries} deliveries · deducted {sar(m.deductions)}
                  </p>
                </div>
                <div className="text-right">
                  <p className="font-semibold text-slate-800">SAR {sar(m.net)}</p>
                  <StatusBadge final={m.final} />
                </div>
              </Link>
            ))}
          </div>
        </>
      )}
    </div>
  );
}
