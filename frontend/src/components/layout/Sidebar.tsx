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
  Users,
} from "lucide-react";
import { cn } from "@/lib/utils";
import { useTheme, useAuth } from "@/lib/providers";

const navItems = [
  { href: "/dashboard", label: "Dashboard", icon: LayoutDashboard },
  { href: "/companies", label: "Screener", icon: Search },
  { href: "/catalysts", label: "Catalysts", icon: Calendar },
  { href: "/pdufa", label: "PDUFA Calendar", icon: Pill },
  { href: "/conferences", label: "Conferences", icon: Users },
  { href: "/watchlist", label: "Watchlist", icon: Star },
];

export default function Sidebar() {
  const pathname = usePathname();
  const { theme, toggleTheme } = useTheme();
  const { user, signOut } = useAuth();

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
      <nav className="flex-1 px-3 py-3 space-y-px">
        <p className="text-[10px] font-semibold uppercase tracking-widest text-muted/60 px-3 pt-2 pb-2">
          Platform
        </p>
        {navItems.map((item) => {
          const isActive =
            pathname === item.href ||
            (item.href !== "/" && pathname.startsWith(item.href));
          const Icon = item.icon;

          return (
            <Link
              key={item.href}
              href={item.href}
              className={cn(
                "flex items-center gap-2.5 px-3 py-2 rounded-md text-[13px] font-medium transition-all duration-100",
                isActive
                  ? "bg-accent/15 text-accent"
                  : "text-muted hover:text-foreground hover:bg-surface-hover"
              )}
            >
              <Icon className={cn("w-4 h-4", isActive ? "text-accent" : "text-muted")} />
              {item.label}
            </Link>
          );
        })}
      </nav>

      {/* Bottom */}
      <div className="px-3 py-3 border-t border-border space-y-1">
        <button
          onClick={toggleTheme}
          className="flex items-center gap-2.5 px-3 py-2 rounded-md text-[13px] text-muted hover:text-foreground hover:bg-surface-hover w-full transition-all duration-100"
        >
          {theme === "dark" ? <Sun className="w-4 h-4" /> : <Moon className="w-4 h-4" />}
          {theme === "dark" ? "Light mode" : "Dark mode"}
        </button>
        {user ? (
          <button
            onClick={signOut}
            className="flex items-center gap-2.5 px-3 py-2 rounded-md text-[13px] text-muted hover:text-foreground hover:bg-surface-hover w-full transition-all duration-100"
          >
            <LogOut className="w-4 h-4" />
            Sign Out
          </button>
        ) : (
          <Link
            href="/login"
            className="flex items-center gap-2.5 px-3 py-2 rounded-md text-[13px] text-accent hover:bg-accent/10 w-full transition-all duration-100"
          >
            <LogIn className="w-4 h-4" />
            Sign In
          </Link>
        )}
      </div>
    </aside>
  );
}
