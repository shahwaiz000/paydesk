import { useCallback, useEffect, useState } from "react";
import { api } from "../api";
import { useAuth } from "../auth";
import { sar } from "../format";
import type { Approval } from "../types";

const STEPS = [
  { key: "calculated", label: "Calculated" },
  { key: "submitted", label: "Sent for approval" },
  { key: "approved", label: "Approved & locked" },
];

const ACTIONS: Record<string, string> = {
  submitted: "sent for approval",
  approved: "approved and locked",
  sent_back: "sent back",
};

function when(iso: string | null): string {
  if (!iso) return "";
  return new Date(iso).toLocaleString("en-GB", { day: "numeric", month: "short", hour: "2-digit", minute: "2-digit" });
}

// Stage 10: accountant sends the month -> finance manager approves (locks) or sends it back.
export default function ApprovalCard({ monthId, refreshKey, onChanged }: { monthId: number; refreshKey: number; onChanged: () => void }) {
  const { user } = useAuth();
  const [a, setA] = useState<Approval | null>(null);
  const [note, setNote] = useState("");
  const [reason, setReason] = useState("");
  const [showBack, setShowBack] = useState(false);
  const [confirmApprove, setConfirmApprove] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");

  const load = useCallback(() => {
    api<Approval>(`/api/months/${monthId}/approval`).then(setA).catch((e: Error) => setError(e.message));
  }, [monthId]);
  useEffect(load, [load, refreshKey]);

  async function act(path: string, body: object = {}) {
    setBusy(true);
    setError("");
    try {
      setA(await api<Approval>(`/api/months/${monthId}/${path}`, { method: "POST", body: JSON.stringify(body) }));
      setShowBack(false);
      setConfirmApprove(false);
      setNote("");
      setReason("");
      onChanged();
    } catch (e) {
      setError(e instanceof Error ? e.message : "Something went wrong");
    } finally {
      setBusy(false);
    }
  }

  if (!a) return error ? <p className="mt-6 text-red-600">{error}</p> : null;

  const stepIndex = STEPS.findIndex((s) => s.key === a.status);
  const forApprove = a.status === "submitted";
  const blocking = a.checks.filter((c) => c.blocking && !c.ok && (forApprove || !c.approve_only));
  const isAccountant = user?.role === "accountant";
  const isManager = user?.role === "finance_manager";

  return (
    <div className={`mt-8 rounded-2xl border p-5 shadow-sm ${a.status === "approved" ? "border-slate-300 bg-slate-50" : "border-violet-200 bg-white"}`}>
      <div className="flex flex-wrap items-start justify-between gap-4">
        <div>
          <h2 className="text-lg font-bold text-slate-800">
            {a.status === "approved" ? "Approved and locked" : "Approval"}
          </h2>
          <p className="text-sm text-slate-500">
            {a.status === "approved"
              ? `Approved by ${a.approved_by} · ${when(a.approved_at)}. Final for drivers. Corrections go into next month.`
              : a.status === "submitted"
                ? `Sent by ${a.submitted_by} · ${when(a.submitted_at)}. Locked while the finance manager checks it.`
                : "When everything is checked, send this month to the finance manager."}
          </p>
        </div>
        <div className="text-right">
          <p className="text-xs text-slate-500">Net to pay · {a.totals.drivers} drivers</p>
          <p className="text-2xl font-bold text-slate-800">SAR {sar(a.totals.net)}</p>
          <p className="text-xs text-slate-500">Cash {sar(a.totals.cash_net)} · Bank {sar(a.totals.bank_net)}</p>
        </div>
      </div>

      {/* Steps */}
      <ol className="mt-4 flex flex-wrap gap-2 text-sm">
        {STEPS.map((s, i) => (
          <li
            key={s.key}
            className={`rounded-full px-3 py-1 ${i <= stepIndex ? "bg-violet-600 text-white" : "bg-slate-100 text-slate-500"}`}
          >
            {i + 1}. {s.label}
          </li>
        ))}
      </ol>

      {a.returned_note && a.status === "calculated" && (
        <p className="mt-4 rounded-lg bg-amber-50 p-3 text-sm text-amber-900">
          <b>Sent back by the finance manager:</b> {a.returned_note}
        </p>
      )}

      {/* Checklist */}
      {a.status !== "approved" && (
        <ul className="mt-4 space-y-1.5 text-sm">
          {a.checks.map((c) => (
            <li key={c.key} className="flex gap-2">
              <span>{c.ok ? "✓" : c.blocking ? "✕" : "!"}</span>
              <span className={c.ok ? "text-slate-600" : c.blocking ? "font-medium text-red-700" : "text-amber-800"}>
                {c.text}
                {!c.ok && c.approve_only && !forApprove && <span className="text-xs text-slate-400"> (needed before approval)</span>}
              </span>
            </li>
          ))}
        </ul>
      )}

      {error && <p className="mt-3 text-sm text-red-600">{error}</p>}

      {/* Accountant: send */}
      {isAccountant && a.status === "calculated" && (
        <div className="mt-4 flex flex-wrap items-center gap-2">
          <input
            value={note}
            onChange={(e) => setNote(e.target.value)}
            maxLength={400}
            placeholder="Note for the finance manager (optional)"
            className="min-w-0 flex-1 rounded-lg border border-slate-300 px-3 py-2 text-sm"
          />
          <button
            onClick={() => act("submit", { note })}
            disabled={busy || blocking.length > 0}
            className="rounded-lg bg-violet-600 px-4 py-2 text-sm font-semibold text-white hover:bg-violet-700 disabled:opacity-50"
          >
            {busy ? "Sending…" : "Send for approval"}
          </button>
        </div>
      )}
      {isAccountant && a.status === "submitted" && (
        <p className="mt-4 text-sm text-violet-700">Waiting for the finance manager. You can't change this month now.</p>
      )}

      {/* Finance manager: approve or send back */}
      {isManager && a.status === "submitted" && !showBack && (
        <div className="mt-4 flex flex-wrap gap-2">
          {!confirmApprove ? (
            <button
              onClick={() => setConfirmApprove(true)}
              disabled={busy || blocking.length > 0}
              className="rounded-lg bg-emerald-600 px-4 py-2 text-sm font-semibold text-white hover:bg-emerald-700 disabled:opacity-50"
            >
              Approve & lock
            </button>
          ) : (
            <div className="flex flex-wrap items-center gap-2 rounded-lg bg-emerald-50 p-2 text-sm text-emerald-900">
              <span>Approve SAR {sar(a.totals.net)} for {a.totals.drivers} drivers? This can't be undone.</span>
              <button
                onClick={() => act("approve")}
                disabled={busy}
                className="rounded-lg bg-emerald-600 px-3 py-1.5 font-semibold text-white hover:bg-emerald-700 disabled:opacity-50"
              >
                {busy ? "Approving…" : "Yes, approve"}
              </button>
              <button onClick={() => setConfirmApprove(false)} className="rounded-lg border border-emerald-300 px-3 py-1.5">
                Cancel
              </button>
            </div>
          )}
          <button
            onClick={() => setShowBack(true)}
            className="rounded-lg border border-slate-300 px-4 py-2 text-sm font-medium text-slate-700 hover:bg-slate-50"
          >
            Send back
          </button>
        </div>
      )}
      {isManager && showBack && (
        <div className="mt-4 flex flex-wrap items-center gap-2">
          <input
            value={reason}
            onChange={(e) => setReason(e.target.value)}
            maxLength={400}
            placeholder="What should the accountant check or fix?"
            className="min-w-0 flex-1 rounded-lg border border-slate-300 px-3 py-2 text-sm"
          />
          <button
            onClick={() => act("send-back", { reason })}
            disabled={busy || reason.trim().length < 5}
            className="rounded-lg bg-amber-600 px-4 py-2 text-sm font-semibold text-white hover:bg-amber-700 disabled:opacity-50"
          >
            Send back to accountant
          </button>
          <button onClick={() => setShowBack(false)} className="rounded-lg border border-slate-300 px-3 py-2 text-sm">
            Cancel
          </button>
        </div>
      )}
      {isManager && a.status === "calculated" && (
        <p className="mt-4 text-sm text-slate-500">The accountant hasn't sent this month for approval yet.</p>
      )}

      {/* History */}
      {a.events.length > 0 && (
        <details className="mt-4">
          <summary className="cursor-pointer text-sm font-medium text-slate-600">History ({a.events.length})</summary>
          <ul className="mt-2 space-y-1 text-sm text-slate-600">
            {a.events.map((e, i) => (
              <li key={i}>
                <span className="text-slate-400">{when(e.at)}</span> · <b>{e.by}</b> {ACTIONS[e.action]}
                {e.totals?.net !== undefined && <span className="text-slate-400"> (net SAR {sar(e.totals.net)})</span>}
                {e.note && <span> – “{e.note}”</span>}
              </li>
            ))}
          </ul>
        </details>
      )}
    </div>
  );
}
