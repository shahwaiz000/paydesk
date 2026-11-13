import { useEffect, useState } from "react";
import { Link, useParams } from "react-router-dom";
import { api, downloadFile } from "../api";
import { sar } from "../format";
import { monthLabel, type Outbox, type OutboxEmail } from "../types";

// Automation 1: every station email of one month and what n8n did with it.
// Click one to read it and download its Excel file.
const BADGE: Record<OutboxEmail["status"], string> = {
  sent: "bg-emerald-100 text-emerald-800",
  failed: "bg-red-100 text-red-700",
  prepared: "bg-slate-100 text-slate-600",
};
const LABEL: Record<OutboxEmail["status"], string> = { sent: "Sent", failed: "Failed", prepared: "Waiting" };

function when(iso: string | null): string {
  if (!iso) return "";
  return new Date(iso).toLocaleString("en-GB", { day: "numeric", month: "short", hour: "2-digit", minute: "2-digit" });
}
export default function OutboxPage() {
  const { id } = useParams();
  const [box, setBox] = useState<Outbox | null>(null);
  const [open, setOpen] = useState<OutboxEmail | null>(null);
  const [q, setQ] = useState("");
  const [error, setError] = useState("");

  useEffect(() => {
    api<Outbox>(`/api/months/${id}/outbox`).then(setBox).catch((e: Error) => setError(e.message));
  }, [id]);

  async function show(e: OutboxEmail) {
    setError("");
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
          <h1 className="text-2xl font-bold text-slate-800">Station emails · {monthLabel(box.period)}</h1>
          <p className="mt-1 text-slate-500">
            {box.delivered} of {box.prepared} sent
            {box.failed > 0 ? ` · ${box.failed} failed` : ""}
            {box.run.seconds != null ? ` · ${box.run.seconds} s` : ""} · cash SAR {sar(box.cash_total)} · bank SAR{" "}
            {sar(box.bank_total)}
          </p>
          <p className="mt-1 text-xs text-amber-700">
            Demo: every email goes to {box.demo_inbox ?? "the demo inbox"}, never to a real station.
          </p>
        </div>
        <input
          value={q}
          onChange={(e) => setQ(e.target.value)}
          placeholder="Filter station…"
          className="w-48 rounded-lg border border-slate-300 px-3 py-1.5 text-sm"
        />
      </div>

      {error && <p className="mt-3 text-sm text-red-600">{error}</p>}

      {box.prepared === 0 ? (
        <p className="mt-8 text-slate-500">No emails yet. They are prepared automatically when the month is approved.</p>
      ) : (
        <div className="mt-6 grid gap-6 lg:grid-cols-[1fr_1.2fr]">
          {/* List */}
          <div className="overflow-hidden rounded-2xl border border-slate-200 bg-white shadow-sm">
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
                      <span>{e.cash_drivers} cash · {e.bank_drivers} bank</span>
                      <span className={`rounded-full px-2 py-0.5 font-medium ${BADGE[e.status]}`}>{LABEL[e.status]}</span>
                    </div>
                  </button>
                </li>
              ))}
              {emails.length === 0 && <li className="px-4 py-6 text-sm text-slate-500">No station matches.</li>}
            </ul>
          </div>

          {/* Preview */}
          <div className="rounded-2xl border border-slate-200 bg-white shadow-sm p-5">
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
                  {open.attachment_name}
                </button>
                <div className="mt-3 rounded-lg bg-slate-50 p-3 text-sm">
                  <span className={`rounded-full px-2 py-0.5 text-xs font-medium ${BADGE[open.status]}`}>{LABEL[open.status]}</span>
                  {open.status === "sent" && (
                    <span className="ml-2 text-slate-600">
                      Sent to {open.delivered_to} · {when(open.delivered_at)}
                    </span>
                  )}
                  {open.status === "failed" && <span className="ml-2 text-red-700">{open.delivery_note}</span>}
                  {open.status === "prepared" && <span className="ml-2 text-slate-500">Waiting to be sent</span>}
                </div>
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
