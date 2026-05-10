const BASE_URL = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

export function getFileUrl(claimId: string, filename: string): string {
  return `${BASE_URL}/claims/${claimId}/files/${encodeURIComponent(filename)}`;
}

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
}

export interface ClaimResultResponse {
  claim_id: string;
  state: string;
  evidence: Evidence;
}

export interface ReviewQueueItem {
  claim_id: string;
  state: string;
  claim_type: string | null;
  routing_confidence: number | null;
  fraud_signal_count: number;
  created_at: string;
}

export interface ReviewQueueResponse {
  items: ReviewQueueItem[];
  total: number;
}

export interface ReviewDetailResponse {
  claim_id: string;
  state: string;
  claim_type: string | null;
  routing_confidence: number | null;
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

export async function getReviewQueue(): Promise<ReviewQueueResponse> {
  return request<ReviewQueueResponse>("/review/queue");
}

export interface HistoryItem {
  claim_id: string;
  state: string;
  claim_type: string | null;
  routing_confidence: number | null;
  fraud_signal_count: number;
  officer_note: string;
  decided_at: string;
}

export interface HistoryResponse {
  items: HistoryItem[];
  total: number;
}

export async function getHistory(): Promise<HistoryResponse> {
  return request<HistoryResponse>("/review/history");
}

export async function getReviewDetail(claimId: string): Promise<ReviewDetailResponse> {
  return request<ReviewDetailResponse>(`/review/${claimId}`);
}

export interface ClaimFilesResponse {
  images: string[];
  pdfs: string[];
  audio: string[];
  description: string;
}

export async function getClaimFiles(claimId: string): Promise<ClaimFilesResponse> {
  return request<ClaimFilesResponse>(`/claims/${claimId}/files`);
}

export async function postOfficerDecision(
  claimId: string,
  decision: "approve" | "deny" | "request_info",
  note: string
): Promise<void> {
  await request(`/review/${claimId}/decision`, {
    method: "PATCH",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ decision, note }),
  });
}
