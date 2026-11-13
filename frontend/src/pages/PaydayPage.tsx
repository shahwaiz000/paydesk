import { useCallback, useEffect, useState } from "react";
import { api } from "../api";
import { useAuth } from "../auth";
import { sar } from "../format";
import StatCard from "../components/StatCard";

// Automation 3: "Did the driver get his cash?"
// Cashier: marks his cash drivers as Paid -> n8n asks each driver on Telegram -> driver taps ✅ / ❌.
// Accountant / finance manager: every station's progress + drivers who said "wrong amount".

type Status = "not_paid" | "waiting" | "confirmed" | "wrong" | "no_telegram";

interface Row {
  driver_id: string;
  name: string;
  station_code: string;
  station: string;
  net: number;
  telegram: boolean;
  status: Status;
  paid_at: string | null;
  paid_by: string | null;
  answered_at: string | null;
  said_amount: number | null;
  note: string | null;
}

interface Totals {
  drivers: number;
  cash: number;
  paid: number;
  paid_amount: number;
  confirmed: number;
  wrong: number;
  waiting: number;
  no_telegram: number;
  not_paid: number;
}

interface StationRow extends Totals {
  station_code: string;
  station: string;
  state: "all_paid" | "partly_paid" | "not_started";
}

interface Payday {
  month: { id: number; period: string; month_name: string } | null;
  totals?: Totals;
  drivers?: Row[];
  stations?: StationRow[];
  problems?: Row[];
}

const BADGE: Record<Status, { label: string; style: string }> = {
  not_paid: { label: "Not paid", style: "bg-slate-100 text-slate-600" },
  waiting: { label: "Paid · waiting for driver", style: "bg-amber-50 text-amber-700" },
  confirmed: { label: "Confirmed by driver", style: "bg-emerald-100 text-emerald-800" },
  wrong: { label: "Driver says wrong amount", style: "bg-red-100 text-red-700" },
  no_telegram: { label: "Paid · driver not on Telegram", style: "bg-slate-100 text-slate-600" },
};

const STATE: Record<StationRow["state"], { label: string; style: string }> = {
  all_paid: { label: "All paid", style: "bg-emerald-100 text-emerald-800" },
  partly_paid: { label: "Partly paid", style: "bg-amber-50 text-amber-700" },
  not_started: { label: "Not started", style: "bg-slate-100 text-slate-600" },
};

function when(iso: string | null): string {
  if (!iso) return "";
  return new Date(iso).toLocaleString("en-GB", { day: "numeric", month: "short", hour: "2-digit", minute: "2-digit" });
}

export default function PaydayPage() {
  const { user } = useAuth();
  const [data, setData] = useState<Payday | null>(null);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);

  const load = useCallback(() => {
    api<Payday>("/api/payday").then(setData).catch((e: Error) => setError(e.message));
  }, []);

  useEffect(() => {
    load();
    const timer = window.setInterval(load, 10_000); // driver answers come in from Telegram
    return () => window.clearInterval(timer);
  }, [load]);

  async function markPaid(ids: string[]) {
    if (!data?.month || ids.length === 0) return;
    setBusy(true);
    setError("");
    try {
      await api(`/api/payday/${data.month.id}/paid`, { method: "POST", body: JSON.stringify({ driver_ids: ids }) });
      load();
    } catch (e) {
      setError(e instanceof Error ? e.message : "Could not save");
    } finally {
      setBusy(false);
    }
  }

  if (error && !data) return <p className="text-red-600">{error}</p>;
  if (!data || !user) return <p className="text-slate-500">Loading…</p>;
  if (!data.month) {
    return (
      <div>
        <h1 className="text-2xl font-bold text-slate-800">Payday</h1>
        <p className="mt-2 text-slate-500">No approved month yet. Payday starts after the finance manager approves a month.</p>
      </div>
    );
  }

  const t = data.totals!;
  const cashier = user.role === "cashier";
  const unpaid = (data.drivers ?? []).filter((d) => d.status === "not_paid").map((d) => d.driver_id);

  return (
    <div>
      <div className="flex flex-wrap items-end justify-between gap-4">
        <div>
          <h1 className="text-2xl font-bold text-slate-800">Payday · {data.month.month_name}</h1>
          <p className="mt-1 text-sm text-slate-500">
            {cashier
              ? "Mark each cash driver as Paid when you give him his salary. He confirms on Telegram – no paper signature."
              : "Cash salaries at every station. Drivers confirm on Telegram that they received their cash."}
          </p>
        </div>
        {cashier && unpaid.length > 0 && (
          <button
            disabled={busy}
            onClick={() => markPaid(unpaid)}
            className="rounded-lg bg-indigo-600 px-4 py-2 text-sm font-bold text-white hover:bg-indigo-700 disabled:opacity-50"
          >
            Mark all {unpaid.length} as paid
          </button>
        )}
      </div>

      {error && <p className="mt-3 text-sm text-red-600">{error}</p>}

      <div className="mt-6 grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
        <StatCard label="Cash drivers paid" value={`${t.paid} of ${t.drivers}`} note={`SAR ${sar(t.paid_amount)} of SAR ${sar(t.cash)} paid`} />
        <StatCard label="Confirmed by driver" value={t.confirmed} note="Driver confirmed the amount on Telegram" tone={t.confirmed ? "good" : undefined} />
        <StatCard label="Waiting for driver" value={t.waiting} note="Asked on Telegram, no answer yet" tone={t.waiting ? "warn" : undefined} />
        <StatCard label="Wrong amount reported" value={t.wrong} note={t.wrong ? "Driver says he got a different amount" : "No problems reported"} tone={t.wrong ? "bad" : undefined} />
      </div>

      {/* Problems first: drivers who said they got a different amount */}
      {!cashier && (data.problems?.length ?? 0) > 0 && (
        <div className="mt-6 rounded-2xl border border-red-200 bg-red-50 p-5">
          <h2 className="font-bold text-red-800">Drivers who say the amount is wrong</h2>
          <ul className="mt-3 grid gap-2">
            {data.problems!.map((p) => (
              <li key={p.driver_id} className="rounded-lg bg-white px-4 py-3 text-sm">
                <b>{p.driver_id} · {p.name}</b> – {p.station_code} {p.station}
                <div className="mt-1 text-slate-700">
                  Paid SAR {sar(p.net)} by {p.paid_by} · driver says{" "}
                  <b>{p.said_amount != null ? `SAR ${sar(p.said_amount)}` : "a different amount"}</b>
                  {p.note && <span className="text-slate-500"> – “{p.note}”</span>}
                </div>
              </li>
            ))}
          </ul>
        </div>
      )}

      {cashier ? (
        <div className="mt-6 overflow-x-auto rounded-2xl border border-slate-200 bg-white shadow-sm">
          <table className="w-full whitespace-nowrap text-sm">
            <thead className="bg-slate-50 text-left text-xs uppercase text-slate-500">
              <tr>
                <th className="px-4 py-2">Driver</th>
                <th className="px-4 py-2 text-right">Cash to pay</th>
                <th className="px-4 py-2">Status</th>
                <th className="px-4 py-2" />
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-100">
              {data.drivers!.map((d) => (
                <tr key={d.driver_id}>
                  <td className="px-4 py-3">
                    <b>{d.driver_id}</b> · {d.name}
                    {d.telegram && <span className="ml-2 text-xs text-sky-600">Telegram</span>}
                  </td>
                  <td className="px-4 py-3 text-right font-semibold">SAR {sar(d.net)}</td>
                  <td className="px-4 py-3">
                    <span className={`rounded-full px-2 py-0.5 text-xs font-medium ${BADGE[d.status].style}`}>
                      {BADGE[d.status].label}
                    </span>
                    {d.paid_at && <span className="ml-2 text-xs text-slate-400">{when(d.paid_at)}</span>}
                    {d.status === "wrong" && d.said_amount != null && (
                      <span className="ml-2 text-xs text-red-600">says SAR {sar(d.said_amount)}</span>
                    )}
                  </td>
                  <td className="px-4 py-3 text-right">
                    {d.status === "not_paid" && (
                      <button
                        disabled={busy}
                        onClick={() => markPaid([d.driver_id])}
                        className="rounded-lg border border-indigo-300 px-3 py-1 text-xs font-semibold text-indigo-700 hover:bg-indigo-50 disabled:opacity-50"
                      >
                        Paid
                      </button>
                    )}
                  </td>
                </tr>
              ))}
              {data.drivers!.length === 0 && (
                <tr>
                  <td colSpan={4} className="px-4 py-6 text-slate-500">No cash drivers at your station this month.</td>
                </tr>
              )}
            </tbody>
          </table>
        </div>
      ) : (
        <div className="mt-6 overflow-x-auto rounded-2xl border border-slate-200 bg-white shadow-sm">
          <table className="w-full whitespace-nowrap text-sm">
            <thead className="bg-slate-50 text-left text-xs uppercase text-slate-500">
              <tr>
                <th className="px-4 py-2">Station</th>
                <th className="px-4 py-2">State</th>
                <th className="px-4 py-2 text-right">Paid</th>
                <th className="px-4 py-2 text-right">Cash paid</th>
                <th className="px-4 py-2 text-right">Confirmed</th>
                <th className="px-4 py-2 text-right">Wrong</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-100">
              {data.stations!.map((s) => (
                <tr key={s.station_code}>
                  <td className="px-4 py-2"><b>{s.station_code}</b> · {s.station}</td>
                  <td className="px-4 py-2">
                    <span className={`rounded-full px-2 py-0.5 text-xs font-medium ${STATE[s.state].style}`}>
                      {STATE[s.state].label}
                    </span>
                  </td>
                  <td className="px-4 py-2 text-right">{s.paid} / {s.drivers}</td>
                  <td className="px-4 py-2 text-right">SAR {sar(s.paid_amount)}</td>
                  <td className="px-4 py-2 text-right text-emerald-700">{s.confirmed || ""}</td>
                  <td className="px-4 py-2 text-right text-red-600">{s.wrong || ""}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}
