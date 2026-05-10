import type { FraudSignal } from "@/lib/api";

const SEVERITY_STYLES = {
  low: "bg-yellow-50 border-yellow-300 text-yellow-800",
  medium: "bg-orange-50 border-orange-300 text-orange-800",
  high: "bg-red-50 border-red-400 text-red-800",
};

const SEVERITY_BADGE = {
  low: "bg-yellow-100 text-yellow-700",
  medium: "bg-orange-100 text-orange-700",
  high: "bg-red-100 text-red-700",
};

interface FraudSignalCardProps {
  signal: FraudSignal;
}

export default function FraudSignalCard({ signal }: FraudSignalCardProps) {
  return (
    <div className={`border rounded-lg p-4 ${SEVERITY_STYLES[signal.severity]}`}>
      <div className="flex items-center justify-between mb-1">
        <span className="font-semibold text-sm">{signal.signal_type.replace(/_/g, " ")}</span>
        <span className={`text-xs px-2 py-0.5 rounded-full font-medium ${SEVERITY_BADGE[signal.severity]}`}>
          {signal.severity}
        </span>
      </div>
      <p className="text-sm leading-relaxed">{signal.description}</p>
      <p className="text-xs mt-1 opacity-60">
        confidence {(signal.confidence * 100).toFixed(0)}% · {signal.source.replace(/_/g, " ")}
      </p>
    </div>
  );
}
