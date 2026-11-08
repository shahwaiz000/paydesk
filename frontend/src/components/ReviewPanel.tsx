import { useCallback, useEffect, useState } from "react";
import { api } from "../api";
import { sar } from "../format";

interface ReviewRow {
  driver_id: string;
  name: string;
  station: string;
  previous_net: number | null;
  net: number;
  change_reason: string | null;
  ai_reason: string | null;
}

interface Props {
  monthId: number;
  aiSummary: string | null;
  aiSummaryAt: string | null;
  onOpen: (driverId: string) => void;
  onSummaryChanged: () => void;
}

export default function ReviewPanel({ monthId, aiSummary, aiSummaryAt, onOpen, onSummaryChanged }: Props) {
  const [rows, setRows] = useState<ReviewRow[]>([]);
  const [aiEnabled, setAiEnabled] = useState<boolean | null>(null);
  const [busy, setBusy] = useState<"" | "explain" | "summary">("");
  const [error, setError] = useState("");

  const load = useCallback(() => {
    api<{ items: ReviewRow[] }>(`/api/months/${monthId}/salaries?flag=unusual_change&size=200`)
      .then((d) => setRows(d.items))
      .catch(() => setRows([]));
  }, [monthId]);

  useEffect(load, [load]);
  useEffect(() => {
    api<{ enabled: boolean }>("/api/ai/status").then((d) => setAiEnabled(d.enabled)).catch(() => setAiEnabled(false));
  }, []);

  async function run(kind: "explain" | "summary") {
    setBusy(kind);
    setError("");
    try {
      await api(`/api/months/${monthId}/ai/${kind}`, { method: "POST" });
      if (kind === "explain") load();
      else onSummaryChanged();
    } catch (e) {
      setError(e instanceof Error ? e.message : "AI request failed");
    } finally {
      setBusy("");
    }
  }

  const aiButton = "rounded-lg bg-violet-600 px-4 py-2 text-sm font-semibold text-white hover:bg-violet-700 disabled:opacity-50";

  return (
    <div className="mt-4 space-y-6">
      {aiEnabled === false && (
        <div className="rounded-xl border border-amber-200 bg-amber-50 p-4 text-sm text-amber-800">
          AI is off: add <code className="font-mono">GEMINI_API_KEY</code> to <code className="font-mono">backend/.env</code> and
          restart the backend. The rule-based reasons below still work without it.
        </div>
      )}
      {error && <p className="text-sm text-red-600">{error}</p>}

      {/* AI month summary */}
      <div className="rounded-2xl border border-violet-200 bg-violet-50/50 p-5">
        <div className="flex items-center justify-between gap-4">
          <div>
            <h3 className="font-semibold text-slate-800">✨ Month summary for the finance manager</h3>
            <p className="text-xs text-slate-500">
              Written by Gemini from the totals only – no names or IBANs are sent.
              {aiSummaryAt && ` Last written ${new Date(aiSummaryAt).toLocaleString()}.`}
            </p>
          </div>
          <button disabled={!aiEnabled || busy !== ""} onClick={() => run("summary")} className={aiButton}>
            {busy === "summary" ? "Writing…" : aiSummary ? "Rewrite" : "Write summary"}
          </button>
        </div>
        {aiSummary && <div className="mt-3 whitespace-pre-line text-sm leading-relaxed text-slate-700">{aiSummary}</div>}
      </div>

      {/* Unusual salaries */}
      <div className="rounded-2xl border border-slate-200 bg-white">
        <div className="flex items-center justify-between gap-4 border-b border-slate-100 p-5">
          <div>
            <h3 className="font-semibold text-slate-800">{rows.length} salaries changed more than 30% since last month</h3>
            <p className="text-xs text-slate-500">Check these before approving. Click a row to open the payslip.</p>
          </div>
          <button disabled={!aiEnabled || busy !== "" || rows.length === 0} onClick={() => run("explain")} className={aiButton}>
            {busy === "explain" ? "Explaining…" : "✨ Explain with AI"}
          </button>
        </div>
        {rows.length === 0 && (
          <p className="p-5 text-sm text-slate-500">
            Nothing unusual – or there is no previous month to compare with yet.
          </p>
        )}
        <div className="divide-y divide-slate-100">
          {rows.map((r) => {
            const up = r.previous_net !== null && r.net > r.previous_net;
            return (
              <button key={r.driver_id} onClick={() => onOpen(r.driver_id)} className="block w-full p-4 text-left hover:bg-slate-50">
                <div className="flex flex-wrap items-baseline justify-between gap-2">
                  <span>
                    <b className="text-slate-800">{r.name}</b>{" "}
                    <span className="text-xs text-slate-400">{r.driver_id} · {r.station}</span>
                  </span>
                  <span className="text-sm">
                    <span className="text-slate-400">{sar(r.previous_net)} → </span>
                    <b className={up ? "text-emerald-700" : "text-red-600"}>{sar(r.net)} SAR</b>
                  </span>
                </div>
                {r.ai_reason && <p className="mt-1 text-sm text-violet-800">✨ {r.ai_reason}</p>}
                {r.change_reason && <p className="mt-1 text-xs text-slate-500">{r.change_reason}</p>}
              </button>
            );
          })}
        </div>
      </div>
    </div>
  );
}
