import { useEffect, useRef, useState } from "react";
import { api } from "../api";

interface Turn {
  role: "driver" | "assistant";
  text: string;
}

const SUGGESTIONS = [
  "Why is my salary this amount?",
  "Why was money deducted?",
  "How is my fixed salary calculated?",
  "Why is it different from last month?",
];

// "Why is my salary this?" - the driver asks about HIS payslip, AI answers from his numbers only.
export default function PayslipChat({ monthId, enabled }: { monthId: number; enabled: boolean }) {
  const [turns, setTurns] = useState<Turn[]>([]);
  const [text, setText] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const bottom = useRef<HTMLDivElement>(null);

  useEffect(() => {
    bottom.current?.scrollIntoView({ behavior: "smooth", block: "nearest" });
  }, [turns, busy]);

  async function ask(question: string) {
    const q = question.trim();
    if (!q || busy) return;
    setBusy(true);
    setError("");
    setText("");
    const history = turns;
    setTurns([...history, { role: "driver", text: q }]);
    try {
      const data = await api<{ answer: string }>(`/api/me/payslips/${monthId}/ask`, {
        method: "POST",
        body: JSON.stringify({ question: q, history }),
      });
      setTurns([...history, { role: "driver", text: q }, { role: "assistant", text: data.answer }]);
    } catch (e) {
      setTurns(history);   // take the question back so he can try again
      setText(q);
      setError(e instanceof Error ? e.message : "Could not get an answer");
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="mt-6 rounded-2xl border border-violet-200 bg-white p-5 shadow-sm">
      <h2 className="text-lg font-bold text-slate-800">Ask about your salary</h2>
      <p className="text-sm text-slate-500">Ask about this payslip. The assistant only sees your own salary for this month.</p>

      {!enabled && (
        <p className="mt-3 rounded-lg bg-slate-50 p-3 text-sm text-slate-600">
          The assistant is not switched on. Read "Your salary in simple words" above, or ask your station cashier.
        </p>
      )}

      {enabled && (
        <>
          {turns.length > 0 && (
            <div className="mt-4 max-h-96 space-y-3 overflow-y-auto">
              {turns.map((t, i) => (
                <div key={i} className={`flex ${t.role === "driver" ? "justify-end" : "justify-start"}`}>
                  <p
                    className={`max-w-[85%] whitespace-pre-line rounded-2xl px-4 py-2 text-sm ${
                      t.role === "driver" ? "bg-indigo-600 text-white" : "bg-slate-100 text-slate-800"
                    }`}
                  >
                    {t.text}
                  </p>
                </div>
              ))}
              {busy && <p className="text-sm text-slate-400">Thinking…</p>}
              <div ref={bottom} />
            </div>
          )}

          {turns.length === 0 && (
            <div className="mt-4 flex flex-wrap gap-2">
              {SUGGESTIONS.map((s) => (
                <button
                  key={s}
                  onClick={() => ask(s)}
                  disabled={busy}
                  className="rounded-full border border-violet-200 bg-violet-50 px-3 py-1.5 text-sm text-violet-800 hover:bg-violet-100 disabled:opacity-50"
                >
                  {s}
                </button>
              ))}
            </div>
          )}

          {error && <p className="mt-3 text-sm text-red-600">{error}</p>}

          <form
            className="mt-4 flex gap-2"
            onSubmit={(e) => {
              e.preventDefault();
              ask(text);
            }}
          >
            <input
              value={text}
              onChange={(e) => setText(e.target.value)}
              maxLength={300}
              placeholder="Type your question…"
              className="min-w-0 flex-1 rounded-lg border border-slate-300 px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-violet-500"
            />
            <button
              type="submit"
              disabled={busy || !text.trim()}
              className="rounded-lg bg-violet-600 px-4 py-2 text-sm font-semibold text-white hover:bg-violet-700 disabled:opacity-50"
            >
              {busy ? "…" : "Ask"}
            </button>
          </form>
          <p className="mt-2 text-xs text-slate-400">
            The assistant explains your payslip. It can't change your salary. If something is wrong, tell your station
            cashier or the payroll team.
          </p>
        </>
      )}
    </div>
  );
}
