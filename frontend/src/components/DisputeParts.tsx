import { useState } from "react";
import { api } from "../api";
import { TOPIC_LABELS, type Dispute, type DisputeTopic } from "../types";

// Shown under a deduction (or in the "something else" box) once the driver has reported it.
export function DisputeStatus({ d }: { d: Dispute }) {
  if (d.status === "open") {
    return (
      <div className="mt-2 rounded-lg bg-sky-50 p-3 text-xs text-sky-800">
        <b>Reported – waiting for the payroll team.</b>
        <p className="mt-1 text-sky-700">You wrote: “{d.message}”</p>
      </div>
    );
  }
  const agreed = d.status === "accepted";
  return (
    <div className={`mt-2 rounded-lg p-3 text-xs ${agreed ? "bg-emerald-50 text-emerald-900" : "bg-slate-100 text-slate-700"}`}>
      <b>{agreed ? "✓ Payroll team agreed" : "Payroll team checked – it stays"}</b>
      {d.deduction_removed && <span className="ml-1">· this deduction is being removed</span>}
      <p className="mt-1 whitespace-pre-line">{d.reply}</p>
      <p className="mt-1 opacity-70">You wrote: “{d.message}”</p>
    </div>
  );
}

// "I don't agree" form. For a deduction pass lineKey; otherwise the driver picks a topic.
export function ReportForm({
  monthId,
  lineKey,
  onSent,
  onCancel,
}: {
  monthId: number;
  lineKey?: string;
  onSent: (all: Dispute[]) => void;
  onCancel: () => void;
}) {
  const [topic, setTopic] = useState<DisputeTopic>(lineKey ? "deduction" : "deliveries");
  const [message, setMessage] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");

  async function send() {
    setBusy(true);
    setError("");
    try {
      const data = await api<{ disputes: Dispute[] }>(`/api/me/payslips/${monthId}/disputes`, {
        method: "POST",
        body: JSON.stringify({ topic, line_key: lineKey ?? null, message }),
      });
      onSent(data.disputes);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Could not send");
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="mt-2 rounded-lg border border-slate-200 bg-slate-50 p-3">
      {!lineKey && (
        <label className="block text-xs font-medium text-slate-600">
          What is wrong?
          <select
            value={topic}
            onChange={(e) => setTopic(e.target.value as DisputeTopic)}
            className="mt-1 block w-full rounded-lg border border-slate-300 bg-white px-2 py-1.5 text-sm"
          >
            {(["deliveries", "days", "other"] as DisputeTopic[]).map((t) => (
              <option key={t} value={t}>{TOPIC_LABELS[t]}</option>
            ))}
          </select>
        </label>
      )}
      <label className="mt-2 block text-xs font-medium text-slate-600">
        Tell the payroll team why
        <textarea
          value={message}
          onChange={(e) => setMessage(e.target.value)}
          maxLength={500}
          rows={3}
          placeholder={lineKey ? "For example: I returned this advance in cash on 20 Oct" : "For example: I delivered 15 orders on 12 Oct, not 8"}
          className="mt-1 block w-full rounded-lg border border-slate-300 bg-white px-2 py-1.5 text-sm"
        />
      </label>
      {error && <p className="mt-2 text-xs text-red-600">{error}</p>}
      <div className="mt-2 flex gap-2">
        <button
          onClick={send}
          disabled={busy || message.trim().length < 5}
          className="rounded-lg bg-indigo-600 px-3 py-1.5 text-sm font-semibold text-white hover:bg-indigo-700 disabled:opacity-50"
        >
          {busy ? "Sending…" : "Send to payroll team"}
        </button>
        <button onClick={onCancel} className="rounded-lg border border-slate-300 px-3 py-1.5 text-sm">
          Cancel
        </button>
      </div>
    </div>
  );
}
