// Why /proxy: the browser fetches are routed same-origin to /proxy/*,
// which next.config.ts rewrites at the edge to the real backend
// (biotick-api.fly.dev). This keeps all client fetches on biotick.io so
// ad-blockers and privacy shields can't pattern-match on the fly.dev
// hostname or path names (insider-trades, filings, etc.). As a bonus,
// CORS preflights go away too.
//
// In Node/SSR or when NEXT_PUBLIC_API_URL is explicitly set, we fall back
// to hitting the backend directly — useful for local dev against a
// non-proxied backend.
function resolveApiBase(): string {
  // Always same-origin in the browser.
  if (typeof window !== "undefined") return "/proxy";
  // Server-side: honour the env var, otherwise default to local FastAPI.
  return process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000/api";
}

const API_BASE = resolveApiBase();

export async function fetchAPI<T>(
  endpoint: string,
  options?: RequestInit
): Promise<T> {
  const url = `${API_BASE}${endpoint}`;
  const controller = new AbortController();
  const timeout = setTimeout(() => controller.abort(), 30000);

  // IMPORTANT: spread options FIRST, then override headers + signal.
  // The previous order (...options last) replaced the merged headers
  // object when a caller passed custom headers, wiping out Content-Type
  // and making FastAPI read the body as a raw string instead of JSON.
  const res = await fetch(url, {
    ...options,
    headers: {
      "Content-Type": "application/json",
      ...(options?.headers || {}),
    },
    signal: controller.signal,
  });

  clearTimeout(timeout);

  if (!res.ok) {
    const error = await res.text();
    throw new Error(`API Error ${res.status}: ${error}`);
  }

  return res.json();
}
