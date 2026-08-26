import { Link } from "react-router-dom";
import { LayoutDashboard, Camera, Users, ShieldCheck } from "lucide-react";
import { useAuth } from "@/lib/auth-context";
import { Button } from "@/components/ui/button";
import { SidebarShell, type SidebarNavItem } from "@/components/layout/Sidebar";
import type { Role } from "@/types";

const SIDEBAR_NAV: (SidebarNavItem & { roles: Role[] | null })[] = [
  { to: "/dashboard", label: "Dashboard", icon: LayoutDashboard, roles: null, end: true },
  { to: "/agent", label: "Agent upload", icon: Camera, roles: ["agent"] },
  { to: "/campaign-manager", label: "Campaign manager", icon: Users, roles: ["campaign_manager", "admin"] },
  { to: "/admin", label: "Moderation", icon: ShieldCheck, roles: ["coordinator", "admin"] },
];

export function AppShell({ children }: { children: React.ReactNode }) {
  const { agent, logout } = useAuth();

  if (agent) {
    const navItems = SIDEBAR_NAV.filter((item) => !item.roles || item.roles.includes(agent.role));
    return (
      <SidebarShell navItems={navItems} userName={agent.full_name} role={agent.role} onLogout={logout}>
        <div className="mx-auto max-w-6xl">{children}</div>
      </SidebarShell>
    );
  }

  // Logged out: a minimal top bar. Signing up as any role — agent or
  // campaign manager — happens on "/" via a role picker, not via separate
  // header links. No Dashboard link here — it requires login now.
  return (
    <div className="min-h-screen bg-background text-foreground">
      <header className="border-b border-border">
        <div className="mx-auto flex max-w-6xl items-center justify-between px-5 py-3">
          <Link to="/" className="font-display text-lg font-bold">
            Tally333
          </Link>
          <nav className="flex items-center gap-4 text-sm font-medium text-muted-foreground">
            <Link to="/agent" className="hover:text-foreground">
              Agent upload
            </Link>
          </nav>
          <Link to="/login">
            <Button size="sm">Sign in</Button>
          </Link>
        </div>
      </header>
      <main className="mx-auto max-w-6xl px-5 py-8">{children}</main>
    </div>
  );
}
