import { Navigate } from "react-router-dom";
import { useAuth } from "@/lib/auth-context";
import type { Role } from "@/types";

export function ProtectedRoute({ children, roles }: { children: React.ReactNode; roles?: Role[] }) {
  const { agent, loading } = useAuth();

  if (loading) return null;
  if (!agent) return <Navigate to="/login" replace />;
  // effective_role, not role: a self-registered campaign manager awaiting
  // admin activation still *is* a campaign_manager, but every privileged call
  // it makes 403s server-side. Gating on `role` would render the management
  // UI and then fail on each request.
  if (roles && !roles.some((r) => r === agent.effective_role)) return <Navigate to="/dashboard" replace />;

  return <>{children}</>;
}
