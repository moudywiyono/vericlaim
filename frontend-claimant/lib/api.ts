const BASE_URL = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

export interface ClaimSubmitResponse {
  claim_id: string;
  status: string;
}

export interface ClaimStatusResponse {
  claim_id: string;
  state: string;
  claim_type: string | null;
  routing_confidence: number | null;
  specialist_status: Record<string, string>;
  is_terminal: boolean;
}

export interface DamageFinding {
  region_id: string;
  category: "cosmetic" | "moderate" | "severe" | "total_loss";
  description: string;
  estimated_cost_usd: number;
  cost_confidence: number;
}

export interface DocumentFinding {
  field_name: string;
  value: string;
  page: number;
  extraction_confidence: number;
}

export interface StatementFinding {
  claim: string;
  timestamp_in_audio: number;
  speaker_confidence: number;
}

export interface PolicyFinding {
  clause_id: string;
  corpus_layer: string;
  determination: string;
  cited_text: string;
  confidence: number;
}

export interface FraudSignal {
  signal_type: string;
  description: string;
  severity: "low" | "medium" | "high";
  confidence: number;
  source: string;
}

export interface ConsistencyFlag {
  flag_type: string;
  description: string;
  severity: "minor" | "major" | "critical";
}

export interface Evidence {
  claim_id: string;
  damage_findings: DamageFinding[];
  document_findings: DocumentFinding[];
  statement_findings: StatementFinding[];
  policy_findings: PolicyFinding[];
  fraud_signals: FraudSignal[];
  consistency_flags: ConsistencyFlag[];
  specialist_status: Record<string, string>;
  claimant_letter: string;
  officer_note: string;
}

export interface ClaimResultResponse {
  claim_id: string;
  state: string;
  evidence: Evidence;
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(`${BASE_URL}${path}`, init);
  if (!res.ok) {
    const text = await res.text();
    throw new Error(`${res.status} ${res.statusText}: ${text}`);
  }
  return res.json() as Promise<T>;
}

export async function submitClaim(formData: FormData): Promise<ClaimSubmitResponse> {
  return request<ClaimSubmitResponse>("/claims", { method: "POST", body: formData });
}

export async function getClaimStatus(claimId: string): Promise<ClaimStatusResponse> {
  return request<ClaimStatusResponse>(`/claims/${claimId}/status`);
}

export async function getClaimResult(claimId: string): Promise<ClaimResultResponse> {
  return request<ClaimResultResponse>(`/claims/${claimId}/result`);
}

