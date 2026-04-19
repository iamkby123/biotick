import Link from "next/link";
import Sidebar from "@/components/layout/Sidebar";
import { CommandPalette } from "@/components/CommandPalette";

export default function AppLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <div className="flex h-full">
      <Sidebar />
      <main className="flex-1 overflow-auto bg-background">
        <div className="max-w-[1200px] mx-auto px-6 lg:px-10 py-8 page-transition">
          {children}
        </div>
        <AppFooter />
      </main>
      <CommandPalette />
    </div>
  );
}

/** Compact footer shown on every authenticated page. Carries the
 *  "not financial advice" disclaimer required wherever investment-adjacent
 *  content is displayed, plus privacy/terms links. */
function AppFooter() {
  return (
    <footer className="mt-16 border-t border-border">
      <div className="max-w-[1200px] mx-auto px-6 lg:px-10 py-6 text-[11px] text-muted/70 space-y-3">
        <p className="leading-relaxed">
          <span className="text-muted font-medium">Not financial advice.</span>{" "}
          Biotick is a research tool for informational purposes only. We are not a registered
          investment advisor. Nothing on this site is a recommendation to buy, sell, or hold any
          security. Biotech investing is volatile and you can lose your entire investment. Data
          is aggregated from public sources (SEC EDGAR, ClinicalTrials.gov, Finnhub) and provided
          without warranty — verify against the primary source before acting on it.
        </p>
        <div className="flex flex-wrap items-center gap-x-5 gap-y-1 pt-2 border-t border-border/50">
          <span>&copy; {new Date().getFullYear()} Biotick</span>
          <Link href="/privacy" className="hover:text-foreground transition">Privacy</Link>
          <Link href="/terms" className="hover:text-foreground transition">Terms</Link>
          <a href="mailto:contact@biotick.io" className="hover:text-foreground transition">Contact</a>
        </div>
      </div>
    </footer>
  );
}
