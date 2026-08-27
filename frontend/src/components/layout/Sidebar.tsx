import { useState } from "react";
import { NavLink } from "react-router-dom";
import { LogOut, PanelLeftClose, PanelLeftOpen, Menu, X } from "lucide-react";
import { cn } from "@/lib/utils";
import type { LucideIcon } from "lucide-react";

export interface SidebarNavItem {
  to: string;
  label: string;
  icon: LucideIcon;
  end?: boolean;
}

/** Collapsible on desktop (icons-only toggle); a slide-in drawer with a
 * tap-to-dismiss backdrop on mobile, controlled by `mobileOpen`/`onMobileClose`. */
function Sidebar({
  navItems,
  userName,
  role,
  onLogout,
  mobileOpen,
  onMobileClose,
}: {
  navItems: SidebarNavItem[];
  userName: string;
  role: string;
  onLogout: () => void;
  mobileOpen: boolean;
  onMobileClose: () => void;
}) {
  const [collapsed, setCollapsed] = useState(false);

  return (
    <>
      {mobileOpen && <div className="fixed inset-0 z-40 bg-black/30 md:hidden" onClick={onMobileClose} />}
      <aside
        className={cn(
          "fixed inset-y-0 left-0 z-50 flex min-h-screen flex-col overflow-y-auto border-r border-border bg-card p-4 transition-all duration-200 md:sticky md:top-0 md:z-auto md:translate-x-0",
          collapsed ? "md:w-[72px]" : "md:w-60",
          "w-60",
          mobileOpen ? "translate-x-0" : "-translate-x-full"
        )}
      >
        <div className="mb-8 flex items-center justify-between">
          {!collapsed && <span className="truncate px-1 font-display text-lg font-bold">Tally333</span>}
          <button
            onClick={() => setCollapsed((v) => !v)}
            title={collapsed ? "Expand sidebar" : "Collapse sidebar"}
            className="hidden shrink-0 rounded-md p-1.5 text-muted-foreground hover:bg-muted hover:text-foreground md:flex"
          >
            {collapsed ? <PanelLeftOpen size={18} /> : <PanelLeftClose size={18} />}
          </button>
          <button
            onClick={onMobileClose}
            aria-label="Close menu"
            className="rounded-md p-1.5 text-muted-foreground hover:bg-muted hover:text-foreground md:hidden"
          >
            <X size={18} />
          </button>
        </div>

        <nav className="flex flex-col gap-1">
          {navItems.map(({ to, end, icon: Icon, label }) => (
            <NavLink
              key={to}
              to={to}
              end={end}
              title={collapsed ? label : undefined}
              onClick={onMobileClose}
              className={({ isActive }) =>
                cn(
                  "flex items-center gap-2.5 rounded-md px-3 py-2 text-sm font-medium transition-colors",
                  collapsed && "md:justify-center md:px-2",
                  isActive ? "bg-muted text-primary" : "text-muted-foreground hover:bg-muted hover:text-foreground"
                )
              }
            >
              <Icon size={17} className="shrink-0" />
              {!collapsed && <span className="truncate">{label}</span>}
            </NavLink>
          ))}
        </nav>

        <div className="mt-auto flex items-center justify-between gap-2 border-t border-border pt-4">
          {!collapsed && (
            <span className="truncate text-sm">
              <span className="font-medium">{userName}</span>{" "}
              <span className="block font-mono text-xs uppercase text-muted-foreground">{role}</span>
            </span>
          )}
          <button
            onClick={onLogout}
            title="Log out"
            className="shrink-0 rounded-md p-1.5 text-muted-foreground hover:bg-muted hover:text-foreground"
          >
            <LogOut size={16} />
          </button>
        </div>
      </aside>
    </>
  );
}

/** Wraps routed page content with the sidebar (desktop) / drawer (mobile) +
 * a mobile-only top bar carrying the hamburger + wordmark. */
export function SidebarShell({
  navItems,
  userName,
  role,
  onLogout,
  children,
}: {
  navItems: SidebarNavItem[];
  userName: string;
  role: string;
  onLogout: () => void;
  children: React.ReactNode;
}) {
  const [mobileOpen, setMobileOpen] = useState(false);

  return (
    <div className="flex min-h-screen flex-col bg-background text-foreground">
      <div className="sticky top-0 z-30 flex items-center justify-between border-b border-border bg-card px-4 py-3 md:hidden">
        <button
          onClick={() => setMobileOpen(true)}
          aria-label="Open menu"
          className="rounded-md p-1 text-muted-foreground hover:text-foreground"
        >
          <Menu size={22} />
        </button>
        <span className="font-display text-lg font-bold">Tally333</span>
        <span className="w-[22px]" />
      </div>

      <div className="flex flex-1 items-start">
        <Sidebar
          navItems={navItems}
          userName={userName}
          role={role}
          onLogout={onLogout}
          mobileOpen={mobileOpen}
          onMobileClose={() => setMobileOpen(false)}
        />
        <main className="min-w-0 flex-1 px-5 py-8">{children}</main>
      </div>
    </div>
  );
}
