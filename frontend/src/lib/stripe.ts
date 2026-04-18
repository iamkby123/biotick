import { useAuth } from "./providers";
import { fetchAPI } from "./api";

// Legacy static Payment Link — kept as a fallback for logged-out users.
// Logged-in users always go through the backend-generated Checkout Session
// so the webhook can match them by Supabase user id instead of by email.
const STRIPE_PRO_BASE = "https://buy.stripe.com/4gM14n9m1914cGm5lq73G02";

/**
 * Returns an `onUpgrade()` function that kicks off Stripe checkout.
 * - Logged in: POSTs to /api/stripe/create-checkout to get a session URL
 *   tied to the Supabase user id, then redirects.
 * - Logged out: opens the static Payment Link (their purchase will be linked
 *   via email fallback when they log in for the first time).
 */
export function useUpgrade() {
  const { user } = useAuth();

  return async () => {
    if (!user?.id) {
      window.open(STRIPE_PRO_BASE, "_blank", "noopener,noreferrer");
      return;
    }
    try {
      const { url } = await fetchAPI<{ url: string }>("/stripe/create-checkout", {
        method: "POST",
        body: JSON.stringify({ user_id: user.id, email: user.email }),
      });
      // Full navigation (not a new tab) so cookies/session are preserved on return.
      window.location.href = url;
    } catch (err) {
      console.error("Failed to create checkout session, falling back to payment link", err);
      const sep = STRIPE_PRO_BASE.includes("?") ? "&" : "?";
      const url = user.email
        ? `${STRIPE_PRO_BASE}${sep}prefilled_email=${encodeURIComponent(user.email)}`
        : STRIPE_PRO_BASE;
      window.open(url, "_blank", "noopener,noreferrer");
    }
  };
}

/**
 * @deprecated Use useUpgrade() instead. Kept for any callsites still reading
 * a plain URL. Returns the static payment link (with prefilled email) — does
 * NOT carry the Supabase user id, so webhook matching may fail.
 */
export function useUpgradeUrl() {
  const { user } = useAuth();
  if (user?.email) {
    const sep = STRIPE_PRO_BASE.includes("?") ? "&" : "?";
    return `${STRIPE_PRO_BASE}${sep}prefilled_email=${encodeURIComponent(user.email)}`;
  }
  return STRIPE_PRO_BASE;
}

export const STRIPE_PRO_URL = STRIPE_PRO_BASE;
