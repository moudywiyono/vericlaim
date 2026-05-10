"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { getReviewQueue } from "@/lib/api";

export default function OfficerOverview() {
  const [queueCount, setQueueCount] = useState<number | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    getReviewQueue()
      .then((r) => setQueueCount(r.total))
      .catch((e: Error) => { setError(e.message); setQueueCount(0); });
  }, []);

  return (
    <div className="p-8 space-y-6">
      <div>
        <h1 className="text-2xl font-bold" style={{ color: "var(--text)" }}>Overview</h1>
        <p className="text-sm mt-1" style={{ color: "var(--text-muted)" }}>Claims requiring your attention today</p>
      </div>

      {error && (
        <div className="rounded-xl border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-600">
          Could not reach backend: {error}
        </div>
      )}

      <div className="grid grid-cols-3 gap-5">
        <div className="rounded-2xl border p-5 shadow-sm" style={{ background: "var(--bg-card)", borderColor: "var(--border)" }}>
          <p className="text-sm font-medium" style={{ color: "var(--text-muted)" }}>Awaiting Your Decision</p>
          <p className="text-4xl font-bold mt-1 text-amber-500">
            {queueCount === null ? "—" : queueCount}
          </p>
          <p className="text-xs mt-2" style={{ color: "var(--text-subtle)" }}>
            Claims the AI could not auto-adjudicate
          </p>
          <Link href="/review" className="text-xs text-blue-500 hover:underline mt-1 inline-block">View queue →</Link>
        </div>
        <div className="rounded-2xl border p-5 shadow-sm" style={{ background: "var(--bg-card)", borderColor: "var(--border)" }}>
          <p className="text-sm font-medium" style={{ color: "var(--text-muted)" }}>AI Auto-Decided</p>
          <p className="text-4xl font-bold mt-1 text-green-500">—</p>
          <p className="text-xs mt-2" style={{ color: "var(--text-subtle)" }}>
            Claims approved or denied by AI without escalation
          </p>
        </div>
        <div className="rounded-2xl border p-5 shadow-sm" style={{ background: "var(--bg-card)", borderColor: "var(--border)" }}>
          <p className="text-sm font-medium" style={{ color: "var(--text-muted)" }}>High Fraud Risk</p>
          <p className="text-4xl font-bold mt-1 text-red-500">—</p>
          <p className="text-xs mt-2" style={{ color: "var(--text-subtle)" }}>
            Claims with 3+ fraud signals — may need SIU referral
          </p>
        </div>
      </div>

      {queueCount !== null && queueCount > 0 && (
        <div className="border rounded-2xl p-5 flex items-center justify-between"
          style={{ background: "rgba(245,158,11,0.06)", borderColor: "#f59e0b" }}>
          <div>
            <p className="font-semibold text-amber-500">
              {queueCount} claim{queueCount !== 1 ? "s" : ""} waiting for review
            </p>
            <p className="text-sm mt-0.5" style={{ color: "var(--text-muted)" }}>
              These claims could not be auto-adjudicated and need your decision.
            </p>
          </div>
          <Link href="/review"
            className="bg-amber-500 hover:bg-amber-600 text-white font-medium px-5 py-2.5 rounded-xl text-sm transition-colors shrink-0 ml-4">
            Review Now →
          </Link>
        </div>
      )}

      {queueCount === 0 && (
        <div className="border rounded-2xl p-8 text-center"
          style={{ background: "rgba(34,197,94,0.06)", borderColor: "#4ade80" }}>
          <p className="text-3xl mb-2">✅</p>
          <p className="font-semibold text-green-500">All caught up!</p>
          <p className="text-sm mt-1" style={{ color: "var(--text-muted)" }}>No claims are waiting for review.</p>
        </div>
      )}
    </div>
  );
}
