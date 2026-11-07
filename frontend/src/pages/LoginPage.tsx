import { useState, type FormEvent } from "react";
import { Navigate } from "react-router-dom";
import { useAuth } from "../auth";

const DEMO_ACCOUNTS = [
  { label: "Payroll Accountant", username: "accountant", password: "demo123" },
  { label: "Finance Manager", username: "manager", password: "demo123" },
  { label: "Cashier – Riyadh Azizia", username: "ruh-01", password: "demo123" },
  { label: "Driver D10001", username: "d10001", password: "1234" },
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
    <div className="min-h-screen grid lg:grid-cols-2 bg-slate-50">
      {/* Brand side */}
      <div className="hidden lg:flex flex-col justify-between bg-indigo-700 text-white p-12">
        <div className="text-2xl font-bold tracking-tight">PayDesk</div>
        <div>
          <h1 className="text-4xl font-bold leading-tight">
            Driver payroll,
            <br />
            from file upload to signed receipt.
          </h1>
          <p className="mt-4 text-indigo-100 max-w-md">
            Calculate 750 salaries, send every station its list in one click, and let drivers see
            exactly why every riyal was paid or deducted.
          </p>
        </div>
        <p className="text-sm text-indigo-200">Demo build · fake data only</p>
      </div>

      {/* Form side */}
      <div className="flex items-center justify-center p-6">
        <div className="w-full max-w-sm">
          <h2 className="text-2xl font-bold text-slate-800">Sign in</h2>
          <p className="text-slate-500 mt-1 text-sm">Drivers: use your driver ID and PIN.</p>

          <form onSubmit={handleSubmit} className="mt-6 space-y-4">
            <div>
              <label className="block text-sm font-medium text-slate-700">Username or driver ID</label>
              <input
                className="mt-1 w-full rounded-lg border border-slate-300 px-3 py-2 focus:outline-none focus:ring-2 focus:ring-indigo-500"
                value={username}
                onChange={(e) => setUsername(e.target.value)}
                autoFocus
              />
            </div>
            <div>
              <label className="block text-sm font-medium text-slate-700">Password or PIN</label>
              <input
                type="password"
                className="mt-1 w-full rounded-lg border border-slate-300 px-3 py-2 focus:outline-none focus:ring-2 focus:ring-indigo-500"
                value={password}
                onChange={(e) => setPassword(e.target.value)}
              />
            </div>
            {error && <p className="text-sm text-red-600">{error}</p>}
            <button
              type="submit"
              disabled={busy || !username || !password}
              className="w-full rounded-lg bg-indigo-600 py-2.5 font-semibold text-white hover:bg-indigo-700 disabled:opacity-50"
            >
              {busy ? "Signing in…" : "Sign in"}
            </button>
          </form>

          <div className="mt-8 rounded-xl border border-dashed border-slate-300 p-4">
            <p className="text-xs font-semibold uppercase tracking-wide text-slate-500">Demo accounts</p>
            <div className="mt-2 space-y-1">
              {DEMO_ACCOUNTS.map((a) => (
                <button
                  key={a.username}
                  type="button"
                  onClick={() => {
                    setUsername(a.username);
                    setPassword(a.password);
                  }}
                  className="flex w-full justify-between rounded-md px-2 py-1.5 text-sm hover:bg-slate-100"
                >
                  <span className="text-slate-700">{a.label}</span>
                  <span className="font-mono text-slate-400">{a.username}</span>
                </button>
              ))}
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
