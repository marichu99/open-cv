import { Navigate } from "react-router-dom";
import { useAuth } from "@/lib/auth-context";
import type { Role } from "@/types";

export function ProtectedRoute({ children, roles }: { children: React.ReactNode; roles?: Role[] }) {
  const { agent, loading } = useAuth();

  if (loading) return null;
  if (!agent) return <Navigate to="/login" replace />;
  if (roles && !roles.includes(agent.role)) return <Navigate to="/dashboard" replace />;

  return <>{children}</>;
}
