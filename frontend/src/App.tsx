import { Navigate, Route, Routes } from "react-router-dom";
import Layout from "./components/Layout";
import DisputesPage from "./pages/DisputesPage";
import DriverPage from "./pages/DriverPage";
import DriversPage from "./pages/DriversPage";
import HomePage from "./pages/HomePage";
import LoginPage from "./pages/LoginPage";
import MonthPage from "./pages/MonthPage";
import MonthsPage from "./pages/MonthsPage";
import MyPayslipPage from "./pages/MyPayslipPage";

export default function App() {
  return (
    <Routes>
      <Route path="/login" element={<LoginPage />} />
      <Route element={<Layout />}>
        <Route path="/" element={<HomePage />} />
        <Route path="/months" element={<MonthsPage />} />
        <Route path="/months/:id" element={<MonthPage />} />
        <Route path="/drivers" element={<DriversPage />} />
        <Route path="/drivers/:id" element={<DriverPage />} />
        <Route path="/disputes" element={<DisputesPage />} />
        <Route path="/payslips/:monthId" element={<MyPayslipPage />} />
      </Route>
      <Route path="*" element={<Navigate to="/" replace />} />
    </Routes>
  );
}
