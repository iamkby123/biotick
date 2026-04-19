import type { NextConfig } from "next";

// All biotick-api.fly.dev requests are proxied through /proxy/* on the
// same origin (biotick.io). This keeps fetches same-origin so ad-blockers
// and privacy shields can't pattern-match on the fly.dev hostname or
// specific paths like /insider-trades. Vercel handles the proxying at
// the edge with negligible added latency.
const BACKEND_URL =
  process.env.BACKEND_URL || "https://biotick-api.fly.dev/api";

const nextConfig: NextConfig = {
  async rewrites() {
    return [
      {
        source: "/proxy/:path*",
        destination: `${BACKEND_URL}/:path*`,
      },
    ];
  },
};

export default nextConfig;
