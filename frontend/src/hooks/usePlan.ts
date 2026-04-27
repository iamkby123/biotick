import { useAuth } from "@/lib/providers";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useEffect, useRef } from "react";
import { supabase } from "@/lib/supabase";
import { fetchAPI } from "@/lib/api";

export type Plan = "free" | "pro";

/**
 * Reads the current user's plan from the `profiles` table.
 *
 * Auto-heals the duplicate-account case: when a user signs in via email
 * and their profile says `free` but they actually paid via Stripe under
 * the same email, we silently call `/api/stripe/sync-me` which re-links
 * the existing Stripe subscription to this user_id and sets plan='pro'.
 * This fixes the "I logged in and now it's asking me to pay again" bug.
 */
export function usePlan() {
  const { user } = useAuth();
  const qc = useQueryClient();
  const triedSyncRef = useRef<string | null>(null);

  const { data: profile } = useQuery({
    queryKey: ["profile", user?.id],
    queryFn: async () => {
      if (!user) return null;
      const { data } = await supabase
        .from("profiles")
        .select("plan, is_admin, stripe_customer_id")
        .eq("id", user.id)
        .single();
      return data;
    },
    enabled: !!user,
  });

  // Auto-link Stripe sub on first profile load if profile says "free"
  // but user might actually have paid. Runs once per user_id per page
  // visit. Cheap server-side: one Stripe customer.list + subs.list call.
  useEffect(() => {
    if (!user?.id || !profile) return;
    if (profile.plan === "pro") return;
    // Already linked to a Stripe customer? Then this isn't the
    // duplicate-account problem — actual cancellation. Don't re-call.
    if (profile.stripe_customer_id) return;
    if (triedSyncRef.current === user.id) return;
    triedSyncRef.current = user.id;

    (async () => {
      try {
        const { data: sess } = await supabase.auth.getSession();
        const token = sess.session?.access_token;
        if (!token) return;
        const result = await fetchAPI<{ linked: boolean }>("/stripe/sync-me", {
          method: "POST",
          headers: { Authorization: `Bearer ${token}` },
          body: JSON.stringify({}),
        });
        if (result.linked) {
          // Force refetch so the UI flips from free → pro immediately
          qc.invalidateQueries({ queryKey: ["profile", user.id] });
        }
      } catch {
        // Silent — failures here are not fatal. User stays on free tier
        // and can manually re-purchase if needed; we don't want to alarm
        // them about an internal sync attempt.
      }
    })();
  }, [user?.id, profile, qc]);

  const plan: Plan = profile?.plan === "pro" ? "pro" : "free";
  const isPro = plan === "pro";
  const isAdmin = Boolean(profile?.is_admin);

  return { plan, isPro, isAdmin, isLoggedIn: !!user };
}
