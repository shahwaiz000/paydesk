import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { api } from "../api";
import { useAuth } from "../auth";

type Overview = Record<string, string | number | null>;

function Stat({ label, value }: { label: string; value: string | number | null }) {
  return (
    <div className="rounded-2xl bg-white p-5 shadow-sm border border-slate-200">
      <p className="text-sm text-slate-500">{label}</p>
      <p className="mt-1 text-3xl font-bold text-slate-800">{value ?? "—"}</p>
    </div>
  );
}

function Row({ label, value }: { label: string; value: string | number | null }) {
  return (
    <div className="flex justify-between py-2 border-b border-slate-100 last:border-0">
      <span className="text-slate-500">{label}</span>
      <span className="font-medium text-slate-800">{value ?? "—"}</span>
    </div>
  );
}

export default function HomePage() {
  const { user } = useAuth();
  const [data, setData] = useState<Overview | null>(null);
  const [error, setError] = useState("");

  useEffect(() => {
    api<Overview>("/api/overview")
      .then(setData)
      .catch((e: Error) => setError(e.message));
  }, []);

  if (error) return <p className="text-red-600">{error}</p>;
  if (!data || !user) return <p className="text-slate-500">Loading…</p>;

  if (user.role === "accountant" || user.role === "finance_manager") {
    return (
      <div>
        <h1 className="text-2xl font-bold text-slate-800">Welcome, {user.full_name}</h1>
        <p className="text-slate-500 mt-1">Company-wide payroll overview</p>
        <div className="mt-6 grid grid-cols-2 lg:grid-cols-5 gap-4">
          <Stat label="Stations" value={data.stations} />
          <Stat label="Cities" value={data.cities} />
          <Stat label="Drivers" value={data.drivers} />
          <Stat label="Paid in cash" value={data.cash_drivers} />
          <Stat label="Paid by bank" value={data.bank_drivers} />
        </div>
        <Link
          to="/months"
          className="mt-8 block rounded-2xl border border-dashed border-indigo-300 bg-indigo-50 p-6 text-indigo-800 hover:bg-indigo-100"
        >
          Go to <b>Payroll months</b> to upload this month's files →
        </Link>
      </div>
    );
  }

  if (user.role === "cashier") {
    return (
      <div>
        <h1 className="text-2xl font-bold text-slate-800">{data.station}</h1>
        <p className="text-slate-500 mt-1">Station {data.station_code}</p>
        <div className="mt-6 grid grid-cols-2 gap-4 max-w-lg">
          <Stat label="Drivers at this station" value={data.drivers} />
          <Stat label="Paid in cash here" value={data.cash_drivers} />
        </div>
      </div>
    );
  }

  // Driver
  return (
    <div className="max-w-md">
      <h1 className="text-2xl font-bold text-slate-800">Hello, {data.name}</h1>
      <p className="text-slate-500 mt-1">Your payslips will appear here.</p>
      <div className="mt-6 rounded-2xl bg-white p-5 shadow-sm border border-slate-200">
        <Row label="Driver ID" value={data.driver_id} />
        <Row label="Station" value={data.station} />
        <Row label="Joining date" value={data.joining_date} />
        <Row
          label="Salary paid by"
          value={data.payment_method === "Bank" ? `Bank ···· ${data.iban_last4}` : "Cash at station"}
        />
      </div>
    </div>
  );
}
