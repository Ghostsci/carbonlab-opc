import { lazy, Suspense } from "react";
import { Navigate, Route, Routes } from "react-router-dom";
import Layout from "./components/Layout";
import ProtectedRoute from "./components/ProtectedRoute";

const Login = lazy(() => import("./pages/Login"));
const Upload = lazy(() => import("./pages/Upload"));
const DataLedger = lazy(() => import("./pages/DataLedger"));
const CalculationWorkbench = lazy(() => import("./pages/CalculationWorkbench"));
const InstallationPassports = lazy(() => import("./pages/InstallationPassports"));
const AgentOps = lazy(() => import("./pages/AgentOps"));

export default function App() {
  return (
    <Suspense fallback={<PageFallback />}>
      <Routes>
        <Route path="/login" element={<Login />} />
        <Route
          element={
            <ProtectedRoute>
              <Layout />
            </ProtectedRoute>
          }
        >
          <Route index element={<Navigate to="/upload" replace />} />
          <Route path="/upload" element={<Upload />} />
          <Route path="/data-ledger" element={<DataLedger />} />
          <Route path="/calculations" element={<CalculationWorkbench />} />
          <Route path="/passports" element={<InstallationPassports />} />
          <Route path="/agent-ops" element={<AgentOps />} />
        </Route>
        <Route path="*" element={<Navigate to="/upload" replace />} />
      </Routes>
    </Suspense>
  );
}

function PageFallback() {
  return (
    <div className="flex min-h-screen items-center justify-center bg-[#f6f9ff] text-sm text-slate-500">
      页面加载中...
    </div>
  );
}
