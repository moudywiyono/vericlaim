"use client";

import { useEffect, useState } from "react";
import { useParams } from "next/navigation";
import Link from "next/link";
import { getClaimStatus, getClaimResult, type ClaimStatusResponse, type ClaimResultResponse } from "@/lib/api";

function CopyButton({ text }: { text: string }) {
  const [copied, setCopied] = useState(false);
  const handleCopy = async () => {
    try {
      await navigator.clipboard.writeText(text);
    } catch {
      const ta = document.createElement("textarea");
      ta.value = text;
      document.body.appendChild(ta);
      ta.select();
      document.execCommand("copy");
      document.body.removeChild(ta);
    }
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  };
  return (
    <button
      onClick={handleCopy}
      className="text-xs font-medium px-3 py-1.5 rounded-lg border transition-all shrink-0"
      style={{
        borderColor: copied ? "#2563eb" : "var(--border)",
        color: copied ? "#2563eb" : "var(--text-muted)",
        background: copied ? "#eff6ff" : "transparent",
      }}>
      {copied ? "Copied!" : "Copy ID"}
    </button>
  );
}

const STEPS = ["Routing", "Evidence", "Reasoning", "Adjudicating", "Drafting"];
const STATE_TO_STEP: Record<string, number> = {
  received: -1, routing: 0, evidence_gathering: 1, reasoning: 2,
  adjudicating: 3, drafting: 4, complete: 5, human_review: 5, failed: 5,
};

function StatusStepper({ state }: { state: string }) {
  const current = STATE_TO_STEP[state] ?? -1;
  const done = ["complete", "human_review", "failed"].includes(state);
  return (
    <div className="flex items-center w-full">
      {STEPS.map((label, i) => {
        const completed = i < current || done;
        const active = i === current && !done;
        const lineCompleted = i < current || done;
        return (
          <div key={label} className={`flex items-center ${i < STEPS.length - 1 ? "flex-1" : ""}`}>
            <div className="flex flex-col items-center">
              <div className={`w-9 h-9 rounded-full flex items-center justify-center text-sm font-bold transition-all
                ${completed ? "bg-blue-600 text-white" : active ? "border-2 border-blue-500 text-blue-500" : "text-[var(--text-subtle)]"}`}
                style={!completed && !active ? { background: "var(--bg-subtle)" } : {}}>
                {completed ? "✓" : i + 1}
              </div>
              <span className={`text-xs mt-1.5 font-medium whitespace-nowrap
                ${completed ? "text-blue-500" : active ? "text-blue-400" : ""}`}
                style={!completed && !active ? { color: "var(--text-subtle)" } : {}}>
                {label}
              </span>
            </div>
            {i < STEPS.length - 1 && (
              <div className={`flex-1 h-0.5 mx-1 mb-5`}
                style={{ background: lineCompleted ? "#3b82f6" : "var(--border)" }} />
            )}
          </div>
        );
      })}
    </div>
  );
}

const OUTCOME: Record<string, { borderColor: string; bg: string; title: string; body: string; showCost?: boolean }> = {
  complete: {
    borderColor: "#86efac", bg: "rgba(34,197,94,0.06)",
    title: "Claim Approved",
    body: "Your claim has been approved. Payment will be processed within 5–7 business days.",
    showCost: true,
  },
  approved: {
    borderColor: "#86efac", bg: "rgba(34,197,94,0.06)",
    title: "Claim Approved",
    body: "Your claim has been reviewed and approved by our team. Payment will be processed within 5–7 business days.",
    showCost: true,
  },
  denied: {
    borderColor: "#fca5a5", bg: "rgba(239,68,68,0.06)",
    title: "Claim Denied",
    body: "After review, we are unable to approve this claim. Our team will send you a formal decision letter within 2 business days explaining the reasons. If you wish to appeal, please contact our support team.",
  },
  human_review: {
    borderColor: "#fcd34d", bg: "rgba(245,158,11,0.06)",
    title: "In Review with a Specialist",
    body: "Your claim and all submitted documents have been received and fully processed by our system. A claims specialist has been assigned to make the final decision — this is a standard step for claims of this type. There is nothing else you need to submit right now. You will hear from us within 2 business days.",
  },
  failed: {
    borderColor: "#fca5a5", bg: "rgba(239,68,68,0.06)",
    title: "Processing Error",
    body: "Something went wrong while processing your claim. Please resubmit or contact our support team.",
  },
};

function TotalCost({ findings }: { findings: { estimated_cost_usd: number }[] }) {
  const total = findings.reduce((s, f) => s + f.estimated_cost_usd, 0);
  if (total === 0) return null;
  return (
    <div className="rounded-2xl border p-5" style={{ background: "var(--bg-card)", borderColor: "var(--border)" }}>
      <p className="text-sm mb-1" style={{ color: "var(--text-muted)" }}>Estimated damage cost</p>
      <p className="text-3xl font-bold" style={{ color: "var(--text)" }}>
        ${total.toLocaleString("en-US", { minimumFractionDigits: 2 })}
      </p>
      <p className="text-xs mt-1" style={{ color: "var(--text-subtle)" }}>
        Based on {findings.length} damage region{findings.length !== 1 ? "s" : ""} identified in your photos
      </p>
    </div>
  );
}

export default function ClaimStatusPage() {
  const { claim_id } = useParams<{ claim_id: string }>();
  const [status, setStatus] = useState<ClaimStatusResponse | null>(null);
  const [result, setResult] = useState<ClaimResultResponse | null>(null);
  const [error, setError] = useState("");

  useEffect(() => {
    let cancelled = false;
    const poll = async () => {
      try {
        const s = await getClaimStatus(claim_id);
        if (cancelled) return;
        setStatus(s);
        if (s.is_terminal) {
          try { const r = await getClaimResult(claim_id); if (!cancelled) setResult(r); } catch { /* retry */ }
          return;
        }
        setTimeout(poll, 3000);
      } catch (err) {
        if (!cancelled) setError(err instanceof Error ? err.message : "Failed to load status.");
      }
    };
    poll();
    return () => { cancelled = true; };
  }, [claim_id]);

  if (error) return (
    <div className="max-w-2xl mx-auto px-4 py-10">
      <div className="rounded-2xl border border-red-300 p-6 text-red-600" style={{ background: "rgba(239,68,68,0.06)" }}>
        <p className="font-semibold">Could not load claim</p>
        <p className="text-sm mt-1">{error}</p>
      </div>
    </div>
  );

  if (!status) return (
    <div className="max-w-2xl mx-auto px-4 py-10 text-center">
      <p className="animate-pulse" style={{ color: "var(--text-subtle)" }}>Loading your claim status...</p>
    </div>
  );

  const outcome = OUTCOME[status.state];
  const denialReason = (() => {
    if (status.state !== "denied") return undefined;
    if (result?.evidence.officer_note) return result.evidence.officer_note;
    const signals = result?.evidence.fraud_signals ?? [];
    const flags = result?.evidence.consistency_flags ?? [];
    const topSignal = signals.find(s => s.severity === "high") ?? signals[0];
    const topFlag = flags.find(f => f.severity === "critical") ?? flags[0];
    return (topSignal ?? topFlag)?.description ?? undefined;
  })();
  const outcomeBody = outcome
    ? (denialReason
      ? `After review, we are unable to approve this claim. ${denialReason} If you wish to appeal, please contact our support team.`
      : outcome.body)
    : null;

  return (
    <div className="max-w-2xl mx-auto px-4 py-10 space-y-6">
      <div className="flex items-start justify-between">
        <div>
          <h1 className="text-2xl font-bold" style={{ color: "var(--text)" }}>Your Claim</h1>
          <p className="text-xs font-mono mt-0.5" style={{ color: "var(--text-subtle)" }}>Reference: {claim_id}</p>
        </div>
        <Link href="/submit" className="text-sm text-blue-500 hover:underline">Submit another</Link>
      </div>

      <div className="rounded-xl border px-4 py-3 flex items-center justify-between gap-4"
        style={{ background: "var(--bg-card)", borderColor: "var(--border)" }}>
        <div>
          <p className="text-xs font-medium" style={{ color: "var(--text)" }}>Save your reference number</p>
          <p className="text-xs mt-0.5 font-mono" style={{ color: "var(--text-muted)" }}>{claim_id}</p>
        </div>
        <CopyButton text={claim_id} />
      </div>

      {!status.is_terminal && (
        <div className="rounded-2xl border p-6" style={{ background: "var(--bg-card)", borderColor: "var(--border)" }}>
          <StatusStepper state={status.state} />
          <p className="text-center text-sm mt-5 animate-pulse" style={{ color: "var(--text-subtle)" }}>
            Analysing your evidence — please wait...
          </p>
        </div>
      )}

      {outcome && (
        <div className="rounded-2xl overflow-hidden border"
          style={{ borderColor: outcome.borderColor, background: outcome.bg }}>
          <div className="h-1 w-full" style={{ background: outcome.borderColor }} />
          <div className="p-5">
            <p className="font-semibold text-base" style={{ color: "var(--text)" }}>{outcome.title}</p>
            <p className="text-sm mt-1.5 leading-relaxed" style={{ color: "var(--text-muted)" }}>{outcomeBody}</p>
          </div>
        </div>
      )}

      {result && outcome?.showCost && <TotalCost findings={result.evidence.damage_findings} />}

      {result?.evidence.officer_note && status.state !== "denied" && (
        <div className="rounded-2xl border px-5 py-4"
          style={{ background: "var(--bg-card)", borderColor: "var(--border)" }}>
          <p className="text-xs font-semibold uppercase tracking-wide mb-1.5" style={{ color: "var(--text-subtle)" }}>
            Note from your claims officer
          </p>
          <p className="text-sm leading-relaxed" style={{ color: "var(--text)" }}>
            {result.evidence.officer_note}
          </p>
        </div>
      )}

      {status.state === "complete" && result?.evidence.claimant_letter && (
        <div className="rounded-2xl border p-6 space-y-2"
          style={{ background: "var(--bg-card)", borderColor: "var(--border)" }}>
          <p className="text-xs font-semibold uppercase tracking-wide" style={{ color: "var(--text-subtle)" }}>
            Claim Notice
          </p>
          <p className="text-sm leading-relaxed whitespace-pre-wrap" style={{ color: "var(--text-muted)" }}>
            {result.evidence.claimant_letter}
          </p>
        </div>
      )}
    </div>
  );
}
