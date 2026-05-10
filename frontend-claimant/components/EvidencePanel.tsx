"use client";

import { useState } from "react";
import type { Evidence } from "@/lib/api";

const CATEGORY_COLOR = {
  cosmetic: "bg-green-100 text-green-700",
  moderate: "bg-yellow-100 text-yellow-700",
  severe: "bg-orange-100 text-orange-700",
  total_loss: "bg-red-100 text-red-700",
};

const DETERMINATION_COLOR: Record<string, string> = {
  covered: "bg-green-100 text-green-700",
  denied: "bg-red-100 text-red-700",
  partial: "bg-yellow-100 text-yellow-700",
  ambiguous: "bg-gray-100 text-gray-700",
  needs_review: "bg-orange-100 text-orange-700",
};

const TABS = ["Damage", "Documents", "Statement", "Policy"] as const;
type Tab = typeof TABS[number];

interface EvidencePanelProps {
  evidence: Evidence;
}

export default function EvidencePanel({ evidence }: EvidencePanelProps) {
  const [active, setActive] = useState<Tab>("Damage");

  return (
    <div>
      <div className="flex border-b mb-4">
        {TABS.map((tab) => (
          <button
            key={tab}
            onClick={() => setActive(tab)}
            className={`px-4 py-2 text-sm font-medium border-b-2 transition-colors
              ${active === tab ? "border-blue-500 text-blue-600" : "border-transparent text-gray-500 hover:text-gray-700"}`}
          >
            {tab}
            <span className="ml-1 text-xs text-gray-400">
              ({tab === "Damage" ? evidence.damage_findings.length
                : tab === "Documents" ? evidence.document_findings.length
                : tab === "Statement" ? evidence.statement_findings.length
                : evidence.policy_findings.length})
            </span>
          </button>
        ))}
      </div>

      {active === "Damage" && (
        <div className="space-y-3">
          {evidence.damage_findings.length === 0 && <p className="text-gray-400 text-sm">No damage findings.</p>}
          {evidence.damage_findings.map((f, i) => (
            <div key={i} className="border rounded-lg p-4">
              <div className="flex items-center justify-between mb-1">
                <span className="font-medium text-sm">{f.region_id.replace(/_/g, " ")}</span>
                <span className={`text-xs px-2 py-0.5 rounded-full font-medium ${CATEGORY_COLOR[f.category]}`}>
                  {f.category}
                </span>
              </div>
              <p className="text-sm text-gray-600">{f.description}</p>
              <p className="text-xs text-gray-400 mt-1">
                Est. ${f.estimated_cost_usd.toLocaleString()} · confidence {(f.cost_confidence * 100).toFixed(0)}%
              </p>
            </div>
          ))}
        </div>
      )}

      {active === "Documents" && (
        <div className="space-y-2">
          {evidence.document_findings.length === 0 && <p className="text-gray-400 text-sm">No document findings.</p>}
          {evidence.document_findings.map((f, i) => (
            <div key={i} className="flex items-start justify-between border rounded-lg px-4 py-3 text-sm">
              <span className="font-medium text-gray-700 w-40 shrink-0">{f.field_name.replace(/_/g, " ")}</span>
              <span className="text-gray-600 flex-1 mx-4">{f.value}</span>
              <span className="text-xs text-gray-400 shrink-0">{(f.extraction_confidence * 100).toFixed(0)}%</span>
            </div>
          ))}
        </div>
      )}

      {active === "Statement" && (
        <div className="space-y-2">
          {evidence.statement_findings.length === 0 && <p className="text-gray-400 text-sm">No statement findings.</p>}
          {evidence.statement_findings.map((f, i) => (
            <div key={i} className="border rounded-lg px-4 py-3 text-sm">
              <p className="text-gray-700">{f.claim}</p>
              <p className="text-xs text-gray-400 mt-1">
                confidence {(f.speaker_confidence * 100).toFixed(0)}%
                {f.timestamp_in_audio > 0 && ` · ${f.timestamp_in_audio.toFixed(1)}s`}
              </p>
            </div>
          ))}
        </div>
      )}

      {active === "Policy" && (
        <div className="space-y-3">
          {evidence.policy_findings.length === 0 && <p className="text-gray-400 text-sm">No policy findings.</p>}
          {evidence.policy_findings.map((f, i) => (
            <div key={i} className="border rounded-lg p-4">
              <div className="flex items-center justify-between mb-1">
                <span className="font-medium text-sm">{f.clause_id}</span>
                <span className={`text-xs px-2 py-0.5 rounded-full font-medium ${DETERMINATION_COLOR[f.determination] ?? "bg-gray-100 text-gray-700"}`}>
                  {f.determination}
                </span>
              </div>
              <p className="text-xs text-gray-500 italic border-l-2 border-gray-200 pl-2 mt-1">{f.cited_text}</p>
              <p className="text-xs text-gray-400 mt-1">{f.corpus_layer} · {(f.confidence * 100).toFixed(0)}%</p>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
