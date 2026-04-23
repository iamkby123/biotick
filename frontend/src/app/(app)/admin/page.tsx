"use client";

import { useState } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { Shield, Check, X, Loader2, Gift, UserX } from "lucide-react";
import { fetchAPI } from "@/lib/api";
import { supabase } from "@/lib/supabase";
import { usePlan } from "@/hooks/usePlan";
import { cn } from "@/lib/utils";

interface AdminUser {
  id: string;
  email: string;
  plan: "free" | "pro";
  is_admin: boolean;
  comp_granted: boolean;
  stripe_customer_id: string | null;
  created_at: string | null;
}

interface UsersResponse {
  total: number;
  items: AdminUser[];
}

interface AuditItem {
  id: number;
  admin_email: string | null;
  target_email: string | null;
  action: string;
  details: Record<string, unknown> | null;
  created_at: string | null;
}

async function withAuth<T>(
  endpoint: string,
  init?: RequestInit
): Promise<T> {
  const { data: sess } = await supabase.auth.getSession();
  const token = sess.session?.access_token;
  if (!token) throw new Error("Not logged in");
  return fetchAPI<T>(endpoint, {
    ...init,
    headers: { Authorization: `Bearer ${token}`, ...(init?.headers || {}) },
  });
}

export default function AdminPage() {
  const { isAdmin, isLoggedIn } = usePlan();
  const qc = useQueryClient();
  const [email, setEmail] = useState("");
  const [note, setNote] = useState("");
  const [search, setSearch] = useState("");
  const [planFilter, setPlanFilter] = useState<"all" | "free" | "pro">("all");
  const [flash, setFlash] = useState<{ kind: "ok" | "err"; text: string } | null>(null);

  const users = useQuery<UsersResponse>({
    queryKey: ["admin-users", search, planFilter],
    queryFn: () => {
      const params = new URLSearchParams();
      if (search) params.set("search", search);
      if (planFilter !== "all") params.set("plan", planFilter);
      params.set("limit", "100");
      return withAuth<UsersResponse>(`/admin/users?${params}`);
    },
    enabled: isAdmin,
  });

  const audit = useQuery<{ items: AuditItem[] }>({
    queryKey: ["admin-audit"],
    queryFn: () => withAuth<{ items: AuditItem[] }>(`/admin/audit?limit=25`),
    enabled: isAdmin,
  });

  const grant = useMutation({
    mutationFn: (args: { email: string; note?: string }) =>
      withAuth<{ ok: boolean; email: string; previous_plan: string; new_plan: string }>(
        "/admin/grant-pro",
        { method: "POST", body: JSON.stringify(args) }
      ),
    onSuccess: (r) => {
      setFlash({ kind: "ok", text: `Granted Pro to ${r.email} (was ${r.previous_plan}).` });
      setEmail("");
      setNote("");
      qc.invalidateQueries({ queryKey: ["admin-users"] });
      qc.invalidateQueries({ queryKey: ["admin-audit"] });
    },
    onError: (e: Error) => setFlash({ kind: "err", text: e.message }),
  });

  const revoke = useMutation({
    mutationFn: (args: { email: string; note?: string }) =>
      withAuth<{ ok: boolean; email: string }>("/admin/revoke-pro", {
        method: "POST",
        body: JSON.stringify(args),
      }),
    onSuccess: (r) => {
      setFlash({ kind: "ok", text: `Revoked Pro from ${r.email}.` });
      qc.invalidateQueries({ queryKey: ["admin-users"] });
      qc.invalidateQueries({ queryKey: ["admin-audit"] });
    },
    onError: (e: Error) => setFlash({ kind: "err", text: e.message }),
  });

  if (!isLoggedIn) {
    return (
      <div className="rounded-lg border border-border p-16 text-center">
        <p className="text-sm">Sign in to view this page.</p>
      </div>
    );
  }
  if (!isAdmin) {
    return (
      <div className="rounded-lg border border-border p-16 text-center">
        <Shield className="w-6 h-6 text-muted mx-auto mb-3" />
        <p className="text-sm">This page is admin-only.</p>
      </div>
    );
  }

  return (
    <div className="space-y-6">
      <div>
        <div className="flex items-center gap-2 text-sm font-medium text-accent">
          <Shield className="w-4 h-4" />
          Admin
        </div>
        <h1 className="text-3xl font-bold tracking-tight mt-1">User Management</h1>
        <p className="text-sm text-muted mt-1">
          Grant any user Pro access (comped, no Stripe charge) or revoke a previously-comped Pro sub.
          Paying Stripe subscribers cannot be revoked here — cancel in Stripe instead.
        </p>
      </div>

      {flash && (
        <div
          className={cn(
            "rounded-md px-4 py-3 text-sm flex items-center gap-2",
            flash.kind === "ok"
              ? "bg-positive/10 text-positive border border-positive/30"
              : "bg-negative/10 text-negative border border-negative/30"
          )}
        >
          {flash.kind === "ok" ? <Check className="w-4 h-4" /> : <X className="w-4 h-4" />}
          {flash.text}
          <button
            onClick={() => setFlash(null)}
            className="ml-auto text-xs text-muted hover:text-foreground"
          >
            dismiss
          </button>
        </div>
      )}

      {/* Grant / revoke card */}
      <div className="rounded-lg border border-border p-5 space-y-3">
        <h2 className="text-sm font-semibold uppercase tracking-widest text-muted">
          Grant / Revoke Pro
        </h2>
        <div className="flex flex-col sm:flex-row gap-2">
          <input
            type="email"
            value={email}
            onChange={(e) => setEmail(e.target.value)}
            placeholder="user@example.com"
            className="flex-1 px-3 py-2 rounded-md bg-surface border border-border text-sm focus:border-accent focus:outline-none"
          />
          <input
            type="text"
            value={note}
            onChange={(e) => setNote(e.target.value)}
            placeholder="note (optional — stored in audit log)"
            className="flex-1 px-3 py-2 rounded-md bg-surface border border-border text-sm focus:border-accent focus:outline-none"
          />
          <button
            disabled={!email || grant.isPending}
            onClick={() => grant.mutate({ email, note: note || undefined })}
            className="inline-flex items-center gap-1.5 px-4 py-2 rounded-md bg-accent text-black text-sm font-semibold disabled:opacity-50 hover:bg-accent/90"
          >
            {grant.isPending ? (
              <Loader2 className="w-4 h-4 animate-spin" />
            ) : (
              <Gift className="w-4 h-4" />
            )}
            Grant Pro
          </button>
          <button
            disabled={!email || revoke.isPending}
            onClick={() => revoke.mutate({ email, note: note || undefined })}
            className="inline-flex items-center gap-1.5 px-4 py-2 rounded-md border border-border text-sm font-medium disabled:opacity-50 hover:border-negative/50 hover:text-negative"
          >
            {revoke.isPending ? (
              <Loader2 className="w-4 h-4 animate-spin" />
            ) : (
              <UserX className="w-4 h-4" />
            )}
            Revoke
          </button>
        </div>
      </div>

      {/* User list */}
      <div className="rounded-lg border border-border overflow-hidden">
        <div className="p-4 border-b border-border flex flex-col sm:flex-row gap-2 items-start sm:items-center">
          <h2 className="text-sm font-semibold uppercase tracking-widest text-muted sm:mr-auto">
            Users {users.data && <span className="text-muted">({users.data.total})</span>}
          </h2>
          <input
            type="text"
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            placeholder="Search by email…"
            className="px-3 py-1.5 rounded-md bg-surface border border-border text-[12px] focus:border-accent focus:outline-none"
          />
          <div className="flex items-center gap-1">
            {(["all", "free", "pro"] as const).map((f) => (
              <button
                key={f}
                onClick={() => setPlanFilter(f)}
                className={cn(
                  "px-2.5 py-1 rounded text-[11px] font-medium transition-colors",
                  planFilter === f
                    ? "bg-accent/15 text-accent"
                    : "text-muted hover:text-foreground hover:bg-surface-hover"
                )}
              >
                {f}
              </button>
            ))}
          </div>
        </div>

        {users.isLoading ? (
          <div className="p-16 flex justify-center">
            <Loader2 className="w-5 h-5 animate-spin text-accent" />
          </div>
        ) : (
          <table className="w-full text-sm">
            <thead>
              <tr className="bg-surface/50 border-b border-border">
                <th className="text-left px-4 py-2 text-[10px] font-semibold uppercase tracking-widest text-muted">Email</th>
                <th className="text-left px-4 py-2 text-[10px] font-semibold uppercase tracking-widest text-muted">Plan</th>
                <th className="text-left px-4 py-2 text-[10px] font-semibold uppercase tracking-widest text-muted">Source</th>
                <th className="text-left px-4 py-2 text-[10px] font-semibold uppercase tracking-widest text-muted">Created</th>
                <th className="text-right px-4 py-2 text-[10px] font-semibold uppercase tracking-widest text-muted">Action</th>
              </tr>
            </thead>
            <tbody>
              {(users.data?.items ?? []).map((u) => (
                <tr key={u.id} className="border-b border-border last:border-b-0 hover:bg-surface/60">
                  <td className="px-4 py-2.5 text-[13px]">
                    {u.email}
                    {u.is_admin && (
                      <span className="ml-2 text-[9px] bg-accent/15 text-accent px-1.5 py-0.5 rounded uppercase tracking-wider">
                        admin
                      </span>
                    )}
                  </td>
                  <td className="px-4 py-2.5">
                    <span
                      className={cn(
                        "text-[10px] font-semibold px-2 py-0.5 rounded uppercase tracking-wider",
                        u.plan === "pro"
                          ? "bg-positive/10 text-positive"
                          : "bg-surface/80 text-muted"
                      )}
                    >
                      {u.plan}
                    </span>
                  </td>
                  <td className="px-4 py-2.5 text-[11px] text-muted">
                    {u.plan === "pro"
                      ? u.comp_granted
                        ? "comped"
                        : u.stripe_customer_id
                          ? "stripe"
                          : "—"
                      : "—"}
                  </td>
                  <td className="px-4 py-2.5 text-[11px] font-mono text-muted">
                    {u.created_at ? u.created_at.slice(0, 10) : "—"}
                  </td>
                  <td className="px-4 py-2.5 text-right">
                    {u.plan === "pro" && u.comp_granted ? (
                      <button
                        onClick={() => revoke.mutate({ email: u.email })}
                        disabled={revoke.isPending}
                        className="text-[11px] text-muted hover:text-negative"
                      >
                        Revoke
                      </button>
                    ) : u.plan !== "pro" ? (
                      <button
                        onClick={() => grant.mutate({ email: u.email })}
                        disabled={grant.isPending}
                        className="text-[11px] text-muted hover:text-accent"
                      >
                        Grant Pro
                      </button>
                    ) : (
                      <span className="text-[10px] text-muted">—</span>
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>

      {/* Audit log */}
      <div className="rounded-lg border border-border overflow-hidden">
        <div className="p-4 border-b border-border">
          <h2 className="text-sm font-semibold uppercase tracking-widest text-muted">
            Recent admin actions
          </h2>
        </div>
        {audit.isLoading ? (
          <div className="p-8 flex justify-center">
            <Loader2 className="w-5 h-5 animate-spin text-accent" />
          </div>
        ) : (
          <table className="w-full text-sm">
            <thead>
              <tr className="bg-surface/50 border-b border-border">
                <th className="text-left px-4 py-2 text-[10px] font-semibold uppercase tracking-widest text-muted">When</th>
                <th className="text-left px-4 py-2 text-[10px] font-semibold uppercase tracking-widest text-muted">Admin</th>
                <th className="text-left px-4 py-2 text-[10px] font-semibold uppercase tracking-widest text-muted">Action</th>
                <th className="text-left px-4 py-2 text-[10px] font-semibold uppercase tracking-widest text-muted">Target</th>
                <th className="text-left px-4 py-2 text-[10px] font-semibold uppercase tracking-widest text-muted">Note</th>
              </tr>
            </thead>
            <tbody>
              {(audit.data?.items ?? []).map((a) => (
                <tr key={a.id} className="border-b border-border last:border-b-0">
                  <td className="px-4 py-2 text-[11px] font-mono text-muted">
                    {a.created_at ? new Date(a.created_at).toLocaleString() : "—"}
                  </td>
                  <td className="px-4 py-2 text-[12px]">{a.admin_email}</td>
                  <td className="px-4 py-2">
                    <span className="text-[10px] font-semibold px-2 py-0.5 rounded uppercase tracking-wider bg-accent/10 text-accent">
                      {a.action}
                    </span>
                  </td>
                  <td className="px-4 py-2 text-[12px]">{a.target_email || "—"}</td>
                  <td className="px-4 py-2 text-[11px] text-muted">
                    {(a.details && (a.details.note as string)) || ""}
                  </td>
                </tr>
              ))}
              {(audit.data?.items ?? []).length === 0 && (
                <tr>
                  <td colSpan={5} className="px-4 py-8 text-center text-[12px] text-muted">
                    No admin actions yet.
                  </td>
                </tr>
              )}
            </tbody>
          </table>
        )}
      </div>
    </div>
  );
}
