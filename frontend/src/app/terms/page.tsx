import type { Metadata } from "next";
import Link from "next/link";
import { Activity, AlertTriangle } from "lucide-react";

export const metadata: Metadata = {
  title: "Terms of Service · Biotick",
  description: "Terms governing the use of Biotick.",
};

export default function TermsPage() {
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

      <main className="max-w-3xl mx-auto px-6 py-16">
        <h1 className="text-3xl md:text-4xl font-bold tracking-tight">Terms of Service</h1>
        <p className="text-sm text-muted mt-2">Last updated: April 19, 2026</p>

        <p className="mt-8 text-[15px] leading-relaxed text-muted">
          These terms govern your use of Biotick (&ldquo;we&rdquo;, &ldquo;us&rdquo;, &ldquo;the
          Service&rdquo;) at{" "}
          <a href="https://biotick.io" className="text-accent hover:underline">biotick.io</a>.
          By creating an account or using the Service you agree to these terms.
        </p>

        {/* Big scary disclaimer up top — this is the most important thing on the page */}
        <div className="mt-8 rounded-lg border border-warning/30 bg-warning/5 p-5">
          <div className="flex items-start gap-3">
            <AlertTriangle className="w-5 h-5 text-warning shrink-0 mt-0.5" />
            <div>
              <h2 className="text-sm font-bold uppercase tracking-widest text-warning">
                Not Financial Advice
              </h2>
              <p className="mt-2 text-[14px] leading-relaxed text-foreground">
                Biotick is a <strong>research tool</strong>. Everything shown on the Service —
                catalysts, predictions, trial factors, scores, options flow, insider trades — is
                for <strong>informational purposes only</strong>. We are not a registered
                investment advisor, broker, or dealer.
              </p>
              <p className="mt-3 text-[14px] leading-relaxed text-foreground">
                <strong>Nothing on Biotick is a recommendation to buy, sell, or hold any
                security.</strong> Past performance does not predict future results. Biotech
                investing is volatile and you can lose your entire investment. Always consult a
                licensed financial advisor before making investment decisions.
              </p>
            </div>
          </div>
        </div>

        <Section title="Your account">
          <ul>
            <li>You must be 18 or older to use Biotick.</li>
            <li>You&apos;re responsible for keeping your login credentials secure.</li>
            <li>One account per person.</li>
          </ul>
        </Section>

        <Section title="Subscription">
          <ul>
            <li>Pro is <strong>$19.99 USD / month</strong>, billed via Stripe.</li>
            <li>Auto-renews monthly until you cancel.</li>
            <li>
              Cancel anytime from the Stripe customer portal (link in your receipts). Cancellation
              takes effect at the end of the current billing period.
            </li>
          </ul>
        </Section>

        <Section title="Refunds">
          <ul>
            <li>
              Refunds available within <strong>7 days</strong> of purchase if you have not used any
              Pro feature. Email{" "}
              <a href="mailto:contact@biotick.io" className="text-accent hover:underline">
                contact@biotick.io
              </a>
              .
            </li>
            <li>After 7 days, or if you have used Pro features, no refunds.</li>
            <li>Failed payments: we retry a few times. If they continue to fail we downgrade you to Free.</li>
          </ul>
        </Section>

        <Section title="Acceptable use">
          <p>Don&apos;t:</p>
          <ul>
            <li>Scrape the site or abuse the API.</li>
            <li>Share your account credentials with others.</li>
            <li>Resell, sublicense, or build competing products using our data.</li>
            <li>
              Attempt to reverse-engineer, interfere with the service, or gain unauthorized access
              to other users&apos; accounts.
            </li>
          </ul>
          <p className="mt-3">
            We may rate-limit or suspend accounts that violate this.
          </p>
        </Section>

        <Section title="Data accuracy">
          <p>
            We aggregate data from public sources (SEC EDGAR, ClinicalTrials.gov, Finnhub, and
            others). We try to keep it accurate but provide <strong>no warranty</strong> that it
            is correct, complete, or timely. Verify anything important against the primary source
            before acting on it.
          </p>
        </Section>

        <Section title="Service changes">
          <p>
            We may add, remove, or change features at any time. If we make material changes that
            affect paid features we&apos;ll notify Pro subscribers by email.
          </p>
        </Section>

        <Section title="Limitation of liability">
          <p>
            Biotick is provided &ldquo;as is.&rdquo; To the maximum extent permitted by law, our
            total liability for any claim is limited to the amount you have paid us in the
            preceding 12 months.
          </p>
          <p className="mt-3">
            We are <strong>not liable</strong> for trading losses, missed opportunities, lost
            profits, or any indirect or consequential damages arising from your use of the Service.
          </p>
        </Section>

        <Section title="Termination">
          <ul>
            <li>You can delete your account at any time (see the Privacy Policy).</li>
            <li>We may terminate accounts that violate these terms.</li>
          </ul>
        </Section>

        <Section title="Governing law">
          <p>
            These terms are governed by the laws of the State of California, USA, without regard
            to its conflict-of-laws rules.
          </p>
        </Section>

        <Section title="Changes to these terms">
          <p>
            If we change these terms materially we&apos;ll update the date at the top and notify
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
          <Link href="/privacy" className="hover:text-foreground transition">Privacy</Link>
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
