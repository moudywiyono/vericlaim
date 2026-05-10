"use client";

const STEPS = [
  { key: "routing", label: "Routing" },
  { key: "evidence_gathering", label: "Evidence" },
  { key: "reasoning", label: "Reasoning" },
  { key: "adjudicating", label: "Adjudicating" },
  { key: "drafting", label: "Drafting" },
];

const TERMINAL = ["complete", "human_review", "failed"];

function stepIndex(state: string): number {
  const map: Record<string, number> = {
    received: -1,
    routing: 0,
    evidence_gathering: 1,
    reasoning: 2,
    adjudicating: 3,
    drafting: 4,
    complete: 5,
    human_review: 5,
    failed: 5,
  };
  return map[state] ?? -1;
}

interface ClaimStatusTrackerProps {
  state: string;
}

export default function ClaimStatusTracker({ state }: ClaimStatusTrackerProps) {
  const current = stepIndex(state);
  const done = TERMINAL.includes(state);

  return (
    <div className="w-full">
      <div className="flex items-center justify-between">
        {STEPS.map((step, i) => {
          const completed = i < current || done;
          const active = i === current && !done;
          return (
            <div key={step.key} className="flex-1 flex flex-col items-center">
              <div className="flex items-center w-full">
                {i > 0 && (
                  <div className={`flex-1 h-1 ${completed || active ? "bg-blue-500" : "bg-gray-200"}`} />
                )}
                <div
                  className={`w-8 h-8 rounded-full flex items-center justify-center text-sm font-bold shrink-0 transition-colors
                    ${completed ? "bg-blue-500 text-white"
                    : active ? "bg-blue-100 border-2 border-blue-500 text-blue-600"
                    : "bg-gray-200 text-gray-400"}`}
                >
                  {completed ? "✓" : i + 1}
                </div>
                {i < STEPS.length - 1 && (
                  <div className={`flex-1 h-1 ${completed ? "bg-blue-500" : "bg-gray-200"}`} />
                )}
              </div>
              <span className={`text-xs mt-1 ${active ? "text-blue-600 font-semibold" : completed ? "text-blue-500" : "text-gray-400"}`}>
                {step.label}
              </span>
            </div>
          );
        })}
      </div>

      {!done && (
        <p className="text-center text-sm text-gray-500 mt-4 animate-pulse">
          Processing — this takes about 60 seconds...
        </p>
      )}
    </div>
  );
}
