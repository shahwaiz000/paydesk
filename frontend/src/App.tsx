import { useEffect, useState } from "react";

export default function App() {
  const [status, setStatus] = useState("checking...");

  useEffect(() => {
    fetch("http://localhost:8001/api/health")
      .then((res) => res.json())
      .then((data) => setStatus(data.status))
      .catch(() => setStatus("offline"));
  }, []);

  return (
    <div className="min-h-screen bg-slate-50 flex items-center justify-center">
      <div className="bg-white rounded-2xl shadow p-10 text-center">
        <h1 className="text-3xl font-bold text-slate-800">PayDesk</h1>
        <p className="text-slate-500 mt-2">
          Driver Payroll & Salary Distribution System
        </p>
        <p className="mt-6">
          Backend:{" "}
          <span
            className={
              status === "ok"
                ? "text-green-600 font-semibold"
                : "text-red-600 font-semibold"
            }
          >
            {status}
          </span>
        </p>
      </div>
    </div>
  );
}