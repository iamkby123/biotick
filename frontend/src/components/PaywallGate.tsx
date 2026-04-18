"use client";

import Link from "next/link";
import { useState } from "react";
import { Lock, Loader2 } from "lucide-react";
import { usePlan } from "@/hooks/usePlan";
import { useUpgrade } from "@/lib/stripe";

export function ProBadge() {
  return (
    <span className="text-[9px] font-bold px-1.5 py-0.5 rounded bg-accent/15 text-accent uppercase tracking-wider">
      Pro
    </span>
  );
}

function UpgradeButton({
  className = "block w-full py-3 rounded-lg bg-accent text-black font-semibold text-sm hover:bg-accent-hover transition-colors",
  label = "Upgrade — $19.99/mo",
}: {
  className?: string;
  label?: string;
}) {
  const upgrade = useUpgrade();
  const [loading, setLoading] = useState(false);

  const handleClick = async () => {
    setLoading(true);
    try {
      await upgrade();
    } finally {
      // If redirect succeeded the unmount happens before this runs.
      setLoading(false);
    }
  };

  return (
    <button
      type="button"
      onClick={handleClick}
      disabled={loading}
      className={className}
    >
      {loading ? (
        <span className="inline-flex items-center justify-center gap-2">
          <Loader2 className="w-4 h-4 animate-spin" />
          Loading…
        </span>
      ) : (
        label
      )}
    </button>
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

  if (isPro) return <>{children}</>;

  // Free users: do NOT render children. Show a dedicated upgrade panel so the
  // gated content is truly inaccessible (no blurred leak, no API calls).
  return (
    <div className="flex items-start sm:items-center justify-center min-h-[60vh] px-4 pt-6 sm:pt-4 pb-4">
      <div className="bg-surface border border-border rounded-xl p-6 sm:p-8 text-center w-full max-w-md shadow-2xl">
        <div className="w-12 h-12 rounded-full bg-accent/10 flex items-center justify-center mx-auto mb-4">
          <Lock className="w-6 h-6 text-accent" />
        </div>
        <h3 className="font-bold text-xl">{feature} is a Pro feature</h3>
        <p className="text-sm text-muted mt-2">
          Upgrade to Pro to unlock {feature.toLowerCase()} plus every other premium
          report on Biotick — full catalysts, insider trades, predictions, and more.
        </p>
        <div className="flex flex-col gap-2 mt-6">
          <UpgradeButton />
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
  );
}

export function PaywallBanner({ feature }: { feature: string }) {
  const { isPro } = usePlan();
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
      <UpgradeButton
        className="px-4 py-1.5 rounded-md bg-accent text-black text-xs font-semibold hover:bg-accent-hover transition shrink-0"
        label="Upgrade"
      />
    </div>
  );
}
