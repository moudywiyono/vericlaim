"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { getHistory, type HistoryItem } from "@/lib/api";

const STATE_STYLE: Record<string, { label: string; color: string; bg: string }> = {
  approved: { label: "Approved",     color: "#16a34a", bg: "rgba(34,197,94,0.08)"  },
  denied:   { label: "Denied",       color: "#dc2626", bg: "rgba(239,68,68,0.08)"  },
  complete: { label: "AI Approved",  color: "#2563eb", bg: "rgba(37,99,235,0.08)"  },
};

export default function HistoryPage() {
  const [items, setItems] = useState<HistoryItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [search, setSearch] = useState("");

  const load = () => {
    setLoading(true);
    getHistory()
      .then((r) => setItems(r.items))
      .catch((e: Error) => setError(e.message))
      .finally(() => setLoading(false));
  };

  useEffect(() => { load(); }, []);

  const filtered = items.filter((item) => {
    const q = search.toLowerCase();
    return (
      item.claim_id.toLowerCase().includes(q) ||
      (item.claim_type ?? "").toLowerCase().includes(q) ||
      item.state.toLowerCase().includes(q)
    );
  });

  return (
    <div className="p-8 space-y-5">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold" style={{ color: "var(--text)" }}>Claims History</h1>
          <p className="text-sm mt-1" style={{ color: "var(--text-muted)" }}>
            All decided claims — approved, denied, and AI auto-adjudicated
          </p>
        </div>
        <button
          onClick={load}
          className="text-sm rounded-lg px-3 py-1.5 border transition-colors hover:opacity-80"
          style={{ color: "var(--text-muted)", borderColor: "var(--border)" }}>
          ↻ Refresh
        </button>
      </div>

      <input
        type="text"
        placeholder="Search by claim ID or type..."
        value={search}
        onChange={(e) => setSearch(e.target.value)}
        className="w-full rounded-xl px-4 py-2.5 text-sm focus:outline-none focus:ring-2 focus:ring-blue-400"
        style={{ background: "var(--bg-card)", border: "1px solid var(--border)", color: "var(--text)" }}
      />

      {loading && <p className="text-sm animate-pulse" style={{ color: "var(--text-subtle)" }}>Loading history...</p>}
      {error && <p className="text-sm text-red-500">{error}</p>}

      {!loading && filtered.length === 0 && (
        <div className="rounded-2xl border p-12 text-center shadow-sm"
          style={{ background: "var(--bg-card)", borderColor: "var(--border)", color: "var(--text-subtle)" }}>
          <p className="font-medium" style={{ color: "var(--text-muted)" }}>No decided claims yet</p>
          <p className="text-sm mt-1">Claims will appear here once approved or denied.</p>
        </div>
      )}

      {filtered.length > 0 && (
        <div className="rounded-2xl border shadow-sm overflow-hidden"
          style={{ background: "var(--bg-card)", borderColor: "var(--border)" }}>
          <table className="w-full text-sm">
            <thead className="border-b" style={{ background: "var(--bg-subtle)", borderColor: "var(--border)" }}>
              <tr>
                <th className="text-left px-5 py-3 font-medium" style={{ color: "var(--text-muted)" }}>Claim ID</th>
                <th className="text-left px-5 py-3 font-medium" style={{ color: "var(--text-muted)" }}>Type</th>
                <th className="text-left px-5 py-3 font-medium" style={{ color: "var(--text-muted)" }}>Outcome</th>
                <th className="text-left px-5 py-3 font-medium" style={{ color: "var(--text-muted)" }}>Risk Signals</th>
                <th className="text-left px-5 py-3 font-medium" style={{ color: "var(--text-muted)" }}>Officer Note</th>
                <th className="text-left px-5 py-3 font-medium" style={{ color: "var(--text-muted)" }}>Decided</th>
                <th className="px-5 py-3" />
              </tr>
            </thead>
            <tbody>
              {filtered.map((item, idx) => {
                const style = STATE_STYLE[item.state] ?? { label: item.state, color: "var(--text-muted)", bg: "transparent" };
                return (
                  <tr key={item.claim_id}
                    style={{ borderTop: idx > 0 ? "1px solid var(--border)" : undefined }}>
                    <td className="px-5 py-4 font-mono font-semibold" style={{ color: "var(--text)" }}>
                      {item.claim_id}
                    </td>
                    <td className="px-5 py-4 capitalize" style={{ color: "var(--text-muted)" }}>
                      {item.claim_type ?? "Unknown"}
                    </td>
                    <td className="px-5 py-4">
                      <span className="px-2.5 py-1 rounded-full text-xs font-semibold"
                        style={{ color: style.color, background: style.bg }}>
                        {style.label}
                      </span>
                    </td>
                    <td className="px-5 py-4" style={{ color: item.fraud_signal_count > 0 ? "#ef4444" : "var(--text-muted)" }}>
                      {item.fraud_signal_count > 0 ? `${item.fraud_signal_count} signals` : "—"}
                    </td>
                    <td className="px-5 py-4 max-w-xs">
                      <span className="text-xs leading-relaxed line-clamp-2" style={{ color: "var(--text-muted)" }}>
                        {item.officer_note || <span style={{ color: "var(--text-subtle)" }}>—</span>}
                      </span>
                    </td>
                    <td className="px-5 py-4 text-xs whitespace-nowrap" style={{ color: "var(--text-subtle)" }}>
                      {new Date(item.decided_at).toLocaleString()}
                    </td>
                    <td className="px-5 py-4">
                      <Link href={`/review/${item.claim_id}?from=history`} className="text-blue-500 hover:underline text-xs font-medium">
                        View →
                      </Link>
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}
