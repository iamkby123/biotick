import { useAuth } from "./providers";

const STRIPE_PRO_BASE = "https://buy.stripe.com/4gM14n9m1914cGm5lq73G02";

/** Returns the Stripe checkout URL with prefilled_email so the webhook can match the user. */
export function useUpgradeUrl() {
  const { user } = useAuth();
  if (user?.email) {
    const sep = STRIPE_PRO_BASE.includes("?") ? "&" : "?";
    return `${STRIPE_PRO_BASE}${sep}prefilled_email=${encodeURIComponent(user.email)}`;
  }
  return STRIPE_PRO_BASE;
}

export const STRIPE_PRO_URL = STRIPE_PRO_BASE;
