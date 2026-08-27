import { createContext, useContext, useEffect, useState, type ReactNode } from "react";
import { api, getToken, setToken } from "@/lib/api";
import type { Agent } from "@/types";

interface AuthState {
  agent: Agent | null;
  loading: boolean;
  login: (token: string, agent: Agent) => void;
  logout: () => void;
}

const AuthContext = createContext<AuthState | undefined>(undefined);

export function AuthProvider({ children }: { children: ReactNode }) {
  const [agent, setAgent] = useState<Agent | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    const token = getToken();
    if (!token) {
      setLoading(false);
      return;
    }
    api
      .get("/api/auth/me")
      .then((res) => setAgent(res.data))
      .catch(() => setToken(null))
      .finally(() => setLoading(false));
  }, []);

  function login(token: string, agentData: Agent) {
    setToken(token);
    setAgent(agentData);
  }

  function logout() {
    setToken(null);
    setAgent(null);
  }

  return <AuthContext.Provider value={{ agent, loading, login, logout }}>{children}</AuthContext.Provider>;
}

export function useAuth() {
  const ctx = useContext(AuthContext);
  if (!ctx) throw new Error("useAuth must be used within AuthProvider");
  return ctx;
}
