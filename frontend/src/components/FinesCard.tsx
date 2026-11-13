import { useRef, useState } from "react";
import { api } from "../api";
import { sar } from "../format";

interface FineResult {
  filename: string;
  error: string | null;
  fine_number?: string | null;
  plate_no?: string | null;
  date?: string | null;
  amount?: number | null;
  violation?: string | null;
  confidence?: string | null;
  driver?: { id: string; name: string; station: string } | null;
  problem?: string | null;
}

export default function FinesCard({ monthId, onAdded }: { monthId: number; onAdded: () => void }) {
  const input = useRef<HTMLInputElement>(null);
  const [results, setResults] = useState<FineResult[]>([]);
  const [chosen, setChosen] = useState<string[]>([]);
  const [busy, setBusy] = useState<"" | "read" | "add">("");
  const [message, setMessage] = useState("");
  const [error, setError] = useState("");

  async function read(files: FileList) {
    setBusy("read");
    setError("");
    setMessage("");
    try {
      const form = new FormData();
      Array.from(files).forEach((f) => form.append("files", f));
      const data = await api<{ results: FineResult[] }>(`/api/months/${monthId}/fines/read`, { method: "POST", body: form });
      setResults(data.results);
      setChosen(data.results.filter((r) => !r.error && !r.problem && r.driver).map((r) => r.filename));
    } catch (e) {
      setError(e instanceof Error ? e.message : "Could not read the documents");
    } finally {
      setBusy("");
    }
  }

  async function add() {
    setBusy("add");
    setError("");
    try {
      const fines = results
        .filter((r) => chosen.includes(r.filename) && r.driver)
        .map((r) => ({
          filename: r.filename, fine_number: r.fine_number, plate_no: r.plate_no, date: r.date,
          amount: r.amount, violation: r.violation, driver_id: r.driver!.id,
        }));
      const data = await api<{ added: number; skipped: string[] }>(`/api/months/${monthId}/fines/add`, {
        method: "POST",
        body: JSON.stringify({ fines }),
      });
      setMessage(
        `${data.added} fine(s) added as deductions. Click "Calculate salaries" again to update the payslips.` +
          (data.skipped.length ? ` Skipped: ${data.skipped.join("; ")}` : ""),
      );
      setResults([]);
      setChosen([]);
      onAdded();
    } catch (e) {
      setError(e instanceof Error ? e.message : "Could not add the fines");
    } finally {
      setBusy("");
    }
  }

  return (
    <div className="mt-8 rounded-2xl border border-violet-200 bg-white p-5 shadow-sm">
      <div className="flex flex-wrap items-start justify-between gap-4">
        <div>
          <h2 className="text-lg font-bold text-slate-800">Traffic fines from documents</h2>
          <p className="text-sm text-slate-500">
            Upload fine notices (PDF or photo). AI reads plate, date, amount and fine number – PayDesk finds who drove
            that vehicle that day. You confirm before anything is added.
          </p>
        </div>
        <input
          ref={input}
          type="file"
          multiple
          accept=".pdf,.png,.jpg,.jpeg,.webp"
          className="hidden"
          onChange={(e) => {
            if (e.target.files?.length) read(e.target.files);
            e.target.value = "";
          }}
        />
        <button
          onClick={() => input.current?.click()}
          disabled={busy !== ""}
          className="rounded-lg bg-violet-600 px-4 py-2 text-sm font-semibold text-white hover:bg-violet-700 disabled:opacity-50"
        >
          {busy === "read" ? "AI is reading…" : "Upload fine documents"}
        </button>
      </div>

      {error && <p className="mt-3 text-sm text-red-600">{error}</p>}
      {message && <p className="mt-3 text-sm text-emerald-700">{message}</p>}

      {results.length > 0 && (
        <>
          <div className="mt-4 overflow-x-auto rounded-xl border border-slate-200">
            <table className="w-full text-sm">
              <thead className="bg-slate-50 text-left text-xs uppercase text-slate-500">
                <tr>
                  <th className="p-3">Add</th><th>Document</th><th>Fine no.</th><th>Plate</th><th>Date</th>
                  <th className="text-right">Amount</th><th className="p-3">Driver / problem</th>
                </tr>
              </thead>
              <tbody>
                {results.map((r) => {
                  const ok = !r.error && !r.problem && r.driver;
                  return (
                    <tr key={r.filename} className="border-t border-slate-100 align-top">
                      <td className="p-3">
                        <input
                          type="checkbox"
                          disabled={!ok}
                          checked={chosen.includes(r.filename)}
                          onChange={() =>
                            setChosen((c) => (c.includes(r.filename) ? c.filter((x) => x !== r.filename) : [...c, r.filename]))
                          }
                        />
                      </td>
                      <td className="py-3">{r.filename}</td>
                      <td className="py-3">{r.fine_number ?? "—"}</td>
                      <td className="py-3">{r.plate_no ?? "—"}</td>
                      <td className="py-3">{r.date ?? "—"}</td>
                      <td className="py-3 text-right">{r.amount ? `SAR ${sar(r.amount)}` : "—"}</td>
                      <td className="p-3">
                        {r.error && <span className="text-red-600">{r.error}</span>}
                        {!r.error && r.driver && (
                          <div>
                            <b>{r.driver.name}</b> <span className="text-xs text-slate-400">{r.driver.id} · {r.driver.station}</span>
                            {r.violation && <div className="text-xs text-slate-500">{r.violation}</div>}
                          </div>
                        )}
                        {!r.error && r.problem && <div className="text-amber-700">{r.problem}</div>}
                        {r.confidence && r.confidence !== "high" && (
                          <div className="text-xs text-amber-600">AI confidence: {r.confidence} – check the document</div>
                        )}
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
          <div className="mt-3 flex gap-2">
            <button
              onClick={add}
              disabled={busy !== "" || chosen.length === 0}
              className="rounded-lg bg-emerald-600 px-4 py-2 text-sm font-semibold text-white hover:bg-emerald-700 disabled:opacity-50"
            >
              {busy === "add" ? "Adding…" : `Add ${chosen.length} fine${chosen.length === 1 ? "" : "s"} as deductions`}
            </button>
            <button onClick={() => setResults([])} className="rounded-lg border border-slate-300 px-4 py-2 text-sm">
              Cancel
            </button>
          </div>
        </>
      )}
    </div>
  );
}
