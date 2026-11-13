import { useState, type FormEvent } from "react";
import { Navigate } from "react-router-dom";
import { useAuth } from "../auth";

const DEMO_ACCOUNTS = [
  { label: "Payroll Accountant", username: "accountant", password: "demo123" },
  { label: "Finance Manager", username: "manager", password: "demo123" },
  { label: "Station Cashier – Riyadh Azizia", username: "ruh-01", password: "demo123" },
  { label: "Driver – D10001", username: "d10001", password: "1234" },
];

export default function LoginPage() {
  const { user, login } = useAuth();
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);

  if (user) return <Navigate to="/" replace />;

  async function handleSubmit(e: FormEvent) {
    e.preventDefault();
    setError("");
    setBusy(true);
    try {
      await login(username, password);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Login failed");
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="flex min-h-screen flex-col items-center justify-center bg-[#f4f6f9] px-4 py-10">
      <div className="w-full max-w-sm">
        <div className="mb-7 flex flex-col items-center text-center">
          <span className="flex h-12 w-12 items-center justify-center rounded-xl bg-indigo-600 text-xl font-bold text-white shadow-md">P</span>
          <p className="mt-3 text-2xl font-bold tracking-tight text-slate-800">PayDesk</p>
          <p className="mt-0.5 text-sm text-slate-500">Driver Payroll System</p>
        </div>

        <div className="rounded-xl border border-slate-200 bg-white p-6 shadow-md sm:p-8">
          <h1 className="text-xl font-bold text-slate-800">Sign in to your account</h1>
          <form onSubmit={handleSubmit} className="mt-5 space-y-4">
            <div>
              <label htmlFor="username" className="block text-sm font-medium text-slate-700">Username or driver ID</label>
              <input
                id="username"
                autoComplete="username"
                className="mt-1.5 w-full rounded-lg border border-slate-300 px-3 py-2.5 text-sm focus:border-indigo-600 focus:outline-none focus:ring-1 focus:ring-indigo-600"
                value={username}
                onChange={(e) => setUsername(e.target.value)}
                autoFocus
              />
            </div>
            <div>
              <label htmlFor="password" className="block text-sm font-medium text-slate-700">Password or PIN</label>
              <input
                id="password"
                type="password"
                autoComplete="current-password"
                className="mt-1.5 w-full rounded-lg border border-slate-300 px-3 py-2.5 text-sm focus:border-indigo-600 focus:outline-none focus:ring-1 focus:ring-indigo-600"
                value={password}
                onChange={(e) => setPassword(e.target.value)}
              />
            </div>
            {error && <p className="rounded-lg bg-red-50 px-3 py-2 text-sm text-red-700">{error}</p>}
            <button
              type="submit"
              disabled={busy || !username || !password}
              className="w-full rounded-lg bg-indigo-600 py-3 text-sm font-bold text-white hover:bg-indigo-700 disabled:opacity-50"
            >
              {busy ? "Signing in…" : "Sign in"}
            </button>
          </form>
        </div>

        <div className="mt-6 rounded-xl border border-slate-200 bg-white p-4 shadow-sm">
          <p className="text-xs font-semibold uppercase tracking-wide text-slate-500">Demo accounts</p>
          <div className="mt-2 divide-y divide-slate-100">
            {DEMO_ACCOUNTS.map((a) => (
              <button
                key={a.username}
                type="button"
                onClick={() => {
                  setUsername(a.username);
                  setPassword(a.password);
                  setError("");
                }}
                className="flex w-full items-center justify-between py-2.5 text-left text-sm font-medium hover:text-indigo-600"
              >
                <span className="text-slate-700">{a.label}</span>
                <span className="font-mono text-xs text-slate-400">{a.username}</span>
              </button>
            ))}
          </div>
        </div>
        <p className="mt-4 text-center text-xs text-slate-400">Demo version · sample data only</p>
      </div>
    </div>
  );
}
