import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { api } from "../api";
import { useAuth } from "../auth";
import { MONTH_STATUS, monthLabel, type MonthSummary } from "../types";


export default function MonthsPage() {
  const { user } = useAuth();
  const [months, setMonths] = useState<MonthSummary[]>([]);
  const [period, setPeriod] = useState("");
  const [error, setError] = useState("");

  function load() {
    api<MonthSummary[]>("/api/months").then(setMonths).catch((e: Error) => setError(e.message));
  }
  useEffect(load, []);

  async function create() {
    setError("");
    try {
      await api("/api/months", { method: "POST", body: JSON.stringify({ period }) });
      setPeriod("");
      load();
    } catch (e) {
      setError(e instanceof Error ? e.message : "Could not create month");
    }
  }

  return (
    <div>
      <div className="flex items-end justify-between gap-4 flex-wrap">
        <div>
          <h1 className="text-2xl font-bold text-slate-800">Payroll months</h1>
          <p className="text-slate-500 mt-1">Upload each month's 4 files, then calculate salaries.</p>
        </div>
        {user?.role === "accountant" && (
          <div className="flex gap-2">
            <input
              type="month"
              value={period}
              onChange={(e) => setPeriod(e.target.value)}
              className="rounded-lg border border-slate-300 px-3 py-2"
            />
            <button
              onClick={create}
              disabled={!period}
              className="rounded-lg bg-indigo-600 px-4 py-2 font-semibold text-white hover:bg-indigo-700 disabled:opacity-50"
            >
              New month
            </button>
          </div>
        )}
      </div>
      {error && <p className="mt-4 text-red-600">{error}</p>}

      <div className="mt-6 grid gap-3">
        {months.map((m) => (
          <Link
            key={m.id}
            to={`/months/${m.id}`}
            className="flex items-center justify-between rounded-2xl border border-slate-200 bg-white p-5 shadow-sm hover:border-indigo-300"
          >
            <div>
              <p className="text-lg font-semibold text-slate-800">{monthLabel(m.period)}</p>
              <p className="text-sm text-slate-500">{m.files_imported} of 4 files imported</p>
            </div>
            <span className={`rounded-full px-3 py-1 text-sm font-medium ${MONTH_STATUS[m.status]?.style ?? ""}`}>
              {MONTH_STATUS[m.status]?.label ?? m.status}
            </span>
          </Link>
        ))}
        {months.length === 0 && !error && <p className="text-slate-500">No months yet.</p>}
      </div>
    </div>
  );
}
