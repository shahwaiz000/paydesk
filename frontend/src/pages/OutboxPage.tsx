import { useEffect, useState } from "react";
import { Link, useParams } from "react-router-dom";
import { api, downloadFile } from "../api";
import { useAuth } from "../auth";
import { sar } from "../format";
import { monthLabel, type Outbox, type OutboxEmail } from "../types";

// Stage 11: every station email of one month. Click one to read it and download its Excel file.
export default function OutboxPage() {
  const { id } = useParams();
  const { user } = useAuth();
  const [sending, setSending] = useState(false);
  const [notice, setNotice] = useState("");
  const [box, setBox] = useState<Outbox | null>(null);
  const [open, setOpen] = useState<OutboxEmail | null>(null);
  const [q, setQ] = useState("");
  const [error, setError] = useState("");

  useEffect(() => {
    api<Outbox>(`/api/months/${id}/outbox`).then(setBox).catch((e: Error) => setError(e.message));
  }, [id]);

  async function show(e: OutboxEmail) {
    setError("");
    setNotice("");
    try {
      setOpen(await api<OutboxEmail>(`/api/months/${id}/outbox/${e.id}`));
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not open the email");
    }
  }

  async function download(e: OutboxEmail) {
    try {
      await downloadFile(`/api/months/${id}/outbox/${e.id}/attachment`, e.attachment_name);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Download failed");
    }
  }

  // ONE real email to your own Gmail, through n8n (n8n adds Arabic with Gemini and sends with Gmail)
  async function realCopy(e: OutboxEmail) {
    setSending(true);
    setError("");
    setNotice("");
    try {
      const updated = await api<OutboxEmail>(`/api/months/${id}/outbox/${e.id}/real-copy`, { method: "POST" });
      setOpen(updated);
      setBox((b) => (b ? { ...b, emails: b.emails.map((x) => (x.id === updated.id ? { ...x, ...updated } : x)) } : b));
      setNotice("✓ Sent to n8n. Check your Gmail in a few seconds.");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Sending failed");
    } finally {
      setSending(false);
    }
  }

  if (error && !box) return <p className="text-red-600">{error}</p>;
  if (!box) return <p className="text-slate-500">Loading…</p>;

  const term = q.trim().toLowerCase();
  const emails = box.emails.filter(
    (e) => !term || e.station_code.toLowerCase().includes(term) || e.station.toLowerCase().includes(term),
  );

  return (
    <div>
      <Link to={`/months/${id}`} className="text-sm text-indigo-600 hover:underline">← {monthLabel(box.period)}</Link>
      <div className="mt-2 flex flex-wrap items-end justify-between gap-4">
        <div>
          <h1 className="text-2xl font-bold text-slate-800">Outbox · {monthLabel(box.period)}</h1>
          <p className="mt-1 text-slate-500">
            {box.sent} station emails · cash SAR {sar(box.cash_total)} · bank SAR {sar(box.bank_total)}
          </p>
          <p className="mt-1 text-xs text-amber-700">Demo mode: these emails were saved here, not really sent.</p>
        </div>
        <input
          value={q}
          onChange={(e) => setQ(e.target.value)}
          placeholder="Filter station…"
          className="w-48 rounded-lg border border-slate-300 px-3 py-1.5 text-sm"
        />
      </div>

      {error && <p className="mt-3 text-sm text-red-600">{error}</p>}

      {box.sent === 0 ? (
        <p className="mt-8 text-slate-500">No emails yet. Send them from the month page after approval.</p>
      ) : (
        <div className="mt-6 grid gap-6 lg:grid-cols-[1fr_1.2fr]">
          {/* List */}
          <div className="overflow-hidden rounded-2xl border border-slate-200 bg-white">
            <ul className="max-h-[70vh] divide-y divide-slate-100 overflow-y-auto">
              {emails.map((e) => (
                <li key={e.id}>
                  <button
                    onClick={() => show(e)}
                    className={`w-full px-4 py-3 text-left hover:bg-slate-50 ${open?.id === e.id ? "bg-indigo-50" : ""}`}
                  >
                    <div className="flex items-center justify-between gap-2">
                      <span className="font-semibold text-slate-800">{e.station_code} · {e.station}</span>
                      <span className="whitespace-nowrap text-sm font-semibold text-slate-700">SAR {sar(e.cash_total)}</span>
                    </div>
                    <div className="mt-0.5 flex justify-between text-xs text-slate-500">
                      <span>{e.to}</span>
                      <span>{e.cash_drivers} cash · {e.bank_drivers} bank{e.real_copies > 0 ? " · 📧" : ""}</span>
                    </div>
                  </button>
                </li>
              ))}
              {emails.length === 0 && <li className="px-4 py-6 text-sm text-slate-500">No station matches.</li>}
            </ul>
          </div>

          {/* Preview */}
          <div className="rounded-2xl border border-slate-200 bg-white p-5">
            {!open ? (
              <p className="text-slate-500">Click a station to read its email.</p>
            ) : (
              <div>
                <p className="text-xs text-slate-500">To: {open.to}</p>
                <h2 className="mt-1 font-bold text-slate-800">{open.subject}</h2>
                <button
                  onClick={() => download(open)}
                  className="mt-3 rounded-lg border border-emerald-300 bg-emerald-50 px-3 py-1.5 text-sm font-medium text-emerald-800 hover:bg-emerald-100"
                >
                  📎 {open.attachment_name}
                </button>
                {user?.role === "accountant" && (
                  <div className="mt-3 flex flex-wrap items-center gap-2">
                    <button
                      onClick={() => realCopy(open)}
                      disabled={sending || !box.n8n_ready}
                      title={box.n8n_ready ? "" : "Add N8N_WEBHOOK_URL to backend\\.env first"}
                      className="rounded-lg bg-indigo-600 px-3 py-1.5 text-sm font-semibold text-white hover:bg-indigo-700 disabled:opacity-50"
                    >
                      {sending ? "Sending via n8n…" : "📧 Send a real copy to my Gmail"}
                    </button>
                    {open.real_copies > 0 && (
                      <span className="text-xs text-slate-500">Sent {open.real_copies}× via n8n</span>
                    )}
                    {!box.n8n_ready && <span className="text-xs text-amber-700">n8n not connected yet</span>}
                  </div>
                )}
                {notice && <p className="mt-2 text-sm text-emerald-700">{notice}</p>}
                <pre className="mt-4 overflow-x-auto whitespace-pre-wrap rounded-lg bg-slate-50 p-4 font-mono text-xs leading-relaxed text-slate-700">
                  {open.body}
                </pre>
              </div>
            )}
          </div>
        </div>
      )}
    </div>
  );
}
