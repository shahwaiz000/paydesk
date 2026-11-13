import { useEffect, useState, type ReactNode } from "react";
import { Link } from "react-router-dom";
import { api } from "../api";
import { useAuth } from "../auth";
import { sar } from "../format";
import MyPayslipsPage from "./MyPayslipsPage";
import { MONTH_STATUS, monthLabel, type MonthSummary, type Outbox } from "../types";

type Overview = Record<string, string | number | null>;

interface MonthTotals {
  drivers: number;
  net: number;
  gross: number;
  deductions: number;
  cash_net: number;
  bank_net: number;
}

interface PaydayTotals {
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

interface Payday {
  month: { id: number; period: string; month_name: string } | null;
  totals?: PaydayTotals;
  stations?: { state: string }[];
}

const CALCULATED = ["calculated", "submitted", "approved"];

export default function HomePage() {
  const { user } = useAuth();
  if (user?.role === "driver") return <MyPayslipsPage />;
  if (user?.role === "cashier") return <CashierDashboard />;
  return <StaffDashboard />;
}

// ------------------------------------------------------------------ accountant + finance manager

function StaffDashboard() {
  const { user } = useAuth();
  const [overview, setOverview] = useState<Overview | null>(null);
  const [months, setMonths] = useState<MonthSummary[]>([]);
  const [totals, setTotals] = useState<MonthTotals | null>(null);
  const [outbox, setOutbox] = useState<Outbox | null>(null);
  const [questions, setQuestions] = useState<number | null>(null);
  const [payday, setPayday] = useState<Payday | null>(null);
  const [error, setError] = useState("");

  useEffect(() => {
    api<Overview>("/api/overview").then(setOverview).catch((e: Error) => setError(e.message));
    api<{ open: number }>("/api/disputes/count").then((d) => setQuestions(d.open)).catch(() => {});
    api<Payday>("/api/payday").then(setPayday).catch(() => {});
    api<MonthSummary[]>("/api/months")
      .then((list) => {
        const sorted = [...list].sort((a, b) => b.period.localeCompare(a.period));
        setMonths(sorted);
        const latest = sorted[0];
        if (latest && CALCULATED.includes(latest.status)) {
          api<MonthTotals>(`/api/months/${latest.id}/summary`).then(setTotals).catch(() => {});
        }
        if (latest?.status === "approved") {
          api<Outbox>(`/api/months/${latest.id}/outbox`).then(setOutbox).catch(() => {});
        }
      })
      .catch(() => {});
  }, []);

  if (error) return <p className="text-red-600">{error}</p>;
  if (!overview || !user) return <p className="text-slate-500">Loading…</p>;

  const latest = months[0];
  const status = latest ? MONTH_STATUS[latest.status] : null;
  const waitingApproval = months.filter((m) => m.status === "submitted");
  const sentBack = months.filter((m) => m.status === "calculated" && m.returned_note);
  const pd = payday?.totals;
  const stationsDone = payday?.stations?.filter((s) => s.state === "all_paid").length ?? 0;

  const net = totals ? Math.round(totals.net) : null;
  const emailsDone = outbox ? outbox.delivered : 0;
  const emailsTotal = outbox ? outbox.prepared || outbox.stations : Number(overview.stations ?? 0);

  return (
    <div>
      {user.role === "finance_manager" && waitingApproval.length > 0 && (
        <Notice to={`/months/${waitingApproval[0].id}`} text={`${monthLabel(waitingApproval[0].period)} is waiting for your approval.`} />
      )}
      {user.role === "accountant" && sentBack.length > 0 && (
        <Notice to={`/months/${sentBack[0].id}`} text={`${monthLabel(sentBack[0].period)} was sent back: ${sentBack[0].returned_note}`} />
      )}

      <Banner
        eyebrow={latest ? `${monthLabel(latest.period)} payroll` : "Payroll"}
        big={net != null ? `SAR ${sar(net)}` : "Not calculated yet"}
        line={`${totals?.drivers ?? overview.drivers} drivers · ${overview.stations} stations · ${overview.cities} cities`}
        badge={status?.label}
        action={latest ? { to: `/months/${latest.id}`, label: "Open month" } : { to: "/months", label: "Payroll months" }}
        picture={
          <ChatPicture
            lines={[
              { from: "driver", text: "Why was 300 cut from my salary?" },
              { from: "bot", text: "SAR 300 was a traffic fine on 12 October (TF-2291). You earned SAR 2,008, so you get SAR 1,708." },
              { from: "driver", text: "ليش انخصم من راتبي؟" },
              { from: "bot", text: "تم خصم 300 ريال مخالفة مرورية بتاريخ 12 أكتوبر." },
            ]}
          />
        }
      />

      <h2 className="mt-10 text-lg font-bold text-slate-800">Automations this month</h2>
      <div className="mt-4 grid gap-5 lg:grid-cols-3">
        <AutoCard
          n="1"
          color="blue"
          icon={ICON.mail}
          title="Station salary emails"
          value={`${emailsDone} / ${emailsTotal}`}
          line={
            outbox?.run.seconds != null
              ? `Stations emailed in ${outbox.run.seconds} seconds`
              : latest?.status === "approved"
                ? "Ready to send"
                : "Sent when the month is approved"
          }
          to={latest ? `/months/${latest.id}` : "/months"}
        />
        <AutoCard
          n="2"
          color="green"
          icon={<BotAvatar size="h-11 w-11" />}
          title="AI driver assistant"
          value={questions === null ? "—" : questions === 0 ? "All answered" : `${questions} waiting`}
          line="Drivers ask on Telegram, the AI answers in seconds"
          to="/disputes"
        />
        <AutoCard
          n="3"
          color="amber"
          icon={ICON.cash}
          title="Cash confirmations"
          value={pd ? `${pd.confirmed} / ${pd.paid}` : "—"}
          line={pd ? `Paid drivers who confirmed · ${stationsDone} of ${payday?.stations?.length ?? 0} stations done` : "Starts on payday"}
          to="/payday"
          alert={pd && pd.wrong ? `${pd.wrong} wrong amount reported` : undefined}
        />
      </div>
    </div>
  );
}

const COLORS = {
  blue: "bg-indigo-50 text-indigo-600",
  green: "bg-emerald-50 text-emerald-600",
  amber: "bg-amber-50 text-amber-600",
};

const svg = (d: string) => (
  <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={1.8} strokeLinecap="round" strokeLinejoin="round" className="h-6 w-6">
    <path d={d} />
  </svg>
);
const ICON = {
  mail: svg("M3 6h18v12H3zM3 7l9 6 9-6"),
  chat: svg("M21 12a8 8 0 0 1-11.8 7L4 20l1.1-4.6A8 8 0 1 1 21 12z"),
  cash: svg("M3 7h18v10H3zM12 15a3 3 0 1 0 0-6 3 3 0 0 0 0 6z"),
};

function Banner({ eyebrow, big, line, badge, action, picture }: {
  eyebrow: string; big: string; line: string; badge?: string; action: { to: string; label: string }; picture?: ReactNode;
}) {
  return (
    <div className="rounded-2xl border border-indigo-200 bg-indigo-100 p-7 text-slate-800 sm:p-9">
      <div className="flex flex-wrap items-center justify-between gap-8">
        <div>
          <div className="flex items-center gap-3">
            <p className="text-base font-semibold text-indigo-700">{eyebrow}</p>
            {badge && <span className="rounded-full bg-emerald-100 px-2.5 py-0.5 text-xs font-semibold text-emerald-800">{badge}</span>}
          </div>
          <p className="mt-3 text-4xl font-bold tracking-tight sm:text-5xl">{big}</p>
          <p className="mt-2 text-base text-slate-600">{line}</p>
          <Link to={action.to} className="mt-6 inline-block rounded-lg bg-indigo-600 px-5 py-2.5 text-sm font-bold text-white hover:bg-indigo-700">
            {action.label}
          </Link>
        </div>
        {picture}
      </div>
    </div>
  );
}

// The AI salary assistant on Telegram - a picture of a real conversation
export function BotAvatar({ size = "h-9 w-9" }: { size?: string }) {
  return (
    <span className={`flex ${size} shrink-0 items-center justify-center rounded-full bg-indigo-600 text-white`}>
      <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={1.8} strokeLinecap="round" strokeLinejoin="round" className="h-[60%] w-[60%]">
        <rect x="4" y="8" width="16" height="11" rx="3" />
        <path d="M12 4v4M9 13h.01M15 13h.01M9.5 16h5" />
      </svg>
    </span>
  );
}

function ChatPicture({ lines }: { lines: { from: "driver" | "bot"; text: string }[] }) {
  return (
    <div className="w-full max-w-sm rounded-2xl border border-slate-200 bg-white p-4 text-slate-800 shadow-sm">
      <div className="flex items-center gap-3 border-b border-slate-100 pb-3">
        <BotAvatar />
        <div>
          <p className="text-sm font-bold">PayDesk AI assistant</p>
          <p className="text-xs text-emerald-600">Online on Telegram · English and Arabic</p>
        </div>
      </div>
      <div className="mt-3 space-y-2 text-[13px] leading-snug">
        {lines.map((l, i) =>
          l.from === "driver" ? (
            <p key={i} dir="auto" className="ml-auto w-fit max-w-[85%] rounded-2xl rounded-br-md bg-indigo-600 px-3 py-2 text-white">{l.text}</p>
          ) : (
            <p key={i} dir="auto" className="w-fit max-w-[90%] rounded-2xl rounded-bl-md bg-slate-100 px-3 py-2">{l.text}</p>
          ),
        )}
      </div>
    </div>
  );
}

function AutoCard({ n, color, icon, title, value, line, to, alert }: {
  n: string; color: keyof typeof COLORS; icon: ReactNode; title: string; value: string; line: string; to: string; alert?: string;
}) {
  return (
    <Link to={to} className="group flex flex-col rounded-2xl border border-slate-200 bg-white p-6 shadow-sm transition hover:shadow-md">
      <div className="flex items-center justify-between">
        <span className={`flex h-11 w-11 items-center justify-center rounded-xl ${COLORS[color]}`}>{icon}</span>
        <span className="text-sm font-bold text-slate-300">{n}</span>
      </div>
      <p className="mt-5 text-base font-bold text-slate-800">{title}</p>
      <p className="mt-2 text-4xl font-bold tracking-tight text-slate-800">{value}</p>
      <p className="mt-2 text-sm text-slate-500">{line}</p>
      {alert && <p className="mt-3 rounded-lg bg-red-50 px-3 py-2 text-sm font-semibold text-red-700">{alert}</p>}
      <p className="mt-auto pt-5 text-sm font-bold text-indigo-600 group-hover:underline">View details</p>
    </Link>
  );
}

function Notice({ to, text }: { to: string; text: string }) {
  return (
    <Link to={to} className="mt-6 flex items-center justify-between gap-4 rounded-xl border border-amber-200 bg-amber-50 px-5 py-4 text-sm text-amber-900 hover:bg-amber-100">
      <span className="font-medium">{text}</span>
      <span className="whitespace-nowrap font-medium">Open</span>
    </Link>
  );
}

// ------------------------------------------------------------------ station cashier

function CashierDashboard() {
  const [overview, setOverview] = useState<Overview | null>(null);
  const [payday, setPayday] = useState<Payday | null>(null);
  const [error, setError] = useState("");

  useEffect(() => {
    api<Overview>("/api/overview").then(setOverview).catch((e: Error) => setError(e.message));
    api<Payday>("/api/payday").then(setPayday).catch(() => {});
  }, []);

  if (error) return <p className="text-red-600">{error}</p>;
  if (!overview) return <p className="text-slate-500">Loading…</p>;

  const pd = payday?.totals;
  const bank = Number(overview.drivers ?? 0) - Number(overview.cash_drivers ?? 0);

  return (
    <div>
      <Banner
        eyebrow={`Station ${overview.station_code}${payday?.month ? ` · ${payday.month.month_name}` : ""}`}
        big={`${overview.station}`}
        line={pd ? `Cash to pay: SAR ${sar(pd.cash)} to ${pd.drivers} drivers` : `${overview.drivers} drivers · ${overview.cash_drivers} paid in cash · ${bank} by bank`}
        action={{ to: "/payday", label: "Go to payday" }}
        picture={
          <ChatPicture
            lines={[
              { from: "bot", text: "Your cashier marked you PAID SAR 1,708 for October. Did you receive exactly this amount?" },
              { from: "driver", text: "Yes, received" },
              { from: "bot", text: "Thank you. Saved – no paper signature needed." },
            ]}
          />
        }
      />
      {payday?.month && pd ? (
        <>
          <h2 className="mt-10 text-lg font-bold text-slate-800">Payday progress</h2>
          <div className="mt-4 grid gap-5 lg:grid-cols-3">
            <AutoCard n="1" color="blue" icon={ICON.cash} title="Drivers paid" value={`${pd.paid} / ${pd.drivers}`}
              line={`SAR ${sar(pd.paid_amount)} paid so far`} to="/payday" />
            <AutoCard n="2" color="green" icon={ICON.chat} title="Confirmed by driver" value={`${pd.confirmed} / ${pd.paid}`}
              line="Drivers who confirmed the amount on Telegram" to="/payday" />
            <AutoCard n="3" color="amber" icon={ICON.mail} title="Waiting for answer" value={`${pd.waiting}`}
              line="Asked on Telegram, no reply yet" to="/payday"
              alert={pd.wrong ? `${pd.wrong} wrong amount reported` : undefined} />
          </div>
        </>
      ) : (
        <p className="mt-8 rounded-xl border border-slate-200 bg-white p-5 text-sm text-slate-500">
          No approved month yet. Payday starts after the finance manager approves the salaries.
        </p>
      )}
    </div>
  );
}
