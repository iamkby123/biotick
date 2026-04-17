"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
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
} from "lucide-react";
import { cn } from "@/lib/utils";
import { useTheme, useAuth } from "@/lib/providers";

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
      { href: "/competitors", label: "Competitors", icon: Grid3x3 },
      { href: "/historical", label: "Historical", icon: History },
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

  return (
    <aside className="w-[220px] bg-surface/50 backdrop-blur-sm border-r border-border flex flex-col shrink-0 h-screen sticky top-0">
      {/* Logo */}
      <div className="px-5 h-16 flex items-center border-b border-border">
        <Link href="/" className="flex items-center gap-2.5">
          <div className="w-7 h-7 rounded-md bg-accent flex items-center justify-center">
            <Activity className="w-4 h-4 text-black" />
          </div>
          <span className="font-bold text-[15px] tracking-tight">Biotick</span>
        </Link>
      </div>

      {/* Navigation */}
      <nav className="flex-1 px-3 py-2 space-y-1 overflow-y-auto">
        {navSections.map((section) => (
          <div key={section.label}>
            <p className="text-[9px] font-semibold uppercase tracking-[0.15em] text-muted/50 px-3 pt-3 pb-1">
              {section.label}
            </p>
            {section.items.map((item) => {
              const isActive =
                pathname === item.href ||
                (item.href !== "/" && pathname.startsWith(item.href));
              const Icon = item.icon;

              return (
                <Link
                  key={item.href}
                  href={item.href}
                  className={cn(
                    "flex items-center gap-2.5 px-3 py-[7px] rounded-md text-[13px] font-medium transition-all duration-100",
                    isActive
                      ? "bg-accent/15 text-accent"
                      : "text-muted hover:text-foreground hover:bg-surface-hover"
                  )}
                >
                  <Icon className={cn("w-3.5 h-3.5", isActive ? "text-accent" : "text-muted")} />
                  {item.label}
                </Link>
              );
            })}
          </div>
        ))}
      </nav>

      {/* Bottom */}
      <div className="px-3 py-3 border-t border-border space-y-1">
        <button
          onClick={toggleTheme}
          className="flex items-center gap-2.5 px-3 py-2 rounded-md text-[13px] text-muted hover:text-foreground hover:bg-surface-hover w-full transition-all duration-100"
        >
          {theme === "dark" ? <Sun className="w-3.5 h-3.5" /> : <Moon className="w-3.5 h-3.5" />}
          {theme === "dark" ? "Light mode" : "Dark mode"}
        </button>
        {loading ? null : user ? (
          <button
            onClick={signOut}
            className="flex items-center gap-2.5 px-3 py-2 rounded-md text-[13px] text-muted hover:text-foreground hover:bg-surface-hover w-full transition-all duration-100"
          >
            <LogOut className="w-3.5 h-3.5" />
            Sign Out
          </button>
        ) : (
          <Link
            href="/login"
            className="flex items-center gap-2.5 px-3 py-2 rounded-md text-[13px] text-accent hover:bg-accent/10 w-full transition-all duration-100"
          >
            <LogIn className="w-3.5 h-3.5" />
            Sign In
          </Link>
        )}
      </div>
    </aside>
  );
}
