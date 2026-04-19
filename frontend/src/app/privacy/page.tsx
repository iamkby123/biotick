import type { Metadata } from "next";
import Link from "next/link";
import { Activity } from "lucide-react";

export const metadata: Metadata = {
  title: "Privacy Policy · Biotick",
  description:
    "How Biotick collects, uses, and protects your information.",
};

export default function PrivacyPage() {
  return (
    <div className="min-h-screen bg-background">
      <nav className="sticky top-0 z-50 border-b border-border bg-background/90 backdrop-blur-xl">
        <div className="max-w-3xl mx-auto px-6 h-16 flex items-center">
          <Link href="/" className="flex items-center gap-2.5">
            <div className="w-7 h-7 rounded-md bg-accent flex items-center justify-center">
              <Activity className="w-4 h-4 text-black" />
            </div>
            <span className="font-bold text-[15px] tracking-tight">Biotick</span>
          </Link>
        </div>
      </nav>

      <main className="max-w-3xl mx-auto px-6 py-16 prose-custom">
        <h1 className="text-3xl md:text-4xl font-bold tracking-tight">Privacy Policy</h1>
        <p className="text-sm text-muted mt-2">Last updated: April 19, 2026</p>

        <p className="mt-8 text-[15px] leading-relaxed text-muted">
          Biotick (&ldquo;we&rdquo;, &ldquo;us&rdquo;) operates{" "}
          <a href="https://biotick.io" className="text-accent hover:underline">
            biotick.io
          </a>
          . This policy explains what we collect, how we use it, and your
          rights. If anything here is unclear, email us at{" "}
          <a href="mailto:contact@biotick.io" className="text-accent hover:underline">
            contact@biotick.io
          </a>
          .
        </p>

        <Section title="What we collect">
          <ul>
            <li>
              <strong>Account info</strong>: your email address and (for email/password signups) your password.
              Passwords are hashed by Supabase; we never see them in plaintext.
            </li>
            <li>
              <strong>Subscription info</strong>: if you upgrade to Pro, Stripe processes your payment.
              We receive only a Stripe customer ID and subscription status. Card details never touch our servers.
            </li>
            <li>
              <strong>Usage info</strong>: pages you view, watchlist entries you create, and session
              timing. Used to operate the service.
            </li>
            <li>
              <strong>Request metadata</strong>: IP address and user agent on API calls, briefly, for
              rate limiting and abuse prevention. Not used to build a profile of you.
            </li>
          </ul>
        </Section>

        <Section title="What we don't do">
          <ul>
            <li>We don&apos;t sell your data.</li>
            <li>We don&apos;t use marketing cookies or third-party ad tracking.</li>
            <li>We don&apos;t share data with data brokers.</li>
          </ul>
        </Section>

        <Section title="Third parties that process your data">
          <p>
            To operate the service we rely on a few vendors. Each only receives what they need:
          </p>
          <ul>
            <li><strong>Supabase</strong> — authentication and database (US region).</li>
            <li><strong>Stripe</strong> — payment processing (US).</li>
            <li><strong>Fly.io</strong> — backend hosting (US).</li>
            <li><strong>Vercel</strong> — frontend hosting (US, CDN worldwide).</li>
          </ul>
          <p className="mt-3">
            Separately, we pull <em>public</em> biotech data from SEC EDGAR, ClinicalTrials.gov,
            and Finnhub. We do not send them any information about you.
          </p>
        </Section>

        <Section title="How long we keep it">
          <ul>
            <li>Account email + Stripe customer ID: as long as your account exists.</li>
            <li>Watchlist entries: until you delete them or your account.</li>
            <li>API request logs: rotated within 7 days.</li>
          </ul>
        </Section>

        <Section title="Your rights">
          <ul>
            <li>
              <strong>Access / export</strong>: email us and we&apos;ll send you a copy of your
              account data.
            </li>
            <li>
              <strong>Delete</strong>: email us and we&apos;ll delete your account within 14 days.
              Stripe may retain transaction records for tax compliance independent of us.
            </li>
            <li>
              <strong>Correct</strong>: update your profile from the account settings.
            </li>
            <li>
              If you&apos;re in the <strong>EU/UK (GDPR)</strong> or <strong>California (CCPA)</strong>,
              you have additional rights. Reach out and we&apos;ll help.
            </li>
          </ul>
        </Section>

        <Section title="Cookies and local storage">
          <p>
            We use browser localStorage to remember your session (via Supabase) and UI preferences
            like theme and sidebar state. We don&apos;t use cross-site tracking cookies.
          </p>
        </Section>

        <Section title="Children">
          <p>Biotick is not intended for anyone under 18.</p>
        </Section>

        <Section title="Changes to this policy">
          <p>
            If we materially change this policy we&apos;ll update the date at the top and notify
            logged-in users by email.
          </p>
        </Section>

        <Section title="Contact">
          <p>
            <a href="mailto:contact@biotick.io" className="text-accent hover:underline">
              contact@biotick.io
            </a>
          </p>
        </Section>

        <div className="mt-16 pt-8 border-t border-border flex gap-6 text-sm text-muted">
          <Link href="/" className="hover:text-foreground transition">Home</Link>
          <Link href="/terms" className="hover:text-foreground transition">Terms</Link>
        </div>
      </main>
    </div>
  );
}

function Section({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <section className="mt-10">
      <h2 className="text-xl font-semibold tracking-tight">{title}</h2>
      <div className="mt-3 text-[14px] leading-relaxed text-muted space-y-3 [&_ul]:space-y-2 [&_ul]:list-disc [&_ul]:pl-5 [&_strong]:text-foreground [&_strong]:font-semibold">
        {children}
      </div>
    </section>
  );
}
