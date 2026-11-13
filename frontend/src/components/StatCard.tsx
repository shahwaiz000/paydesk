import type { ReactNode } from "react";

// One number with a clear label and a short line that explains it.
export default function StatCard({ label, value, note, tone }: {
  label: string;
  value: ReactNode;
  note?: ReactNode;
  tone?: "good" | "warn" | "bad";
}) {
  const color = tone === "good" ? "text-emerald-700" : tone === "warn" ? "text-amber-700" : tone === "bad" ? "text-red-600" : "text-slate-800";
  return (
    <div className="rounded-xl border border-slate-200 bg-white p-5 shadow-sm">
      <p className="text-sm font-semibold text-slate-600">{label}</p>
      <p className={`mt-2 text-3xl font-bold tracking-tight ${color}`}>{value}</p>
      {note && <p className="mt-1 text-sm text-slate-500">{note}</p>}
    </div>
  );
}

export function Section({ title, action, children }: { title: string; action?: ReactNode; children: ReactNode }) {
  return (
    <section className="mt-8">
      <div className="mb-3 flex items-center justify-between gap-4">
        <h2 className="text-lg font-bold text-slate-800">{title}</h2>
        {action}
      </div>
      {children}
    </section>
  );
}
