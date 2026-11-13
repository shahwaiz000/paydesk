import { useCallback, useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { api } from "../api";
import { useAuth } from "../auth";
import { sar } from "../format";
import type { Outbox } from "../types";

function when(iso: string | null): string {
  if (!iso) return "";
  return new Date(iso).toLocaleString("en-GB", { day: "numeric", month: "short", hour: "2-digit", minute: "2-digit" });
}

// Automation 1: when the month is approved, n8n sends the salary email to every station by itself.
// This card only shows what n8n is doing (refreshes every 3 seconds while it runs).
export default function DistributionCard({ monthId, refreshKey }: { monthId: number; refreshKey: number }) {
  const { user } = useAuth();
  const [box, setBox] = useState<Outbox | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");

  const load = useCallback(() => {
    api<Outbox>(`/api/months/${monthId}/outbox`).then(setBox).catch((e: Error) => setError(e.message));
  }, [monthId]);
  useEffect(load, [load, refreshKey]);

  const running = box?.run.status === "running";
  useEffect(() => {
    if (!running) return;
    const t = setInterval(load, 3000);
    return () => clearInterval(t);
  }, [running, load]);

  async function runAgain() {
    setBusy(true);
    setError("");
    try {
      setBox(await api<Outbox>(`/api/months/${monthId}/outbox/run`, { method: "POST" }));
    } catch (e) {
      setError(e instanceof Error ? e.message : "Could not start the automation");
    } finally {
      setBusy(false);
    }
  }

  if (!box) return error ? <p className="mt-6 text-red-600">{error}</p> : null;
  const { run } = box;
  const total = box.prepared || box.stations;
  const pct = total ? Math.round((box.delivered / total) * 100) : 0;
  const done = run.status === "done";

  const headline =
    run.status === "running"
      ? `Sending… ${box.delivered} of ${total} stations`
      : done
        ? `${box.delivered} of ${total} station emails sent${run.seconds != null ? ` in ${run.seconds} seconds` : ""}`
        : run.status === "failed"
          ? `${box.delivered} of ${total} sent – sending stopped`
          : run.status === "not_connected"
            ? "Emails are ready and waiting to be sent"
            : `${total} station emails prepared`;

  return (
    <div className={`mt-6 rounded-2xl border p-5 ${done ? "border-emerald-200 bg-emerald-50/40" : "border-slate-200 bg-white"}`}>
      <div className="flex flex-wrap items-start justify-between gap-4">
        <div>
          <p className="text-xs font-medium text-slate-500">Sent automatically after approval · English and Arabic</p>
          <h2 className="text-lg font-bold text-slate-800">Station salary emails</h2>
          <p className="text-sm text-slate-600">{headline}</p>
          {run.started_at && (
            <p className="text-xs text-slate-500">
              Started {when(run.started_at)} after approval by {run.by}
            </p>
          )}
          {run.note && <p className="mt-1 text-sm text-amber-700">{run.note}</p>}
          {box.demo_inbox && (
            <p className="mt-1 text-xs text-amber-700">Demo: every email goes to {box.demo_inbox}, never to a station.</p>
          )}
        </div>
        <div className="text-right">
          <p className="text-xs text-slate-500">Cash at stations</p>
          <p className="text-xl font-semibold text-slate-800">SAR {sar(box.cash_total)}</p>
          <p className="text-xs text-slate-500">Bank {sar(box.bank_total)}</p>
        </div>
      </div>

      {total > 0 && (
        <div className="mt-4 h-2 overflow-hidden rounded-full bg-slate-100">
          <div className={`h-full ${done ? "bg-emerald-500" : "bg-indigo-500"} transition-all`} style={{ width: `${pct}%` }} />
        </div>
      )}

      {error && <p className="mt-3 text-sm text-red-600">{error}</p>}

      <div className="mt-4 flex flex-wrap items-center gap-2">
        {user?.role === "accountant" && box.can_run && (
          <button
            onClick={runAgain}
            disabled={busy}
            className="rounded-lg bg-indigo-600 px-4 py-2 text-sm font-bold text-white hover:bg-indigo-700 disabled:opacity-50"
          >
            {busy ? "Starting…" : run.status ? `Run again (${box.waiting} not sent)` : "Send emails"}
          </button>
        )}
        {box.prepared > 0 && (
          <Link
            to={`/months/${monthId}/outbox`}
            className="rounded-lg border border-slate-300 bg-white px-4 py-2 text-sm font-medium text-slate-700 hover:bg-slate-50"
          >
            See all emails
          </Link>
        )}
      </div>
    </div>
  );
}
