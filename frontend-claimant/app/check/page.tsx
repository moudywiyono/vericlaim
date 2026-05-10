"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";

export default function CheckProgressPage() {
  const router = useRouter();
  const [claimId, setClaimId] = useState("");
  const [error, setError] = useState("");

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    const id = claimId.trim().toUpperCase();
    if (!id) {
      setError("Please enter your claim reference number.");
      return;
    }
    router.push(`/status/${id}`);
  };

  return (
    <div className="max-w-lg mx-auto px-4 py-20">
      <div className="rounded-2xl border p-8 space-y-6" style={{ background: "#fff", borderColor: "var(--border)" }}>

        <div className="space-y-1">
          <h1 className="text-xl font-bold" style={{ color: "var(--text)" }}>Check Claim Progress</h1>
          <p className="text-sm" style={{ color: "var(--text-muted)" }}>
            Enter the reference number from your submission confirmation to see the current status.
          </p>
        </div>

        <form onSubmit={handleSubmit} className="space-y-4">
          <div className="space-y-1.5">
            <label className="text-sm font-medium" style={{ color: "var(--text)" }}>
              Claim Reference Number
            </label>
            <input
              type="text"
              value={claimId}
              onChange={(e) => { setClaimId(e.target.value); setError(""); }}
              placeholder="e.g. CLM-A1B2C3D4"
              className="w-full rounded-lg px-4 py-2.5 text-sm font-mono focus:outline-none focus:ring-2 focus:ring-blue-300 transition-shadow"
              style={{
                background: "var(--bg-subtle)",
                border: "1px solid var(--border)",
                color: "var(--text)",
              }}
            />
            {error && <p className="text-xs text-red-500">{error}</p>}
          </div>

          <button
            type="submit"
            className="w-full bg-blue-600 hover:bg-blue-700 text-white font-semibold py-2.5 rounded-lg text-sm transition-colors"
          >
            View Status
          </button>
        </form>

        <div className="rounded-lg border px-4 py-3 text-xs space-y-1"
          style={{ background: "var(--bg-subtle)", borderColor: "var(--border)", color: "var(--text-muted)" }}>
          <p className="font-medium" style={{ color: "var(--text)" }}>Where is my reference number?</p>
          <p>Your claim reference number was shown on the confirmation page immediately after you submitted your claim. It looks like <span className="font-mono">CLM-XXXXXXXX</span>.</p>
        </div>
      </div>
    </div>
  );
}
