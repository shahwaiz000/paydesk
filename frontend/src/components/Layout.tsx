import { useState } from "react";
import { NavLink, Navigate, Outlet, useLocation, useNavigate } from "react-router-dom";
import { ROLE_LABELS } from "../api";
import { useAuth } from "../auth";

export default function Layout() {
  const { user, loading, logout } = useAuth();
  const navigate = useNavigate();
  const location = useLocation();
  const [search, setSearch] = useState("");

  if (loading) {
    return <div className="min-h-screen flex items-center justify-center text-slate-500">Loading…</div>;
  }
  if (!user) return <Navigate to="/login" replace />;

  return (
    <div className="min-h-screen bg-slate-50">
      <header className="bg-white border-b border-slate-200">
        <div className="mx-auto max-w-6xl flex flex-wrap items-center justify-between gap-2 px-4 py-3 sm:px-6">
          <div className="flex items-center gap-3">
            <span className="text-xl font-bold text-indigo-700">PayDesk</span>
            <span className="rounded-full bg-indigo-50 px-2.5 py-0.5 text-xs font-medium text-indigo-700">
              {ROLE_LABELS[user.role]}
            </span>
            {user.role === "driver" && (
              <NavLink to="/" className="ml-2 hidden text-sm font-medium text-slate-600 hover:text-slate-900 sm:inline">
                My payslips
              </NavLink>
            )}
            {user.role !== "driver" && (
              <nav className="ml-6 flex gap-1 text-sm">
                {[
                  { to: "/", label: "Home" },
                  ...(user.role === "cashier" ? [] : [{ to: "/months", label: "Payroll months" }]),
                  { to: "/drivers", label: "Drivers" },
                ].map((l) => (
                  <NavLink
                    key={l.to}
                    to={l.to}
                    end={l.to === "/"}
                    className={({ isActive }) =>
                      `rounded-lg px-3 py-1.5 ${isActive ? "bg-slate-100 font-semibold text-slate-900" : "text-slate-600 hover:bg-slate-50"}`
                    }
                  >
                    {l.label}
                  </NavLink>
                ))}
              </nav>
            )}
          </div>
          <div className="flex items-center gap-4 text-sm">
            {user.role !== "driver" && location.pathname !== "/drivers" && (
              <form
                onSubmit={(e) => {
                  e.preventDefault();
                  navigate(`/drivers?q=${encodeURIComponent(search.trim())}`);
                  setSearch("");
                }}
              >
                <input
                  value={search}
                  onChange={(e) => setSearch(e.target.value)}
                  placeholder="🔍 Search driver…"
                  className="w-56 rounded-lg border border-slate-300 px-3 py-1.5 focus:outline-none focus:ring-2 focus:ring-indigo-500"
                />
              </form>
            )}
            <span className="hidden text-slate-600 sm:inline">{user.full_name}</span>
            <button onClick={logout} className="rounded-lg border border-slate-300 px-3 py-1.5 hover:bg-slate-100">
              Log out
            </button>
          </div>
        </div>
      </header>
      <main className="mx-auto max-w-6xl px-4 py-6 sm:px-6 sm:py-8">
        <Outlet />
      </main>
    </div>
  );
}
