import { useEffect, useState } from "react";
import { Link, useSearchParams } from "react-router-dom";
import { api } from "../api";
import { useAuth } from "../auth";

export interface DriverInfo {
  id: string;
  name: string;
  station: string;
  station_code: string;
  city: string;
  payment_method: string;
  joining_date: string;
  leaving_date: string | null;
  phone: string | null;
  iban_last4: string | null;
}

export default function DriversPage() {
  const { user } = useAuth();
  const [params, setParams] = useSearchParams();
  const q = params.get("q") ?? "";
  const [text, setText] = useState(q);
  const [items, setItems] = useState<DriverInfo[]>([]);
  const [more, setMore] = useState(false);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");

  // Wait until the user stops typing for 300 ms, then search
  useEffect(() => {
    const t = setTimeout(() => {
      if (text !== q) setParams(text ? { q: text } : {}, { replace: true });
    }, 300);
    return () => clearTimeout(t);
  }, [text, q, setParams]);

  useEffect(() => {
    let cancelled = false;
    api<{ items: DriverInfo[]; more: boolean }>(`/api/drivers?q=${encodeURIComponent(q)}&limit=100`)
      .then((d) => {
        if (cancelled) return;
        setItems(d.items);
        setMore(d.more);
        setError("");
      })
      .catch((e: Error) => !cancelled && setError(e.message))
      .finally(() => !cancelled && setLoading(false));
    return () => {
      cancelled = true;
    };
  }, [q]);

  return (
    <div>
      <h1 className="text-2xl font-bold text-slate-800">Drivers</h1>
      <p className="mt-1 text-slate-500">
        {user?.role === "cashier" ? "Drivers at your station." : "Search all drivers."} Type a name, driver ID, phone or
        Iqama number.
      </p>

      <input
        autoFocus
        value={text}
        onChange={(e) => setText(e.target.value)}
        placeholder="e.g. Usman, D10162, 0551234567"
        className="mt-5 w-full max-w-xl rounded-xl border border-slate-300 px-4 py-3 text-lg focus:outline-none focus:ring-2 focus:ring-indigo-500"
      />

      {error && <p className="mt-4 text-red-600">{error}</p>}

      <div className="mt-5 overflow-x-auto rounded-2xl border border-slate-200 bg-white">
        <table className="w-full text-sm">
          <thead className="bg-slate-50 text-left text-xs uppercase text-slate-500">
            <tr>
              <th className="p-3">Driver</th><th>Station</th><th>Paid by</th><th>Joined</th><th className="p-3">Status</th>
            </tr>
          </thead>
          <tbody>
            {items.map((d) => (
              <tr key={d.id} className="border-t border-slate-100 hover:bg-indigo-50/50">
                <td className="p-3">
                  <Link to={`/drivers/${d.id}`} className="block">
                    <b className="text-indigo-700">{d.name}</b>
                    <div className="text-xs text-slate-400">{d.id}{d.phone ? ` · ${d.phone}` : ""}</div>
                  </Link>
                </td>
                <td className="text-slate-600">{d.station}</td>
                <td>{d.payment_method === "Bank" ? `Bank ···· ${d.iban_last4 ?? ""}` : "Cash"}</td>
                <td>{d.joining_date}</td>
                <td className="p-3">
                  {d.leaving_date ? (
                    <span className="rounded-full bg-slate-100 px-2 py-0.5 text-xs text-slate-600">Left {d.leaving_date}</span>
                  ) : (
                    <span className="rounded-full bg-emerald-50 px-2 py-0.5 text-xs text-emerald-700">Active</span>
                  )}
                </td>
              </tr>
            ))}
            {!loading && items.length === 0 && (
              <tr><td colSpan={5} className="p-6 text-center text-slate-500">No driver found for "{q}".</td></tr>
            )}
          </tbody>
        </table>
      </div>
      {more && <p className="mt-2 text-sm text-slate-500">Showing the first 100 – type more to narrow it down.</p>}
    </div>
  );
}
