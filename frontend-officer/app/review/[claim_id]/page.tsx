"use client";

import { useEffect, useState } from "react";
import { useParams, useRouter, useSearchParams } from "next/navigation";
import Link from "next/link";
import { getReviewDetail, getClaimFiles, getFileUrl, postOfficerDecision, type ReviewDetailResponse, type ClaimFilesResponse } from "@/lib/api";

const FLAG_STYLE: Record<string, { bg: string; border: string }> = {
  minor:    { bg: "rgba(234,179,8,0.06)",   border: "#fde047" },
  major:    { bg: "rgba(249,115,22,0.06)",  border: "#fdba74" },
  critical: { bg: "rgba(239,68,68,0.06)",   border: "#fca5a5" },
};

const SIGNAL_STYLE: Record<string, { bg: string; border: string }> = {
  low:    { bg: "rgba(234,179,8,0.06)",   border: "#fde047" },
  medium: { bg: "rgba(249,115,22,0.06)",  border: "#fdba74" },
  high:   { bg: "rgba(239,68,68,0.06)",   border: "#fca5a5" },
};

const DETERMINATION_BADGE: Record<string, string> = {
  covered:      "bg-green-100 text-green-700",
  denied:       "bg-red-100 text-red-700",
  partial:      "bg-yellow-100 text-yellow-700",
  ambiguous:    "bg-orange-100 text-orange-700",
  needs_review: "bg-orange-100 text-orange-700",
};

const DETERMINATION_LABEL: Record<string, string> = {
  covered:      "Covered",
  denied:       "Not covered",
  partial:      "Partially covered",
  ambiguous:    "Unclear — needs your call",
  needs_review: "Needs review",
};

const DETERMINATION_HINT: Record<string, string> = {
  covered:      "This clause clearly applies and covers the claim.",
  denied:       "This clause clearly excludes this type of claim.",
  partial:      "This clause covers part of the claim but not all of it.",
  ambiguous:    "The clause language could be read either way for this claim. The AI could not make a confident determination — this requires your judgment.",
  needs_review: "The AI flagged this clause as requiring human review before a decision can be made.",
};

const CORPUS_LAYER_LABEL: Record<string, string> = {
  policy_document: "policy document",
  endorsement:     "endorsement",
  state_regulation: "state regulation",
  internal_guideline: "internal guideline",
};

const POLICY_VERDICT: Record<string, { label: string; color: string; bg: string }> = {
  covered:     { label: "Covered",     color: "#16a34a", bg: "rgba(34,197,94,0.08)"  },
  not_covered: { label: "Not Covered", color: "#dc2626", bg: "rgba(239,68,68,0.08)"  },
  unclear:     { label: "Unclear",     color: "#d97706", bg: "rgba(245,158,11,0.08)" },
  unknown:     { label: "Unknown",     color: "var(--text-subtle)", bg: "var(--bg-subtle)" },
};

function InfoTooltip({ text, align = "left", direction = "up" }: { text: string; align?: "left" | "right"; direction?: "up" | "down" }) {
  const isUp = direction === "up";
  return (
    <span className="relative group ml-1.5" style={{ display: "inline-block", verticalAlign: "middle" }}>
      <span className="inline-flex items-center justify-center rounded-full border cursor-help font-bold leading-none"
        style={{ width: "13px", height: "13px", fontSize: "9px", borderColor: "var(--text-subtle)", color: "var(--text-subtle)" }}>
        i
      </span>
      <span
        className="absolute w-60 rounded-lg px-3 py-2 text-xs leading-relaxed pointer-events-none opacity-0 group-hover:opacity-100 transition-opacity z-50 normal-case font-normal"
        style={{
          background: "#1e293b", color: "#f1f5f9", whiteSpace: "normal",
          ...(isUp ? { bottom: "100%", marginBottom: "8px" } : { top: "100%", marginTop: "8px" }),
          ...(align === "right" ? { right: 0 } : { left: 0 }),
        }}>
        {text}
        {isUp
          ? <span className="absolute top-full border-4 border-transparent"
              style={{ borderTopColor: "#1e293b", ...(align === "right" ? { right: "8px" } : { left: "8px" }) }} />
          : <span className="absolute bottom-full border-4 border-transparent"
              style={{ borderBottomColor: "#1e293b", ...(align === "right" ? { right: "8px" } : { left: "8px" }) }} />
        }
      </span>
    </span>
  );
}

type Tab = "files" | "risk" | "damage" | "statement" | "documents" | "policy";

const DECIDED_STATES = new Set(["approved", "denied", "complete"]);

export default function ReviewDetailPage() {
  const { claim_id } = useParams<{ claim_id: string }>();
  const router = useRouter();
  const searchParams = useSearchParams();
  const from = searchParams.get("from") ?? "review";
  const [detail, setDetail] = useState<ReviewDetailResponse | null>(null);
  const [claimFiles, setClaimFiles] = useState<ClaimFilesResponse | null>(null);
  const [error, setError] = useState("");
  const [tab, setTab] = useState<Tab>("files");
  const [note, setNote] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [decided, setDecided] = useState(false);

  useEffect(() => {
    getReviewDetail(claim_id).then(setDetail).catch((e) => setError(e.message));
    getClaimFiles(claim_id).then(setClaimFiles).catch(() => {});
  }, [claim_id]);

  const isAlreadyDecided = detail ? DECIDED_STATES.has(detail.state) : false;

  const decide = async (decision: "approve" | "deny" | "request_info") => {
    setSubmitting(true);
    try {
      await postOfficerDecision(claim_id, decision, note);
      setDecided(true);
      setTimeout(() => router.push(`/${from}`), 1500);
    } finally {
      setSubmitting(false);
    }
  };

  if (error) return (
    <div className="p-8">
      <div className="rounded-2xl border border-red-300 p-5 text-red-500"
        style={{ background: "rgba(239,68,68,0.06)" }}>
        <p className="font-semibold">Error loading claim</p>
        <p className="text-sm mt-1">{error}</p>
      </div>
    </div>
  );

  if (!detail) return (
    <div className="p-8 animate-pulse" style={{ color: "var(--text-subtle)" }}>Loading claim...</div>
  );

  const { evidence } = detail;
  const totalDamage = evidence.damage_findings.reduce((s, f) => s + f.estimated_cost_usd, 0);

  const highSignals = evidence.fraud_signals.filter(s => s.severity === "high");
  const criticalFlags = evidence.consistency_flags.filter(f => f.severity === "critical");
  const topSignal = highSignals[0] ?? evidence.fraud_signals[0];
  const topFlag = criticalFlags[0] ?? evidence.consistency_flags[0];
  const topConcernLabel = topSignal?.signal_type.replace(/_/g, " ") ?? topFlag?.flag_type.replace(/_/g, " ") ?? "";
  const topConcernDesc = topSignal?.description ?? topFlag?.description ?? "";

  const policyDenied = evidence.policy_findings.filter(f => f.determination === "denied");
  const policyAmbiguous = evidence.policy_findings.filter(f => f.determination === "needs_review" || f.determination === "ambiguous");
  const policyKey = policyDenied.length > 0 ? "not_covered"
    : policyAmbiguous.length > 0 ? "unclear"
    : evidence.policy_findings.length > 0 ? "covered"
    : "unknown";
  const verdict = POLICY_VERDICT[policyKey];

  const totalFileCount = claimFiles
    ? claimFiles.images.length + claimFiles.pdfs.length + claimFiles.audio.length
    : undefined;

  const TABS: { key: Tab; label: string; count?: number; tooltip?: string; tooltipAlign?: "left" | "right" }[] = [
    { key: "files",     label: "Files",     count: totalFileCount },
    { key: "risk",      label: "Risk",      count: evidence.fraud_signals.length + evidence.consistency_flags.length },
    { key: "damage",    label: "Damage",    count: evidence.damage_findings.length,
      tooltip: "Cost estimates are generated by our AI from submitted photos — not taken from the claimant's repair quote. Cross-check against the Documents tab to spot inflated estimates." },
    { key: "statement", label: "Statement", count: evidence.statement_findings.length,
      tooltip: "Findings are extracted from the claimant's written description and any uploaded voice or video recordings. Items with a timestamp were sourced from audio — use the Files tab to listen to the original recording.",
      tooltipAlign: "right" },
    { key: "documents", label: "Documents", count: evidence.document_findings.length },
    { key: "policy",    label: "Policy",    count: evidence.policy_findings.length,
      tooltip: "Each row is a policy clause the AI checked against this claim. Covered and Not covered are clear-cut. Unclear clauses are where your judgment is needed — review the quoted text and decide.",
      tooltipAlign: "right" },
  ];


  return (
    <div className="p-8">
      {/* Header */}
      <div className="mb-5">
        <Link href={`/${from}`} className="text-sm text-blue-500 hover:underline">
          ← Back to {from === "history" ? "history" : "queue"}
        </Link>
        <div className="flex items-center gap-2.5 mt-2 flex-wrap">
          <h1 className="text-xl font-bold font-mono" style={{ color: "var(--text)" }}>{claim_id}</h1>
          <span className="text-xs px-2 py-0.5 rounded-full capitalize font-medium"
            style={{ background: "var(--bg-subtle)", color: "var(--text-muted)" }}>
            {detail.claim_type ?? "unknown"}
          </span>
          <span className="text-xs px-2 py-0.5 rounded-full font-medium capitalize bg-amber-500/10 text-amber-500">
            {detail.state.replace(/_/g, " ")}
          </span>
        </div>
      </div>

      {/* Two-column layout */}
      <div className="flex gap-5 items-start">

        {/* Left column: summary + decision (sticky) */}
        <div className="w-64 shrink-0 space-y-4 sticky top-6">

          {/* What happened */}
          {claimFiles?.description && (
            <div className="rounded-2xl border p-4" style={{ background: "var(--bg-card)", borderColor: "var(--border)" }}>
              <p className="text-xs font-semibold uppercase tracking-wide mb-1.5" style={{ color: "var(--text-subtle)" }}>
                What happened
              </p>
              <p className="text-sm leading-relaxed overflow-y-auto" style={{ color: "var(--text)", maxHeight: "8rem" }}>
                {claimFiles.description}
              </p>
            </div>
          )}

          {/* AI assessment */}
          <div className="rounded-2xl border p-4 space-y-3" style={{ background: "var(--bg-card)", borderColor: "var(--border)" }}>
            <p className="text-xs font-semibold uppercase tracking-wide" style={{ color: "var(--text-subtle)" }}>
              AI Assessment
            </p>

            <div className="flex gap-2">
              <div className="flex-1 rounded-xl p-2.5 text-center" style={{ background: verdict.bg }}>
                <p className="text-xs font-semibold" style={{ color: verdict.color }}>{verdict.label}</p>
                <p className="text-xs mt-0.5" style={{ color: "var(--text-subtle)" }}>policy</p>
              </div>
              {totalDamage > 0 && (
                <div className="flex-1 rounded-xl p-2.5 text-center" style={{ background: "var(--bg-subtle)" }}>
                  <p className="text-xs font-semibold" style={{ color: "var(--text)" }}>
                    ${totalDamage.toLocaleString("en-US", { maximumFractionDigits: 0 })}
                  </p>
                  <p className="text-xs mt-0.5" style={{ color: "var(--text-subtle)" }}>est. damage</p>
                </div>
              )}
            </div>

            {topConcernLabel ? (
              <div className="rounded-xl border-l-4 px-3 py-2.5 space-y-1"
                style={{ borderColor: "#ef4444", background: "rgba(239,68,68,0.04)" }}>
                <p className="text-xs font-semibold capitalize" style={{ color: "var(--text)" }}>
                  {topConcernLabel}
                </p>
                <p className="text-xs leading-relaxed" style={{ color: "var(--text-muted)" }}>
                  {topConcernDesc}
                </p>
              </div>
            ) : (
              <p className="text-xs" style={{ color: "var(--text-subtle)" }}>No risk signals detected.</p>
            )}
          </div>

          {/* Decision */}
          {isAlreadyDecided ? (
            <div className="border rounded-2xl px-4 py-3"
              style={{
                background: detail.state === "approved" ? "rgba(34,197,94,0.06)" : detail.state === "denied" ? "rgba(239,68,68,0.06)" : "rgba(37,99,235,0.06)",
                borderColor: detail.state === "approved" ? "#86efac" : detail.state === "denied" ? "#fca5a5" : "#93c5fd",
              }}>
              <p className="text-sm font-semibold capitalize" style={{ color: "var(--text)" }}>
                {detail.state === "approved" ? "Approved" : detail.state === "denied" ? "Denied" : "AI auto-decided"}
              </p>
              <p className="text-xs mt-0.5" style={{ color: "var(--text-muted)" }}>No further action required</p>
            </div>
          ) : decided ? (
            <div className="border rounded-2xl p-4 text-center font-semibold text-green-500"
              style={{ background: "rgba(34,197,94,0.06)", borderColor: "#4ade80" }}>
              Decision recorded — returning...
            </div>
          ) : (
            <div className="rounded-2xl border p-4 space-y-3"
              style={{ background: "var(--bg-card)", borderColor: "var(--border)" }}>
              <p className="text-xs font-semibold uppercase tracking-wide" style={{ color: "var(--text-subtle)" }}>
                Your Decision
              </p>
              <textarea
                className="w-full rounded-xl px-3 py-2 text-sm resize-none focus:outline-none focus:ring-2 focus:ring-blue-400 transition-shadow"
                style={{ background: "var(--bg-subtle)", border: "1px solid var(--border)", color: "var(--text)" }}
                rows={2}
                placeholder="Note for claimant (optional)"
                value={note}
                onChange={(e) => setNote(e.target.value)}
                disabled={submitting}
              />
              <button onClick={() => decide("approve")} disabled={submitting}
                className="w-full bg-green-600 hover:bg-green-700 text-white font-semibold py-2.5 rounded-xl text-sm transition-colors disabled:opacity-50">
                Approve Claim
              </button>
              <div className="flex gap-2">
                <button onClick={() => decide("deny")} disabled={submitting}
                  className="flex-1 bg-red-600 hover:bg-red-700 text-white font-semibold py-2 rounded-xl text-sm transition-colors disabled:opacity-50">
                  Deny
                </button>
                <button onClick={() => decide("request_info")} disabled={submitting}
                  className="flex-1 bg-amber-500 hover:bg-amber-600 text-white font-semibold py-2 rounded-xl text-sm transition-colors disabled:opacity-50">
                  Request Info
                </button>
              </div>
            </div>
          )}
        </div>

        {/* Right column: evidence tabs */}
        <div className="flex-1 min-w-0 rounded-2xl border shadow-sm"
          style={{ background: "var(--bg-card)", borderColor: "var(--border)" }}>
          <div className="flex border-b px-4" style={{ borderColor: "var(--border)" }}>
            {TABS.map((t) => (
              <button key={t.key} onClick={() => setTab(t.key)}
                className="px-4 py-3 text-sm font-medium border-b-2 transition-colors -mb-px shrink-0 flex items-center gap-1"
                style={{
                  borderColor: tab === t.key ? "var(--accent)" : "transparent",
                  color: tab === t.key ? "var(--accent)" : "var(--text-muted)",
                }}>
                {t.label}
                {t.count !== undefined && t.count > 0 && (
                  <span className="text-xs px-1.5 py-0.5 rounded-full"
                    style={{ background: "var(--bg-subtle)", color: "var(--text-subtle)" }}>
                    {t.count}
                  </span>
                )}
                {t.tooltip && <InfoTooltip text={t.tooltip} align={t.tooltipAlign} direction="down" />}
              </button>
            ))}
          </div>

          <div className="p-5 space-y-3">

            {tab === "files" && (
              <>
                {!claimFiles && (
                  <p className="text-sm animate-pulse" style={{ color: "var(--text-subtle)" }}>Loading files...</p>
                )}
                {claimFiles && claimFiles.images.length > 0 && (
                  <div>
                    <p className="text-xs font-semibold uppercase tracking-wide mb-2" style={{ color: "var(--text-subtle)" }}>Photos</p>
                    <div className="grid grid-cols-2 gap-3">
                      {claimFiles.images.map((img) => (
                        <a key={img} href={getFileUrl(claim_id, img)} target="_blank" rel="noopener noreferrer"
                          className="block rounded-xl overflow-hidden border hover:opacity-90 transition-opacity"
                          style={{ borderColor: "var(--border)" }}>
                          <img src={getFileUrl(claim_id, img)} alt={img}
                            className="w-full object-cover" style={{ maxHeight: "200px" }} />
                          <p className="text-xs px-2 py-1 truncate" style={{ color: "var(--text-muted)" }}>{img}</p>
                        </a>
                      ))}
                    </div>
                  </div>
                )}
                {claimFiles && claimFiles.pdfs.length > 0 && (
                  <div className="space-y-4">
                    <p className="text-xs font-semibold uppercase tracking-wide" style={{ color: "var(--text-subtle)" }}>Documents (PDF)</p>
                    {claimFiles.pdfs.map((pdf) => (
                      <div key={pdf} className="border rounded-xl overflow-hidden"
                        style={{ borderColor: "var(--border)" }}>
                        <div className="flex items-center justify-between px-3 py-2 border-b"
                          style={{ background: "var(--bg-subtle)", borderColor: "var(--border)" }}>
                          <span className="text-sm font-medium truncate" style={{ color: "var(--text)" }}>{pdf}</span>
                          <a href={getFileUrl(claim_id, pdf)} target="_blank" rel="noopener noreferrer"
                            className="text-xs ml-3 shrink-0 hover:underline" style={{ color: "var(--accent)" }}>
                            Open in new tab
                          </a>
                        </div>
                        <iframe
                          src={getFileUrl(claim_id, pdf)}
                          className="w-full"
                          style={{ height: "600px", border: "none" }}
                          title={pdf}
                        />
                      </div>
                    ))}
                  </div>
                )}
                {claimFiles && claimFiles.audio.length > 0 && (
                  <div>
                    <p className="text-xs font-semibold uppercase tracking-wide mb-2" style={{ color: "var(--text-subtle)" }}>Audio Recordings</p>
                    <div className="space-y-3">
                      {claimFiles.audio.map((file) => (
                        <div key={file} className="border rounded-xl p-3 space-y-2" style={{ borderColor: "var(--border)" }}>
                          <p className="text-sm font-medium" style={{ color: "var(--text)" }}>{file}</p>
                          <audio controls className="w-full" style={{ height: "36px" }}>
                            <source src={getFileUrl(claim_id, file)} />
                          </audio>
                        </div>
                      ))}
                    </div>
                  </div>
                )}
                {claimFiles && claimFiles.images.length === 0 && claimFiles.pdfs.length === 0
                  && claimFiles.audio.length === 0 && (
                  <p className="text-sm" style={{ color: "var(--text-subtle)" }}>No files submitted with this claim.</p>
                )}
              </>
            )}

            {tab === "risk" && (() => {
              const SIGNAL_DOT: Record<string, string> = { high: "bg-red-500", medium: "bg-orange-400", low: "bg-yellow-400" };
              const FLAG_DOT: Record<string, string>   = { critical: "bg-red-500", major: "bg-orange-400", minor: "bg-yellow-400" };
              const SIGNAL_RANK: Record<string, number> = { high: 3, medium: 2, low: 1 };
              const FLAG_RANK: Record<string, number>   = { critical: 3, major: 2, minor: 1 };

              const groupedSignals = evidence.fraud_signals.reduce((acc, s) => {
                (acc[s.signal_type] = acc[s.signal_type] ?? []).push(s); return acc;
              }, {} as Record<string, typeof evidence.fraud_signals>);

              const groupedFlags = evidence.consistency_flags.reduce((acc, f) => {
                (acc[f.flag_type] = acc[f.flag_type] ?? []).push(f); return acc;
              }, {} as Record<string, typeof evidence.consistency_flags>);

              return (
                <>
                  {evidence.fraud_signals.length === 0 && evidence.consistency_flags.length === 0 && (
                    <p className="text-sm" style={{ color: "var(--text-subtle)" }}>No risk signals detected.</p>
                  )}

                  {evidence.fraud_signals.length > 0 && (
                    <>
                      <p className="text-xs font-semibold uppercase tracking-wide pb-1" style={{ color: "var(--text-subtle)" }}>
                        Fraud Signals
                        <InfoTooltip text="Behavioral patterns suggesting intent to deceive — e.g. inconsistent accounts, prior similar claims, implausible damage sequence. Each signal shows a severity (high / medium / low) and how certain the AI is that it is a real signal rather than a false alarm." />
                      </p>
                      {Object.entries(groupedSignals).map(([type, signals]) => {
                        const worst = signals.reduce((a, b) => (SIGNAL_RANK[a.severity] ?? 0) >= (SIGNAL_RANK[b.severity] ?? 0) ? a : b);
                        return (
                          <div key={type} className="border rounded-xl overflow-hidden text-sm"
                            style={{ borderColor: SIGNAL_STYLE[worst.severity]?.border ?? "var(--border)" }}>
                            <div className="flex items-center justify-between px-4 py-2.5"
                              style={{ background: SIGNAL_STYLE[worst.severity]?.bg ?? "var(--bg-subtle)" }}>
                              <span className="font-semibold capitalize" style={{ color: "var(--text)" }}>
                                {type.replace(/_/g, " ")}
                              </span>
                              {signals.length > 1 && (
                                <span className="text-xs px-1.5 py-0.5 rounded-full"
                                  style={{ background: "rgba(0,0,0,0.08)", color: "var(--text-muted)" }}>
                                  {signals.length}
                                </span>
                              )}
                            </div>
                            {signals.map((s, i) => (
                              <div key={i} className="flex items-start gap-3 px-4 py-2.5 border-t"
                                style={{ borderColor: "var(--border)" }}>
                                <span className={`mt-1.5 w-2 h-2 rounded-full shrink-0 ${SIGNAL_DOT[s.severity] ?? "bg-gray-400"}`} />
                                <p className="flex-1 leading-relaxed" style={{ color: "var(--text-muted)" }}>{s.description}</p>
                                <span className="text-xs capitalize shrink-0 mt-0.5 text-right" style={{ color: "var(--text-subtle)" }}>
                                  {s.severity}<br />
                                  {(s.confidence * 100).toFixed(0)}% certain
                                </span>
                              </div>
                            ))}
                          </div>
                        );
                      })}
                    </>
                  )}

                  {evidence.consistency_flags.length > 0 && (
                    <>
                      <p className="text-xs font-semibold uppercase tracking-wide pt-2 pb-1" style={{ color: "var(--text-subtle)" }}>
                        Consistency Flags
                        <InfoTooltip text="Factual contradictions between submitted documents, photos, and the claimant's account — e.g. a repair invoice that doesn't match the damage in photos, or dates that don't line up. Severity is critical / major / minor." />
                      </p>
                      {Object.entries(groupedFlags).map(([type, flags]) => {
                        const worst = flags.reduce((a, b) => (FLAG_RANK[a.severity] ?? 0) >= (FLAG_RANK[b.severity] ?? 0) ? a : b);
                        return (
                          <div key={type} className="border rounded-xl overflow-hidden text-sm"
                            style={{ borderColor: FLAG_STYLE[worst.severity]?.border ?? "var(--border)" }}>
                            <div className="flex items-center justify-between px-4 py-2.5"
                              style={{ background: FLAG_STYLE[worst.severity]?.bg ?? "var(--bg-subtle)" }}>
                              <span className="font-semibold capitalize" style={{ color: "var(--text)" }}>
                                {type.replace(/_/g, " ")}
                              </span>
                              {flags.length > 1 && (
                                <span className="text-xs px-1.5 py-0.5 rounded-full"
                                  style={{ background: "rgba(0,0,0,0.08)", color: "var(--text-muted)" }}>
                                  {flags.length}
                                </span>
                              )}
                            </div>
                            {flags.map((f, i) => (
                              <div key={i} className="flex items-start gap-3 px-4 py-2.5 border-t"
                                style={{ borderColor: "var(--border)" }}>
                                <span className={`mt-1.5 w-2 h-2 rounded-full shrink-0 ${FLAG_DOT[f.severity] ?? "bg-gray-400"}`} />
                                <p className="flex-1 leading-relaxed" style={{ color: "var(--text-muted)" }}>{f.description}</p>
                                <span className="text-xs capitalize shrink-0 mt-0.5" style={{ color: "var(--text-subtle)" }}>
                                  {f.severity}
                                </span>
                              </div>
                            ))}
                          </div>
                        );
                      })}
                    </>
                  )}
                </>
              );
            })()}

            {tab === "damage" && (
              <>
                {evidence.damage_findings.length === 0 && (
                  <p className="text-sm" style={{ color: "var(--text-subtle)" }}>No damage findings.</p>
                )}
                {evidence.damage_findings.map((f, i) => (
                  <div key={i} className="border rounded-xl p-4 text-sm" style={{ borderColor: "var(--border)" }}>
                    <div className="flex items-center justify-between mb-1">
                      <span className="font-semibold capitalize" style={{ color: "var(--text)" }}>
                        {f.region_id.replace(/_/g, " ")}
                      </span>
                      <span className="text-xs capitalize" style={{ color: "var(--text-muted)" }}>
                        {f.category} · ${f.estimated_cost_usd.toLocaleString()}
                      </span>
                    </div>
                    <p style={{ color: "var(--text-muted)" }}>{f.description}</p>
                  </div>
                ))}
              </>
            )}

            {tab === "statement" && (
              <>
                {evidence.statement_findings.length === 0 && (
                  <p className="text-sm" style={{ color: "var(--text-subtle)" }}>No statement findings.</p>
                )}
                {evidence.statement_findings.map((f, i) => (
                  <div key={i} className="border rounded-xl p-4 text-sm" style={{ borderColor: "var(--border)" }}>
                    <p style={{ color: "var(--text)" }}>{f.claim}</p>
                    <p className="text-xs mt-1" style={{ color: "var(--text-subtle)" }}>
                      <span title="How clearly the AI captured this from the audio recording">
                        transcription clarity {(f.speaker_confidence * 100).toFixed(0)}%
                      </span>
                      {f.timestamp_in_audio > 0 && ` · at ${f.timestamp_in_audio.toFixed(1)}s in recording`}
                    </p>
                  </div>
                ))}
              </>
            )}

            {tab === "documents" && (
              <>
                {evidence.document_findings.length === 0 && (
                  <p className="text-sm" style={{ color: "var(--text-subtle)" }}>No document findings.</p>
                )}
                <div>
                  {evidence.document_findings.map((f, i) => (
                    <div key={i} className="flex items-center justify-between py-2.5 text-sm border-b last:border-0"
                      style={{ borderColor: "var(--border)" }}>
                      <span className="capitalize w-40 shrink-0" style={{ color: "var(--text-muted)" }}>
                        {f.field_name.replace(/_/g, " ")}
                      </span>
                      <span className="font-medium flex-1 mx-4" style={{ color: "var(--text)" }}>{f.value}</span>
                      <span className="text-xs shrink-0" style={{ color: "var(--text-subtle)" }}>
                        {(f.extraction_confidence * 100).toFixed(0)}%
                      </span>
                    </div>
                  ))}
                </div>
              </>
            )}

            {tab === "policy" && (
              <>
                {evidence.policy_findings.length === 0 && (
                  <p className="text-sm" style={{ color: "var(--text-subtle)" }}>No policy findings.</p>
                )}
                {evidence.policy_findings.map((f, i) => (
                  <div key={i} className="border rounded-xl overflow-hidden text-sm" style={{ borderColor: "var(--border)" }}>
                    <div className="flex items-center justify-between px-4 py-2.5"
                      style={{ background: "var(--bg-subtle)" }}>
                      <span className="font-semibold" style={{ color: "var(--text)" }}>{f.clause_id}</span>
                      <span className={`text-xs px-2 py-0.5 rounded-full font-medium
                        ${DETERMINATION_BADGE[f.determination] ?? "bg-gray-100 text-gray-600"}`}>
                        {DETERMINATION_LABEL[f.determination] ?? f.determination}
                      </span>
                    </div>
                    <div className="px-4 py-3 space-y-2">
                      {f.determination === "ambiguous" && DETERMINATION_HINT[f.determination] && (
                        <p className="text-xs font-medium" style={{ color: "var(--text)" }}>
                          {DETERMINATION_HINT[f.determination]}
                        </p>
                      )}
                      <p className="italic border-l-2 pl-3 text-xs leading-relaxed"
                        style={{ borderColor: "var(--border)", color: "var(--text-muted)" }}>
                        {f.cited_text}
                      </p>
                      <p className="text-xs" style={{ color: "var(--text-subtle)" }}>
                        Source: {CORPUS_LAYER_LABEL[f.corpus_layer] ?? f.corpus_layer}
                        {" · "}AI certainty: {(f.confidence * 100).toFixed(0)}%
                      </p>
                    </div>
                  </div>
                ))}
              </>
            )}

          </div>
        </div>
      </div>
    </div>
  );
}
