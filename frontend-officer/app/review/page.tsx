"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { getReviewQueue, type ReviewQueueItem } from "@/lib/api";

function InfoTooltip({ text }: { text: string }) {
  return (
    <span className="relative group ml-1.5" style={{ display: "inline-block", verticalAlign: "middle" }}>
      <span className="inline-flex items-center justify-center rounded-full border cursor-help font-bold leading-none"
        style={{ width: "13px", height: "13px", fontSize: "9px", borderColor: "var(--text-subtle)", color: "var(--text-subtle)" }}>
        i
      </span>
      <span className="absolute bottom-full left-0 mb-2 w-60 rounded-lg px-3 py-2 text-xs leading-relaxed pointer-events-none opacity-0 group-hover:opacity-100 transition-opacity z-50 normal-case font-normal"
        style={{ background: "#1e293b", color: "#f1f5f9", whiteSpace: "normal" }}>
        {text}
        <span className="absolute top-full border-4 border-transparent"
          style={{ borderTopColor: "#1e293b", left: "8px" }} />
      </span>
    </span>
  );
}

const RISK_BADGE = (count: number) => {
  if (count === 0) return "bg-green-100 text-green-700 dark:bg-green-900/30 dark:text-green-400";
  if (count <= 2) return "bg-yellow-100 text-yellow-700 dark:bg-yellow-900/30 dark:text-yellow-400";
  return "bg-red-100 text-red-700 dark:bg-red-900/30 dark:text-red-400";
};

export default function ReviewQueuePage() {
  const [items, setItems] = useState<ReviewQueueItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [typeFilter, setTypeFilter] = useState<string | null>(null);

  const load = () => {
    setLoading(true);
    getReviewQueue()
      .then((r) => setItems(r.items))
      .catch((err) => setError(err.message))
      .finally(() => setLoading(false));
  };

  useEffect(() => { load(); }, []);

  const claimTypes = Array.from(new Set(items.map((i) => i.claim_type ?? "unknown"))).sort();
  const filtered = typeFilter ? items.filter((i) => (i.claim_type ?? "unknown") === typeFilter) : items;

  return (
    <div className="p-8 space-y-5">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold" style={{ color: "var(--text)" }}>Review Queue</h1>
          <p className="text-sm mt-1" style={{ color: "var(--text-muted)" }}>
            Claims flagged by the AI for manual adjudication
          </p>
        </div>
        <button
          onClick={load}
          className="text-sm rounded-lg px-3 py-1.5 border transition-colors hover:opacity-80"
          style={{ color: "var(--text-muted)", borderColor: "var(--border)" }}
        >
          ↻ Refresh
        </button>
      </div>

      {loading && <p className="text-sm animate-pulse" style={{ color: "var(--text-subtle)" }}>Loading queue...</p>}
      {error && <p className="text-sm text-red-500">{error}</p>}

      {!loading && items.length > 0 && (
        <div className="flex items-center gap-2 flex-wrap">
          <span className="text-xs font-medium" style={{ color: "var(--text-subtle)" }}>Type:</span>
          <button
            onClick={() => setTypeFilter(null)}
            className="px-3 py-1 rounded-full text-xs font-medium border transition-colors"
            style={{
              background: typeFilter === null ? "var(--accent)" : "transparent",
              borderColor: typeFilter === null ? "var(--accent)" : "var(--border)",
              color: typeFilter === null ? "#fff" : "var(--text-muted)",
            }}
          >
            All <span className="ml-1 opacity-70">{items.length}</span>
          </button>
          {claimTypes.map((type) => {
            const count = items.filter((i) => (i.claim_type ?? "unknown") === type).length;
            const active = typeFilter === type;
            return (
              <button
                key={type}
                onClick={() => setTypeFilter(active ? null : type)}
                className="px-3 py-1 rounded-full text-xs font-medium border transition-colors capitalize"
                style={{
                  background: active ? "var(--accent)" : "transparent",
                  borderColor: active ? "var(--accent)" : "var(--border)",
                  color: active ? "#fff" : "var(--text-muted)",
                }}
              >
                {type} <span className="ml-1 opacity-70">{count}</span>
              </button>
            );
          })}
        </div>
      )}

      {!loading && items.length === 0 && (
        <div className="rounded-2xl border p-12 text-center shadow-sm"
          style={{ background: "var(--bg-card)", borderColor: "var(--border)", color: "var(--text-subtle)" }}>
          <p className="font-medium" style={{ color: "var(--text-muted)" }}>Queue is empty</p>
          <p className="text-sm mt-1">All claims have been reviewed or auto-adjudicated.</p>
        </div>
      )}

      {!loading && filtered.length === 0 && items.length > 0 && (
        <p className="text-sm" style={{ color: "var(--text-subtle)" }}>
          No <span className="capitalize">{typeFilter}</span> claims in the queue.
        </p>
      )}

      {filtered.length > 0 && (
        <div className="rounded-2xl border shadow-sm"
          style={{ background: "var(--bg-card)", borderColor: "var(--border)" }}>
          <table className="w-full text-sm">
            <thead className="border-b" style={{ background: "var(--bg-subtle)", borderColor: "var(--border)" }}>
              <tr>
                <th className="text-left px-5 py-3 font-medium" style={{ color: "var(--text-muted)" }}>Claim ID</th>
                <th className="text-left px-5 py-3 font-medium" style={{ color: "var(--text-muted)" }}>Type</th>
                <th className="text-left px-5 py-3 font-medium" style={{ color: "var(--text-muted)" }}>
                  Type Confidence
                  <InfoTooltip text="How confident the AI was in classifying the claim type (Auto / Property / Health). Not related to fraud risk or the outcome of the claim." />
                </th>
                <th className="text-left px-5 py-3 font-medium" style={{ color: "var(--text-muted)" }}>Risk Signals</th>
                <th className="text-left px-5 py-3 font-medium" style={{ color: "var(--text-muted)" }}>Received</th>
                <th className="px-5 py-3" />
              </tr>
            </thead>
            <tbody>
              {filtered.map((item, idx) => (
                <tr key={item.claim_id}
                  className="transition-colors hover:opacity-90"
                  style={{
                    borderTop: idx > 0 ? `1px solid var(--border)` : undefined,
                    background: "transparent",
                  }}>
                  <td className="px-5 py-4 font-mono font-semibold" style={{ color: "var(--text)" }}>{item.claim_id}</td>
                  <td className="px-5 py-4 capitalize" style={{ color: "var(--text-muted)" }}>{item.claim_type ?? "Unknown"}</td>
                  <td className="px-5 py-4" style={{ color: "var(--text-muted)" }}>
                    {item.routing_confidence != null ? `${(item.routing_confidence * 100).toFixed(0)}%` : "—"}
                  </td>
                  <td className="px-5 py-4">
                    <span className={`px-2.5 py-1 rounded-full text-xs font-medium ${RISK_BADGE(item.fraud_signal_count)}`}>
                      {item.fraud_signal_count} signal{item.fraud_signal_count !== 1 ? "s" : ""}
                    </span>
                  </td>
                  <td className="px-5 py-4 text-xs" style={{ color: "var(--text-subtle)" }}>
                    {new Date(item.created_at).toLocaleString()}
                  </td>
                  <td className="px-5 py-4">
                    <Link href={`/review/${item.claim_id}`} className="text-blue-500 hover:underline font-medium">
                      Review →
                    </Link>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}
