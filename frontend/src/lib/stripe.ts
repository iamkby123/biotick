import { useAuth } from "./providers";
import { fetchAPI } from "./api";
import { supabase } from "./supabase";

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
    // Logged out: no JWT to send — use the static Payment Link (opens new tab).
    if (!user?.id) {
      window.open(STRIPE_PRO_BASE, "_blank", "noopener,noreferrer");
      return;
    }

    // Authenticated flow: send the Supabase access token so the backend
    // can derive the user id from the verified JWT (no spoofing).
    const { data: sess } = await supabase.auth.getSession();
    const token = sess.session?.access_token;
    if (!token) {
      throw new Error(
        "Couldn't get your Supabase session. Try signing out and back in."
      );
    }

    const { url } = await fetchAPI<{ url: string }>("/stripe/create-checkout", {
      method: "POST",
      headers: { Authorization: `Bearer ${token}` },
      body: JSON.stringify({ email: user.email }),
    });

    // Navigate in the same tab so cookies/session are preserved on return.
    window.location.href = url;
    // Errors (network / backend 401 / etc.) bubble up to the caller so the
    // UI can show the real message instead of a silent no-op.
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
