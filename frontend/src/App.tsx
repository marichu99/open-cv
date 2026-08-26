import { BrowserRouter, Routes, Route, Navigate } from "react-router-dom";
import { Toaster } from "sonner";
import { AuthProvider } from "@/lib/auth-context";
import { AppShell } from "@/components/layout/AppShell";
import { ProtectedRoute } from "@/components/ProtectedRoute";
import { DashboardPage } from "@/pages/DashboardPage";
import { UploadPage } from "@/pages/UploadPage";
import { LoginPage } from "@/pages/LoginPage";
import { SignupPage } from "@/pages/SignupPage";
import { AdminPage } from "@/pages/AdminPage";
import { CampaignManagerPage } from "@/pages/CampaignManagerPage";

export default function App() {
  return (
    <AuthProvider>
      <BrowserRouter>
        <AppShell>
          <Routes>
            <Route path="/" element={<SignupPage />} />
            <Route
              path="/dashboard"
              element={
                <ProtectedRoute>
                  <DashboardPage />
                </ProtectedRoute>
              }
            />
            <Route path="/agent" element={<UploadPage />} />
            <Route path="/login" element={<LoginPage />} />
            {/* Folded into "/"'s role picker — kept as a redirect for anyone with the old link. */}
            <Route path="/campaign-manager/signup" element={<Navigate to="/?role=campaign_manager" replace />} />
            <Route
              path="/campaign-manager"
              element={
                <ProtectedRoute roles={["campaign_manager", "admin"]}>
                  <CampaignManagerPage />
                </ProtectedRoute>
              }
            />
            <Route
              path="/admin"
              element={
                <ProtectedRoute roles={["coordinator", "admin"]}>
                  <AdminPage />
                </ProtectedRoute>
              }
            />
          </Routes>
        </AppShell>
      </BrowserRouter>
      <Toaster richColors position="top-right" duration={5000} visibleToasts={3} />
    </AuthProvider>
  );
}
