/* eslint-disable react-refresh/only-export-components */
export function sar(n: number | null | undefined): string {
  if (n === null || n === undefined) return "—";
  return n.toLocaleString("en-US", { minimumFractionDigits: 0, maximumFractionDigits: 2 });
}

export const FLAG_LABELS: Record<string, { label: string; style: string }> = {
  capped: { label: "Deductions capped", style: "bg-red-50 text-red-700" },
  unusual_change: { label: "Unusual change", style: "bg-amber-50 text-amber-700" },
  no_deliveries: { label: "No deliveries", style: "bg-amber-50 text-amber-700" },
  joiner: { label: "Joined mid-month", style: "bg-sky-50 text-sky-700" },
  leaver: { label: "Left mid-month", style: "bg-slate-100 text-slate-600" },
};

export function FlagChip({ flag }: { flag: string }) {
  const f = FLAG_LABELS[flag] ?? { label: flag, style: "bg-slate-100 text-slate-600" };
  return <span className={`whitespace-nowrap rounded-full px-2 py-0.5 text-xs font-medium ${f.style}`}>{f.label}</span>;
}

// Is this payslip final (approved) or can it still change?
export function StatusBadge({ final, light }: { final: boolean; light?: boolean }) {
  if (final) {
    return (
      <span className={`rounded-full px-2.5 py-0.5 text-xs font-medium ${light ? "bg-white/20 text-white" : "bg-emerald-50 text-emerald-700"}`}>
        ✓ Final
      </span>
    );
  }
  return (
    <span className={`rounded-full px-2.5 py-0.5 text-xs font-medium ${light ? "bg-amber-300/30 text-amber-100" : "bg-amber-50 text-amber-700"}`}>
      Not final yet
    </span>
  );
}
