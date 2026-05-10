"use client";

import { useState } from "react";
import { postOfficerDecision } from "@/lib/api";
import { useRouter } from "next/navigation";

interface OfficerDecisionPanelProps {
  claimId: string;
}

export default function OfficerDecisionPanel({ claimId }: OfficerDecisionPanelProps) {
  const router = useRouter();
  const [note, setNote] = useState("");
  const [loading, setLoading] = useState(false);
  const [done, setDone] = useState(false);

  const handleDecision = async (decision: "approve" | "deny" | "request_info") => {
    setLoading(true);
    try {
      await postOfficerDecision(claimId, decision, note);
      setDone(true);
      setTimeout(() => router.push("/review"), 1500);
    } finally {
      setLoading(false);
    }
  };

  if (done) {
    return (
      <div className="rounded-xl border border-green-300 bg-green-50 p-6 text-center">
        <p className="text-green-700 font-semibold">Decision recorded. Returning to queue...</p>
      </div>
    );
  }

  return (
    <div className="rounded-xl border bg-white p-6 space-y-4">
      <h3 className="font-semibold text-gray-800">Officer Decision</h3>
      <textarea
        className="w-full border rounded-lg px-3 py-2 text-sm resize-none focus:outline-none focus:ring-2 focus:ring-blue-300"
        rows={3}
        placeholder="Optional note (reason, missing documents, etc.)"
        value={note}
        onChange={(e) => setNote(e.target.value)}
        disabled={loading}
      />
      <div className="flex gap-3">
        <button
          onClick={() => handleDecision("approve")}
          disabled={loading}
          className="flex-1 bg-green-600 hover:bg-green-700 text-white font-medium py-2 rounded-lg text-sm transition-colors disabled:opacity-50"
        >
          ✓ Approve
        </button>
        <button
          onClick={() => handleDecision("deny")}
          disabled={loading}
          className="flex-1 bg-red-600 hover:bg-red-700 text-white font-medium py-2 rounded-lg text-sm transition-colors disabled:opacity-50"
        >
          ✕ Deny
        </button>
        <button
          onClick={() => handleDecision("request_info")}
          disabled={loading}
          className="flex-1 bg-yellow-500 hover:bg-yellow-600 text-white font-medium py-2 rounded-lg text-sm transition-colors disabled:opacity-50"
        >
          ↩ Request Info
        </button>
      </div>
    </div>
  );
}
