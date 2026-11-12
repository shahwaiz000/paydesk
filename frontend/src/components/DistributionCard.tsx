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

// Stage 11: after approval, one click sends the salary email to every station (demo: saved in the Outbox).
export default function DistributionCard({ monthId, refreshKey }: { monthId: number; refreshKey: number }) {
  const { user } = useAuth();
  const [box, setBox] = useState<Outbox | null>(null);
  const [confirm, setConfirm] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");

  const load = useCallback(() => {
    api<Outbox>(`/api/months/${monthId}/outbox`).then(setBox).catch((e: Error) => setError(e.message));
  }, [monthId]);
  useEffect(load, [load, refreshKey]);

  async function send() {
    setBusy(true);
    setError("");
    try {
      setBox(await api<Outbox>(`/api/months/${monthId}/outbox/send`, { method: "POST" }));
      setConfirm(false);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Sending failed");
    } finally {
      setBusy(false);
    }
  }

  if (!box) return error ? <p className="mt-6 text-red-600">{error}</p> : null;
  const sent = box.sent > 0;

  return (
    <div className={`mt-6 rounded-2xl border p-5 shadow-sm ${sent ? "border-emerald-200 bg-emerald-50/40" : "border-indigo-200 bg-white"}`}>
      <div className="flex flex-wrap items-start justify-between gap-4">
        <div>
          <h2 className="text-lg font-bold text-slate-800">📤 Send salaries to stations</h2>
          <p className="text-sm text-slate-500">
            {sent
              ? `${box.sent} station emails sent by ${box.sent_by} · ${when(box.sent_at)}`
              : `One email per station (${box.stations} stations): cash to prepare, list of cash drivers, and an Excel sheet to sign.`}
          </p>
          <p className="mt-1 text-xs text-amber-700">Demo mode: emails are saved in the Outbox, not really sent.</p>
        </div>
        {sent && (
          <div className="text-right">
            <p className="text-xs text-slate-500">Cash at stations</p>
            <p className="text-xl font-bold text-slate-800">SAR {sar(box.cash_total)}</p>
            <p className="text-xs text-slate-500">Bank {sar(box.bank_total)}</p>
          </div>
        )}
      </div>

      {error && <p className="mt-3 text-sm text-red-600">{error}</p>}

      <div className="mt-4 flex flex-wrap items-center gap-2">
        {user?.role === "accountant" && box.can_send && !confirm && (
          <button
            onClick={() => setConfirm(true)}
            className="rounded-lg bg-indigo-600 px-4 py-2 text-sm font-semibold text-white hover:bg-indigo-700"
          >
            Send {box.stations} station emails
          </button>
        )}
        {confirm && (
          <div className="flex flex-wrap items-center gap-2 rounded-lg bg-indigo-50 p-2 text-sm text-indigo-900">
            <span>Send the salary email to all {box.stations} stations now?</span>
            <button
              onClick={send}
              disabled={busy}
              className="rounded-lg bg-indigo-600 px-3 py-1.5 font-semibold text-white hover:bg-indigo-700 disabled:opacity-50"
            >
              {busy ? "Sending…" : "Yes, send"}
            </button>
            <button onClick={() => setConfirm(false)} className="rounded-lg border border-indigo-300 px-3 py-1.5">
              Cancel
            </button>
          </div>
        )}
        {sent && (
          <Link
            to={`/months/${monthId}/outbox`}
            className="rounded-lg border border-slate-300 bg-white px-4 py-2 text-sm font-medium text-slate-700 hover:bg-slate-50"
          >
            Open Outbox →
          </Link>
        )}
        {!sent && user?.role === "finance_manager" && (
          <p className="text-sm text-slate-500">Waiting for the accountant to send the station emails.</p>
        )}
      </div>
    </div>
  );
}
