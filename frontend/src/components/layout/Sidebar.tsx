"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { useState, useEffect } from "react";
import {
  LayoutDashboard,
  Search,
  Calendar,
  BarChart3,
  Star,
  Sun,
  Moon,
  Activity,
  LogIn,
  LogOut,
  Pill,
  UserCheck,
  DollarSign,
  History,
  Users,
  Grid3x3,
  Newspaper,
  Megaphone,
  Handshake,
  TrendingUp,
  Landmark,
  ChevronLeft,
  ChevronRight,
} from "lucide-react";
import { cn } from "@/lib/utils";
import { useTheme, useAuth } from "@/lib/providers";
import { useCommandPalette } from "@/components/CommandPalette";

const navSections = [
  {
    label: "Overview",
    items: [
      { href: "/dashboard", label: "Dashboard", icon: LayoutDashboard },
      { href: "/companies", label: "Screener", icon: Search },
    ],
  },
  {
    label: "Catalysts",
    items: [
      { href: "/catalysts", label: "Calendar", icon: Calendar },
      { href: "/pdufa", label: "PDUFA Dates", icon: Pill },
      { href: "/adcom", label: "AdCom", icon: Users },
      { href: "/competitors", label: "Competitors", icon: Grid3x3 },
      { href: "/historical", label: "Historical", icon: History },
    ],
  },
  {
    label: "Edge",
    items: [
      { href: "/news", label: "News", icon: Newspaper },
      { href: "/press-releases", label: "Press Releases", icon: Megaphone },
      { href: "/deals", label: "Deals", icon: Handshake },
      { href: "/etf-flows", label: "ETF Flows", icon: TrendingUp },
      { href: "/congress-trades", label: "Congress Trades", icon: Landmark },
    ],
  },
  {
    label: "Market Data",
    items: [
      { href: "/earnings", label: "Earnings", icon: DollarSign },
      { href: "/insider-trades", label: "Insider Trades", icon: UserCheck },
      { href: "/conferences", label: "Conferences", icon: Users },
    ],
  },
  {
    label: "Personal",
    items: [
      { href: "/watchlist", label: "Watchlist", icon: Star },
    ],
  },
];

export default function Sidebar() {
  const pathname = usePathname();
  const { theme, toggleTheme } = useTheme();
  const { user, loading, signOut } = useAuth();
  const openPalette = useCommandPalette((s) => s.setOpen);
  const [collapsed, setCollapsed] = useState(false);
  const [mac, setMac] = useState(false);
  useEffect(() => {
    setMac(typeof navigator !== "undefined" && /Mac/i.test(navigator.platform));
  }, []);

  // Persist collapsed state
  useEffect(() => {
    const saved = localStorage.getItem("sidebar-collapsed");
    if (saved === "true") setCollapsed(true);
  }, []);

  const toggleCollapsed = () => {
    const next = !collapsed;
    setCollapsed(next);
    localStorage.setItem("sidebar-collapsed", String(next));
  };

  return (
    <aside
      className={cn(
        "relative bg-surface/50 backdrop-blur-sm border-r border-border flex flex-col shrink-0 h-screen sticky top-0 transition-all duration-200",
        collapsed ? "w-[60px]" : "w-[220px]"
      )}
    >
      {/* Logo */}
      <div className={cn(
        "h-16 flex items-center border-b border-border",
        collapsed ? "justify-center px-0" : "px-5"
      )}>
        <Link href="/" className="flex items-center gap-2.5">
          <div className="w-7 h-7 rounded-md bg-accent flex items-center justify-center shrink-0">
            <Activity className="w-4 h-4 text-black" />
          </div>
          {!collapsed && <span className="font-bold text-[15px] tracking-tight">Biotick</span>}
        </Link>
      </div>

      {/* Toggle button — floats on the right edge */}
      <button
        onClick={toggleCollapsed}
        className="absolute -right-3 top-20 w-6 h-6 rounded-full bg-surface border border-border text-muted hover:text-foreground hover:border-accent/50 flex items-center justify-center shadow-sm transition-colors z-10"
        title={collapsed ? "Expand sidebar" : "Collapse sidebar"}
      >
        {collapsed ? <ChevronRight className="w-3 h-3" /> : <ChevronLeft className="w-3 h-3" />}
      </button>

      {/* Quick search trigger — opens the Cmd+K palette */}
      <div className={cn("pt-3", collapsed ? "px-1.5" : "px-3")}>
        <button
          onClick={() => openPalette(true)}
          title={collapsed ? "Search (⌘K)" : undefined}
          className={cn(
            "w-full flex items-center rounded-md border border-border/60 bg-surface-hover/40 text-muted hover:text-foreground hover:border-border transition-all duration-100",
            collapsed ? "justify-center px-0 py-2" : "gap-2 px-3 py-1.5"
          )}
        >
          <Search className={collapsed ? "w-4 h-4" : "w-3.5 h-3.5"} />
          {!collapsed && (
            <>
              <span className="text-[12px] flex-1 text-left">Search…</span>
              <kbd className="text-[10px] font-mono border border-border rounded px-1 py-0.5">
                {mac ? "⌘K" : "Ctrl+K"}
              </kbd>
            </>
          )}
        </button>
      </div>

      {/* Navigation */}
      <nav className={cn(
        "flex-1 py-2 space-y-1 overflow-y-auto overflow-x-hidden",
        collapsed ? "px-1.5" : "px-3"
      )}>
        {navSections.map((section) => (
          <div key={section.label}>
            {!collapsed && (
              <p className="text-[9px] font-semibold uppercase tracking-[0.15em] text-muted/50 px-3 pt-3 pb-1">
                {section.label}
              </p>
            )}
            {collapsed && <div className="h-2" />}
            {section.items.map((item) => {
              const isActive =
                pathname === item.href ||
                (item.href !== "/" && pathname.startsWith(item.href));
              const Icon = item.icon;

              return (
                <Link
                  key={item.href}
                  href={item.href}
                  title={collapsed ? item.label : undefined}
                  className={cn(
                    "flex items-center rounded-md text-[13px] font-medium transition-all duration-100 group",
                    collapsed ? "justify-center px-0 py-2" : "gap-2.5 px-3 py-[7px]",
                    isActive
                      ? "bg-accent/15 text-accent"
                      : "text-muted hover:text-foreground hover:bg-surface-hover"
                  )}
                >
                  <Icon className={cn(
                    collapsed ? "w-4 h-4" : "w-3.5 h-3.5",
                    isActive ? "text-accent" : "text-muted"
                  )} />
                  {!collapsed && item.label}
                </Link>
              );
            })}
          </div>
        ))}
      </nav>

      {/* Bottom */}
      <div className={cn(
        "py-3 border-t border-border space-y-1",
        collapsed ? "px-1.5" : "px-3"
      )}>
        <button
          onClick={toggleTheme}
          title={collapsed ? (theme === "dark" ? "Light mode" : "Dark mode") : undefined}
          className={cn(
            "flex items-center rounded-md text-[13px] text-muted hover:text-foreground hover:bg-surface-hover w-full transition-all duration-100",
            collapsed ? "justify-center px-0 py-2" : "gap-2.5 px-3 py-2"
          )}
        >
          {theme === "dark" ? <Sun className={collapsed ? "w-4 h-4" : "w-3.5 h-3.5"} /> : <Moon className={collapsed ? "w-4 h-4" : "w-3.5 h-3.5"} />}
          {!collapsed && (theme === "dark" ? "Light mode" : "Dark mode")}
        </button>
        {loading ? null : user ? (
          <button
            onClick={signOut}
            title={collapsed ? "Sign Out" : undefined}
            className={cn(
              "flex items-center rounded-md text-[13px] text-muted hover:text-foreground hover:bg-surface-hover w-full transition-all duration-100",
              collapsed ? "justify-center px-0 py-2" : "gap-2.5 px-3 py-2"
            )}
          >
            <LogOut className={collapsed ? "w-4 h-4" : "w-3.5 h-3.5"} />
            {!collapsed && "Sign Out"}
          </button>
        ) : (
          <Link
            href="/login"
            title={collapsed ? "Sign In" : undefined}
            className={cn(
              "flex items-center rounded-md text-[13px] text-accent hover:bg-accent/10 w-full transition-all duration-100",
              collapsed ? "justify-center px-0 py-2" : "gap-2.5 px-3 py-2"
            )}
          >
            <LogIn className={collapsed ? "w-4 h-4" : "w-3.5 h-3.5"} />
            {!collapsed && "Sign In"}
          </Link>
        )}
      </div>
    </aside>
  );
}
