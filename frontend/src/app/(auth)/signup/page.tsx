"use client";

import { useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { Activity, Loader2 } from "lucide-react";
import { supabase } from "@/lib/supabase";

export default function SignupPage() {
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [success, setSuccess] = useState(false);
  const router = useRouter();

  const handleGoogleSignup = async () => {
    setLoading(true);
    setError(null);
    try {
      const { error } = await supabase.auth.signInWithOAuth({
        provider: "google",
        options: {
          redirectTo: `${window.location.origin}/dashboard`,
        },
      });
      if (error) setError(error.message);
    } catch (e) {
      setError("Failed to sign up");
    } finally {
      setLoading(false);
    }
  };

  const handleEmailSignup = async (e: React.FormEvent<HTMLFormElement>) => {
    e.preventDefault();
    setLoading(true);
    setError(null);

    const formData = new FormData(e.currentTarget);
    const email = formData.get("email") as string;
    const password = formData.get("password") as string;
    const name = formData.get("name") as string;

    const { error } = await supabase.auth.signUp({
      email,
      password,
      options: {
        data: { full_name: name },
      },
    });

    if (error) {
      setError(error.message);
      setLoading(false);
    } else {
      setSuccess(true);
    }
  };

  if (success) {
    return (
      <div className="min-h-screen bg-background flex items-center justify-center px-4">
        <div className="w-full max-w-sm text-center">
          <div className="w-12 h-12 rounded-xl bg-accent/10 flex items-center justify-center mx-auto mb-4">
            <Activity className="w-6 h-6 text-accent" />
          </div>
          <h2 className="text-xl font-bold">Check your email</h2>
          <p className="text-sm text-muted mt-2">
            We sent a confirmation link to your email. Click it to activate your account.
          </p>
          <Link href="/login" className="text-accent hover:underline text-sm mt-4 inline-block">
            Back to sign in
          </Link>
        </div>
      </div>
    );
  }

  return (
    <div className="min-h-screen bg-background flex items-center justify-center px-4">
      <div className="w-full max-w-sm">
        {/* Logo */}
        <div className="text-center mb-8">
          <Link href="/" className="inline-flex items-center gap-2.5">
            <div className="w-8 h-8 rounded-lg bg-accent flex items-center justify-center">
              <Activity className="w-5 h-5 text-black" />
            </div>
            <span className="font-bold text-xl tracking-tight">Biotick</span>
          </Link>
          <p className="text-sm text-muted mt-2">Create your free account</p>
        </div>

        {/* Google Sign Up */}
        <button
          onClick={handleGoogleSignup}
          disabled={loading}
          className="w-full flex items-center justify-center gap-3 px-4 py-3 rounded-lg border border-border bg-surface hover:bg-surface-hover transition-colors text-sm font-medium disabled:opacity-50"
        >
          <svg className="w-5 h-5" viewBox="0 0 24 24">
            <path fill="#4285F4" d="M22.56 12.25c0-.78-.07-1.53-.2-2.25H12v4.26h5.92a5.06 5.06 0 0 1-2.2 3.32v2.77h3.57c2.08-1.92 3.28-4.74 3.28-8.1z"/>
            <path fill="#34A853" d="M12 23c2.97 0 5.46-.98 7.28-2.66l-3.57-2.77c-.98.66-2.23 1.06-3.71 1.06-2.86 0-5.29-1.93-6.16-4.53H2.18v2.84C3.99 20.53 7.7 23 12 23z"/>
            <path fill="#FBBC05" d="M5.84 14.09c-.22-.66-.35-1.36-.35-2.09s.13-1.43.35-2.09V7.07H2.18C1.43 8.55 1 10.22 1 12s.43 3.45 1.18 4.93l2.85-2.22.81-.62z"/>
            <path fill="#EA4335" d="M12 5.38c1.62 0 3.06.56 4.21 1.64l3.15-3.15C17.45 2.09 14.97 1 12 1 7.7 1 3.99 3.47 2.18 7.07l3.66 2.84c.87-2.6 3.3-4.53 6.16-4.53z"/>
          </svg>
          Continue with Google
        </button>

        <div className="flex items-center gap-3 my-6">
          <div className="flex-1 h-px bg-border" />
          <span className="text-xs text-muted">or</span>
          <div className="flex-1 h-px bg-border" />
        </div>

        {/* Email Sign Up */}
        <form onSubmit={handleEmailSignup} className="space-y-3">
          <input
            name="name"
            type="text"
            placeholder="Full name"
            required
            className="w-full px-4 py-3 rounded-lg bg-surface border border-border text-sm placeholder:text-muted/50 focus:outline-none focus:ring-1 focus:ring-accent/40"
          />
          <input
            name="email"
            type="email"
            placeholder="Email"
            required
            className="w-full px-4 py-3 rounded-lg bg-surface border border-border text-sm placeholder:text-muted/50 focus:outline-none focus:ring-1 focus:ring-accent/40"
          />
          <input
            name="password"
            type="password"
            placeholder="Password (min 6 characters)"
            minLength={6}
            required
            className="w-full px-4 py-3 rounded-lg bg-surface border border-border text-sm placeholder:text-muted/50 focus:outline-none focus:ring-1 focus:ring-accent/40"
          />
          <button
            type="submit"
            disabled={loading}
            className="w-full py-3 rounded-lg bg-accent text-black font-semibold text-sm hover:bg-accent-hover transition-colors disabled:opacity-50 flex items-center justify-center gap-2"
          >
            {loading ? <Loader2 className="w-4 h-4 animate-spin" /> : null}
            Create Account
          </button>
        </form>

        {error && (
          <p className="text-sm text-negative mt-3 text-center">{error}</p>
        )}

        <p className="text-xs text-muted text-center mt-6">
          Already have an account?{" "}
          <Link href="/login" className="text-accent hover:underline">Sign in</Link>
        </p>
      </div>
    </div>
  );
}
