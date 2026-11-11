import { useCallback, useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { DISPUTES_CHANGED, api } from "../api";
import { useAuth } from "../auth";
import { sar } from "../format";
import { TOPIC_LABELS, monthLabel, type InboxDispute } from "../types";

interface Inbox {
  items: InboxDispute[];
  counts: { open: number; accepted: number; rejected: number };
  ai_enabled: boolean;
}

function when(iso: string | null): string {
  if (!iso) return "";
  return new Date(iso).toLocaleString("en-GB", { day: "numeric", month: "short", hour: "2-digit", minute: "2-digit" });
}

// Accountant's inbox: drivers who said "I don't agree". Finance manager can read it.
export default function DisputesPage() {
  const { user } = useAuth();
  const [tab, setTab] = useState<"open" | "answered">("open");
  const [inbox, setInbox] = useState<Inbox | null>(null);
  const [error, setError] = useState("");

  const load = useCallback(() => {
    api<Inbox>(`/api/disputes?state=${tab}`).then(setInbox).catch((e: Error) => setError(e.message));
  }, [tab]);
  useEffect(load, [load]);

  if (error) return <p className="text-red-600">{error}</p>;
  const canAnswer = user?.role === "accountant";

  return (
    <div>
      <h1 className="text-2xl font-bold text-slate-800">Driver disputes</h1>
      <p className="mt-1 text-slate-500">Drivers who don't agree with something on their payslip.</p>

      <div className="mt-6 flex gap-2">
        {(["open", "answered"] as const).map((t) => (
          <button
            key={t}
            onClick={() => setTab(t)}
            className={`rounded-lg px-4 py-2 text-sm font-medium ${tab === t ? "bg-indigo-600 text-white" : "border border-slate-300 bg-white text-slate-700 hover:bg-slate-50"}`}
          >
            {t === "open" ? `Waiting (${inbox?.counts.open ?? "…"})` : `Answered (${inbox ? inbox.counts.accepted + inbox.counts.rejected : "…"})`}
          </button>
        ))}
      </div>

      {!inbox && <p className="mt-6 text-slate-500">Loading…</p>}
      {inbox && inbox.items.length === 0 && (
        <p className="mt-6 rounded-2xl border border-dashed border-slate-300 bg-white p-6 text-slate-500">
          {tab === "open" ? "No disputes waiting. 🎉" : "No answered disputes yet."}
        </p>
      )}
      <div className="mt-6 grid gap-4">
        {inbox?.items.map((d) => (
          <DisputeCard key={d.id} d={d} canAnswer={canAnswer} aiEnabled={inbox.ai_enabled} onDone={load} />
        ))}
      </div>
    </div>
  );
}

function DisputeCard({ d, canAnswer, aiEnabled, onDone }: { d: InboxDispute; canAnswer: boolean; aiEnabled: boolean; onDone: () => void }) {
  const [decision, setDecision] = useState<"accepted" | "rejected">("rejected");
  const [reply, setReply] = useState(d.ai_draft ?? "");
  const [remove, setRemove] = useState(false);
  const [busy, setBusy] = useState<"" | "draft" | "send">("");
  const [error, setError] = useState("");
  const [note, setNote] = useState("");

  async function draft() {
    setBusy("draft");
    setError("");
    try {
      const data = await api<{ draft: string }>(`/api/disputes/${d.id}/draft`, {
        method: "POST",
        body: JSON.stringify({ decision }),
      });
      setReply(data.draft);
    } catch (e) {
      setError(e instanceof Error ? e.message : "AI could not write a draft");
    } finally {
      setBusy("");
    }
  }

  async function send() {
    setBusy("send");
    setError("");
    try {
      const data = await api<{ note: string | null }>(`/api/disputes/${d.id}/answer`, {
        method: "POST",
        body: JSON.stringify({ decision, reply, remove_deduction: decision === "accepted" && remove }),
      });
      window.dispatchEvent(new Event(DISPUTES_CHANGED));
      if (data.note) setNote(data.note);
      else onDone();
    } catch (e) {
      setError(e instanceof Error ? e.message : "Could not send the answer");
    } finally {
      setBusy("");
    }
  }

  const open = d.status === "open";

  return (
    <div className="rounded-2xl border border-slate-200 bg-white p-5 shadow-sm">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <Link to={`/drivers/${d.driver_id}`} className="font-bold text-slate-800 hover:text-indigo-700">
            {d.driver_name}
          </Link>
          <span className="ml-2 text-xs text-slate-400">{d.driver_id} · {d.station}</span>
          <p className="text-sm text-slate-500">
            {monthLabel(d.period)} · {TOPIC_LABELS[d.topic]} · sent {when(d.created_at)}
          </p>
        </div>
        {!open && (
          <span className={`rounded-full px-3 py-1 text-xs font-semibold ${d.status === "accepted" ? "bg-emerald-50 text-emerald-700" : "bg-slate-100 text-slate-600"}`}>
            {d.status === "accepted" ? "Agreed" : "Kept"}{d.deduction_removed ? " · deduction removed" : ""}
          </span>
        )}
      </div>

      {d.line && (
        <div className="mt-3 rounded-lg bg-red-50 px-3 py-2 text-sm text-red-900">
          <b>{d.line.type} SAR {sar(d.line.amount)}</b>
          <span className="ml-2 text-xs text-red-700">
            {[d.line.reference, d.line.day, d.line.carried_from && `carried from ${monthLabel(d.line.carried_from)}`, d.line.note]
              .filter(Boolean)
              .join(" · ")}
          </span>
        </div>
      )}
      <p className="mt-3 rounded-lg bg-slate-50 p-3 text-sm text-slate-800">“{d.message}”</p>

      {!open && (
        <div className="mt-3 text-sm">
          <p className="text-xs text-slate-400">Answer by {d.answered_by} · {when(d.answered_at)}</p>
          <p className="mt-1 whitespace-pre-line text-slate-700">{d.reply}</p>
        </div>
      )}

      {open && canAnswer && !note && (
        <div className="mt-4 border-t border-slate-100 pt-4">
          <div className="flex flex-wrap gap-4 text-sm">
            <label className="flex items-center gap-2">
              <input type="radio" checked={decision === "accepted"} onChange={() => setDecision("accepted")} />
              Driver is right
            </label>
            <label className="flex items-center gap-2">
              <input type="radio" checked={decision === "rejected"} onChange={() => { setDecision("rejected"); setRemove(false); }} />
              Keep it – explain why
            </label>
          </div>
          {decision === "accepted" && d.can_remove && (
            <label className="mt-3 flex items-center gap-2 text-sm text-slate-700">
              <input type="checkbox" checked={remove} onChange={(e) => setRemove(e.target.checked)} />
              Remove this deduction from {monthLabel(d.period)} (you'll need to recalculate salaries)
            </label>
          )}
          <textarea
            value={reply}
            onChange={(e) => setReply(e.target.value)}
            rows={4}
            maxLength={1000}
            placeholder="Your answer to the driver…"
            className="mt-3 block w-full rounded-lg border border-slate-300 px-3 py-2 text-sm"
          />
          {error && <p className="mt-2 text-sm text-red-600">{error}</p>}
          <div className="mt-3 flex flex-wrap gap-2">
            {aiEnabled && (
              <button
                onClick={draft}
                disabled={busy !== ""}
                className="rounded-lg border border-violet-300 bg-violet-50 px-4 py-2 text-sm font-semibold text-violet-800 hover:bg-violet-100 disabled:opacity-50"
              >
                {busy === "draft" ? "AI is writing…" : "✨ Draft reply with AI"}
              </button>
            )}
            <button
              onClick={send}
              disabled={busy !== "" || reply.trim().length < 5}
              className="rounded-lg bg-indigo-600 px-4 py-2 text-sm font-semibold text-white hover:bg-indigo-700 disabled:opacity-50"
            >
              {busy === "send" ? "Sending…" : "Send answer to driver"}
            </button>
          </div>
          <p className="mt-2 text-xs text-slate-400">AI only writes a draft. Read it and change it before you send.</p>
        </div>
      )}

      {note && (
        <div className="mt-4 rounded-lg bg-amber-50 p-3 text-sm text-amber-800">
          {note}{" "}
          <Link to={`/months/${d.month_id}`} className="font-semibold underline">Go to {monthLabel(d.period)}</Link>
          <button onClick={onDone} className="ml-3 text-amber-700 underline">OK</button>
        </div>
      )}
    </div>
  );
}
