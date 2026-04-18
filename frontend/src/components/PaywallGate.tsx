"use client";

import Link from "next/link";
import { Lock } from "lucide-react";
import { usePlan } from "@/hooks/usePlan";
import { useUpgradeUrl } from "@/lib/stripe";

export function ProBadge() {
  return (
    <span className="text-[9px] font-bold px-1.5 py-0.5 rounded bg-accent/15 text-accent uppercase tracking-wider">
      Pro
    </span>
  );
}

export function PaywallGate({
  children,
  feature,
}: {
  children: React.ReactNode;
  feature: string;
}) {
  const { isPro, isLoggedIn } = usePlan();
  const upgradeUrl = useUpgradeUrl();

  if (isPro) return <>{children}</>;

  return (
    <div className="relative">
      <div className="blur-sm pointer-events-none select-none opacity-50">
        {children}
      </div>
      <div className="absolute inset-0 flex items-center justify-center">
        <div className="bg-surface border border-border rounded-xl p-8 text-center max-w-sm shadow-2xl">
          <div className="w-12 h-12 rounded-full bg-accent/10 flex items-center justify-center mx-auto mb-4">
            <Lock className="w-6 h-6 text-accent" />
          </div>
          <h3 className="font-bold text-lg">Upgrade to Pro</h3>
          <p className="text-sm text-muted mt-2">
            {feature} is available on the Pro plan. Get full access to all biotech data.
          </p>
          <div className="flex flex-col gap-2 mt-6">
            <a
              href={upgradeUrl}
              target="_blank"
              rel="noopener noreferrer"
              className="block w-full py-3 rounded-lg bg-accent text-black font-semibold text-sm hover:bg-accent-hover transition-colors"
            >
              Upgrade — $19.99/mo
            </a>
            {!isLoggedIn && (
              <Link
                href="/login"
                className="block w-full py-2 text-sm text-muted hover:text-foreground transition"
              >
                Already Pro? Sign in
              </Link>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}

export function PaywallBanner({ feature }: { feature: string }) {
  const { isPro } = usePlan();
  const upgradeUrl = useUpgradeUrl();
  if (isPro) return null;

  return (
    <div className="rounded-lg border border-accent/20 bg-accent/5 p-4 flex items-center justify-between gap-4">
      <div className="flex items-center gap-3">
        <Lock className="w-4 h-4 text-accent shrink-0" />
        <p className="text-sm">
          <span className="font-medium">{feature}</span>
          <span className="text-muted"> — available with Pro</span>
        </p>
      </div>
      <a
        href={upgradeUrl}
        target="_blank"
        rel="noopener noreferrer"
        className="px-4 py-1.5 rounded-md bg-accent text-black text-xs font-semibold hover:bg-accent-hover transition shrink-0"
      >
        Upgrade
      </a>
    </div>
  );
}
