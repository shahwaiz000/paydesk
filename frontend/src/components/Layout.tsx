import { useEffect, useState } from "react";
import { NavLink, Navigate, Outlet, useLocation, useNavigate } from "react-router-dom";
import type { ReactNode } from "react";
import { DISPUTES_CHANGED, ROLE_LABELS, api } from "../api";
import { useAuth } from "../auth";

export default function Layout() {
  const { user, loading, logout } = useAuth();
  const navigate = useNavigate();
  const location = useLocation();
  const [search, setSearch] = useState("");
  const [openDisputes, setOpenDisputes] = useState(0);
  const [menuOpen, setMenuOpen] = useState(false);
  const staff = user?.role === "accountant" || user?.role === "finance_manager";

  // Badge on "Disputes": how many drivers are waiting for an answer
  useEffect(() => {
    if (!staff) return;
    const refresh = () =>
      api<{ open: number }>("/api/disputes/count").then((d) => setOpenDisputes(d.open)).catch(() => {});
    refresh();
    window.addEventListener(DISPUTES_CHANGED, refresh);
    const timer = window.setInterval(refresh, 60_000);
    return () => {
      window.removeEventListener(DISPUTES_CHANGED, refresh);
      window.clearInterval(timer);
    };
  }, [staff, location.pathname]);

  if (loading) {
    return <div className="flex min-h-screen items-center justify-center text-slate-500">Loading…</div>;
  }
  if (!user) return <Navigate to="/login" replace />;

  const links: { to: string; label: string; icon: ReactNode }[] =
    user.role === "driver"
      ? [{ to: "/", label: "My salary", icon: ICONS.home }]
      : [
          { to: "/", label: "Dashboard", icon: ICONS.home },
          ...(user.role === "cashier" ? [] : [{ to: "/months", label: "Payroll months", icon: ICONS.calendar }]),
          { to: "/payday", label: "Payday", icon: ICONS.cash },
          { to: "/drivers", label: "Drivers", icon: ICONS.people },
          ...(staff ? [{ to: "/disputes", label: "Driver questions", icon: ICONS.chat }] : []),
        ];

  const sidebar = (
    <div className="flex h-full flex-col">
      <div className="flex items-center gap-3 px-5 py-6">
        <span className="flex h-9 w-9 items-center justify-center rounded-lg bg-indigo-500 text-base font-bold text-white">P</span>
        <div>
          <p className="text-lg font-bold leading-tight tracking-tight text-slate-800">PayDesk</p>
          <p className="text-xs text-slate-500">Driver Payroll System</p>
        </div>
      </div>
      <nav className="flex-1 space-y-0.5 px-3">
        {links.map((l) => (
          <NavLink
            key={l.to}
            to={l.to}
            end={l.to === "/"}
            onClick={() => setMenuOpen(false)}
            className={({ isActive }) =>
              `flex items-center gap-3 rounded-lg px-3 py-2.5 text-[15px] font-medium ${
                isActive ? "bg-indigo-50 font-semibold text-indigo-700" : "text-slate-600 hover:bg-slate-100 hover:text-slate-800"
              }`
            }
          >
            <span className="h-5 w-5 shrink-0">{l.icon}</span>
            <span className="flex-1">{l.label}</span>
            {l.to === "/disputes" && openDisputes > 0 && (
              <span className="rounded-full bg-red-500 px-1.5 text-xs font-semibold text-white">{openDisputes}</span>
            )}
          </NavLink>
        ))}
      </nav>
      <div className="border-t border-slate-200 px-5 py-4">
        <p className="truncate text-sm font-semibold text-slate-800">{user.full_name}</p>
        <p className="text-xs text-slate-500">{ROLE_LABELS[user.role]}</p>
        <button onClick={logout} className="mt-3 text-sm font-semibold text-slate-600 hover:text-slate-800">
          Sign out
        </button>
      </div>
    </div>
  );

  return (
    <div className="min-h-screen bg-[#f4f6f9]">
      {/* Laptop: fixed menu on the left */}
      <aside className="fixed inset-y-0 left-0 z-30 hidden w-60 border-r border-slate-200 bg-white lg:block">{sidebar}</aside>

      {/* Phone: menu slides in */}
      {menuOpen && (
        <div className="fixed inset-0 z-40 lg:hidden">
          <div className="absolute inset-0 bg-black/30" onClick={() => setMenuOpen(false)} />
          <aside className="absolute inset-y-0 left-0 w-64 bg-white shadow-lg">{sidebar}</aside>
        </div>
      )}

      <div className="lg:pl-60">
        <header className="sticky top-0 z-20 flex h-14 items-center gap-3 border-b border-slate-200 bg-white px-4 sm:px-6">
          <button
            onClick={() => setMenuOpen(true)}
            className="-ml-1 rounded-lg p-1.5 text-slate-600 hover:bg-slate-100 lg:hidden"
            aria-label="Open menu"
          >
            <span className="block h-5 w-5">{ICONS.menu}</span>
          </button>
          <span className="font-bold text-slate-800 lg:hidden">PayDesk</span>
          {user.role !== "driver" && location.pathname !== "/drivers" && (
            <form
              className="ml-auto"
              onSubmit={(e) => {
                e.preventDefault();
                navigate(`/drivers?q=${encodeURIComponent(search.trim())}`);
                setSearch("");
                setMenuOpen(false);
              }}
            >
              <input
                value={search}
                onChange={(e) => setSearch(e.target.value)}
                placeholder="Search driver by name or ID"
                aria-label="Search driver"
                className="w-44 rounded-lg border border-slate-300 bg-white px-3 py-1.5 text-sm placeholder:text-slate-400 focus:border-indigo-600 focus:outline-none focus:ring-1 focus:ring-indigo-600 sm:w-72"
              />
            </form>
          )}
          {user.role === "driver" && (
            <button onClick={logout} className="ml-auto text-sm font-medium text-slate-600 hover:text-slate-800 lg:hidden">
              Sign out
            </button>
          )}
        </header>
        <main className="mx-auto max-w-6xl px-4 py-6 sm:px-6 sm:py-8">
          <Outlet />
        </main>
      </div>
    </div>
  );
}

// Simple line icons (no emoji)
const svg = (d: string) => (
  <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={1.7} strokeLinecap="round" strokeLinejoin="round" className="h-full w-full">
    <path d={d} />
  </svg>
);
const ICONS = {
  home: svg("M3 10.5 12 3l9 7.5V20a1 1 0 0 1-1 1h-5v-6h-6v6H4a1 1 0 0 1-1-1z"),
  calendar: svg("M4 6h16v14H4zM4 10h16M8 3v4M16 3v4"),
  cash: svg("M3 7h18v10H3zM12 15a3 3 0 1 0 0-6 3 3 0 0 0 0 6zM6 10v4M18 10v4"),
  people: svg("M9 11a4 4 0 1 0 0-8 4 4 0 0 0 0 8zM2 21v-1a6 6 0 0 1 12 0v1M16 3.5a4 4 0 0 1 0 7.5M22 21v-1a6 6 0 0 0-4-5.6"),
  chat: svg("M21 12a8 8 0 0 1-11.8 7L4 20l1.1-4.6A8 8 0 1 1 21 12z"),
  menu: svg("M4 6h16M4 12h16M4 18h16"),
};
