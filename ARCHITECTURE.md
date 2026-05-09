# VeriClaim — Context

## What This Is

A multi-modal insurance claims triage and adjudication system. Research prototype — not production-deployable software. The fictional carrier is **VeriClaim Mutual**. The point is to demonstrate: serious multi-modal pipelines, rigorous evaluation methodology, and production-grade operational patterns in a high-stakes domain.

---

## Architecture

Five layers, strict separation between them:

```
Layer 1 — Ingestion & Routing
  Zero-shot classifier routes claims to the right downstream graph
  (auto / property / liability / health)

Layer 2 — Multi-Agent Orchestration
  Static DAG. Specialists run in parallel where safe; coordinator is code, not LLM.

Layer 3 — EvidenceStore (typed schema boundary)
  Specialists write structured findings here. Downstream agents read from here only.

Layer 4 — Adjudicator
  Cannot see raw evidence — only structured EvidenceStore. Forces auditable reasoning.

Layer 5 — Output
  Structured adjudication packet + draft settlement letter.
```

### Execution Graph

```
Intake & Router
    ↓
[Damage Assessor] [Document Extractor] [Statement Analyst]  ← parallel, Stage 2
    ↓                ↓                     ↓
                EvidenceStore
    ↓                ↓                     ↓
[Policy Reasoner] [Fraud Aggregator] [Consistency Auditor]  ← parallel, Stage 3
    ↓                ↓                     ↓
                  Adjudicator              ← Stage 4, blind to raw evidence
                      ↓
                Output Drafter
```

**Stage timing target:** ~22s end-to-end (Stage 2 dominates at ~8s).

---

## Directory Structure

```
vericlaim/
├── ARCHITECTURE.md
├── pyproject.toml
├── .env.example
│
├── ingestion/
│   ├── router.py             # zero-shot claim type classifier
│   └── intake.py             # receive + validate incoming claim packet
│
├── orchestration/
│   ├── graph.py              # static DAG definition
│   ├── orchestrator.py       # async executor: retries, timeouts, tracing
│   ├── state.py              # EvidenceStore schema + claim state machine
│   ├── nodes/
│   │   ├── base.py
│   │   ├── router.py
│   │   ├── damage_assessor.py
│   │   ├── document_extractor.py
│   │   ├── statement_analyst.py
│   │   ├── policy_reasoner.py
│   │   ├── fraud_aggregator.py
│   │   ├── consistency_auditor.py
│   │   ├── adjudicator.py
│   │   └── output_drafter.py
│   ├── failure/
│   │   ├── retry.py
│   │   ├── circuit_breaker.py
│   │   └── degradation.py    # downstream prompts adapt to upstream failures
│   ├── persistence/
│   │   ├── trace_store.py
│   │   └── state_store.py
│   └── tools/
│       └── replay.py         # CLI: replay from any node with overridden prompt
│
├── rag/
│   ├── ingestion/
│   │   ├── policy_parser.py          # parses TOC, section hierarchy, cross-refs
│   │   ├── chunker.py                # section-aware, with metadata enrichment
│   │   ├── endorsement_linker.py     # links endorsements to master clauses
│   │   └── definition_extractor.py
│   ├── indexing/
│   │   ├── dense_indexer.py          # bge-large-en-v1.5 embeddings
│   │   ├── sparse_indexer.py         # BM25 via rank_bm25
│   │   └── collections/              # 4 separate indices (policy/endorsements/regs/guidelines)
│   ├── retrieval/
│   │   ├── hybrid.py                 # RRF fusion
│   │   ├── reranker.py               # bge-reranker-v2-m3 cross-encoder
│   │   ├── query_decomposer.py       # multi-query generation
│   │   ├── hyde.py                   # gated HyDE (only for abstract queries)
│   │   └── orchestrator.py
│   ├── generation/
│   │   ├── adjudicator_prompt.py
│   │   ├── citation_validator.py     # 3-layer check: exists / supports / covers
│   │   └── refusal_logic.py
│   └── eval/
│       ├── retrieval_eval.py
│       ├── citation_eval.py
│       └── ablations/
│
├── evals/
│   ├── datasets/
│   │   ├── component/                # per-agent eval sets
│   │   ├── e2e_gold/                 # 200-sample gold set, version-locked, never iterated against
│   │   ├── adversarial/              # injection, OOD, fairness probes
│   │   └── synthetic/                # generated perturbations, seeded + deterministic
│   ├── perturbation/
│   │   ├── image_perturb.py          # JPEG compression, blur, low-light, occlusion
│   │   ├── audio_perturb.py          # SNR levels, accent variation, background noise
│   │   ├── document_perturb.py       # scan resolution, rotation, OCR noise
│   │   └── fraud_signal_inject.py    # staged patterns, velocity anomalies, narrative inconsistencies
│   ├── metrics/
│   │   ├── damage_metrics.py         # mAP, macro-F1, MAPE, grounding fidelity
│   │   ├── rag_metrics.py            # Recall@k, MRR, faithfulness, RAGAS-style
│   │   ├── calibration.py            # reliability diagrams, ECE
│   │   └── pairwise_judge.py         # LLM-as-judge in pairwise mode
│   ├── runners/
│   │   ├── component_suite.py
│   │   ├── e2e_suite.py
│   │   └── adversarial_suite.py
│   ├── dashboards/
│   └── CHANGELOG.md                  # eval changelog: date / change / metric delta / decision
│
├── data/
│   ├── synthetic/
│   │   └── vericlaim_mutual/         # fictional carrier policy corpus
│   └── external/                     # CarDD, DocVQA samples, NAIC codes (gitignored)
│
└── ops/
    ├── langfuse/                      # self-hosted Langfuse config
    └── ci/
        └── eval_runner.yml            # eval-as-CI: runs on every PR, posts delta report
```

---

## Key Design Decisions

### Adjudicator Blindness
The adjudicator cannot see raw images, audio, or policy text — only the structured `EvidenceStore`. This forces auditable reasoning, limits prompt injection surface, and localizes failures to specific specialists. The tradeoff: the adjudicator can't notice emergent patterns in raw evidence that specialists missed. This is correct for a high-stakes auditable system.

### Static Graph, Not Agent Swarm
The execution graph is a static DAG. Specialists don't decide what happens next; the orchestrator does. This is intentional: dynamic agent-calling looks impressive in demos and is undebuggable in production. The orchestrator is ~300 lines of Python, not a framework magic box.

### Custom Orchestrator Over LangGraph
Evaluated LangGraph, CrewAI, and custom. The graph is small, dependencies are static, and fine-grained tracing is required. Custom wins on all three. If LangGraph is used later, it should be as a structural scaffold only — no tool-calling agent abstractions for specialists.

### Four RAG Corpora, Not One
Policy / endorsements / state regulations / carrier guidelines are indexed separately. They have different authority levels (binding vs. overriding vs. advisory). The adjudicator must know which corpus a finding came from.

### Section-Aware Chunking
Each chunk carries `path`, `parent_summary`, `cross_refs`, `clause_id`. Definitions are duplicated into referencing chunks. Endorsements are linked to the master clauses they modify and are always co-retrieved.

### Eval Before Features
The eval harness skeleton is built first (Weeks 1–2). Component evals go live before the full agent graph does. This is the architectural discipline that separates this from vibes-driven development.

### EvidenceStore as Eval Interface
The `EvidenceStore` schema doubles as a mock boundary. Specialists can be bypassed by populating EvidenceStore directly, enabling isolated eval of the Adjudicator and OutputDrafter.

---

## EvidenceStore Schema (key types)

```python
class DamageFinding(BaseModel):
    region_id: str
    category: Literal["cosmetic", "moderate", "severe", "total_loss"]
    description: str
    estimated_cost_usd: float
    cost_confidence: float
    evidence_uri: str

class DocumentFinding(BaseModel):
    field_name: str
    value: str
    page: int
    bbox: tuple[float, float, float, float]
    extraction_confidence: float

class StatementFinding(BaseModel):
    claim: str
    timestamp_in_audio: float
    speaker_confidence: float
    cross_refs: list[CrossRef]

class EvidenceStore(BaseModel):
    claim_id: str
    damage_findings: list[DamageFinding]
    document_findings: list[DocumentFinding]
    statement_findings: list[StatementFinding]
    policy_findings: list[PolicyFinding]
    fraud_signals: list[FraudSignal]
    consistency_flags: list[ConsistencyFlag]
    specialist_status: dict[str, AgentStatus]  # success/partial/failed per agent
```

---

## Specialist Agents — Responsibilities

| Agent | Inputs | Key models |
|---|---|---|
| Damage Assessor | Images | YOLO-World (detection), SAM (segmentation), VLM (description) |
| Document Extractor | PDFs | DocVQA model |
| Statement Analyst | Audio | Whisper-v3 (ASR), audio classifier (stress markers), LLM (cross-ref) |
| Policy Reasoner | EvidenceStore fields | RAG: bge-large + BM25 + bge-reranker-v2-m3 |
| Fraud Aggregator | EvidenceStore + claim history | Gradient-boosted tabular + LLM soft signals |
| Consistency Auditor | Full EvidenceStore | LLM |
| Adjudicator | EvidenceStore only | LLM via LiteLLM (structured output, citation-enforced) |
| Output Drafter | Adjudicator output | LLM via LiteLLM |

---

## Failure Handling

Every specialist failure is a first-class state in `EvidenceStore.specialist_status`, not an exception. The graph continues. Downstream agents adapt via prompt injection of status flags (e.g., "damage_assessor: failed — do not reference damage findings").

| Failure type | Response |
|---|---|
| Transient (timeout, 429) | Exponential backoff, max 3 retries |
| Input quality (blurry image) | Return `partial` with reason, no retry |
| Schema violation | Retry with parse error in context, max 2 attempts |
| Hard crash | `failed` in status, graph continues |
| Adversarial input | Sanitize, log, route to `HUMAN_REVIEW` |

---

## Claim State Machine

```
RECEIVED → ROUTING → EVIDENCE_GATHERING → REASONING → ADJUDICATING → DRAFTING → COMPLETE
                                                                          ↓
                                                                       FAILED
                                                                          ↓
                                                                    HUMAN_REVIEW
```

Persisted to SQLite (documented migration path to Postgres). Each transition timestamped. Enables crash recovery and free ops dashboards.

---

## Evaluation — Metrics by Component

**Damage Assessor:** mAP@0.5, macro-F1 (severity), MAPE bucketed by damage type, grounding fidelity %

**Document Extractor:** field-level exact match, ANLS, calibration reliability diagram

**Statement Analyst:** WER by SNR bucket, cross-modal consistency score (custom)

**Policy Reasoner (RAG):** Recall@k, MRR, faithfulness, citation correctness (3-layer: exists/supports/covers), endorsement attachment rate

**Fraud Aggregator:** AUC-ROC, PR-AUC, precision@k, performance at operating threshold

**End-to-end:** pairwise LLM judge (validated against human gold set, >80% agreement required), outcome proxy metrics

---

## Adversarial Evals

- Prompt injection in PDFs: measure before/after input sanitization
- OOD claims (marine cargo routed to auto pipeline): measure refusal vs. confabulation rate
- Demographic fairness probes: hold claim facts constant, vary demographic-correlated features
- Confidence calibration under degrading inputs

---

## LLMOps

Self-hosted Langfuse. Every trace carries: `trace_id`, `claim_id`, `prompt_hash`, `model_used`, `claim_type`, `severity_bucket`.

Prompts stored as versioned templates, referenced by hash in traces (never stored as full text in logs).

Four dashboards:
1. System health (daily): latency, error rate, cost/claim, auto-approve %
2. Quality trends (weekly): accuracy by sub-population, LLM judge scores, citation correctness
3. Model/prompt experiments: A/B deltas, per-sub-population breakdown
4. Cost & latency deep-dive: per-node, per-model, cost vs. accuracy tradeoff curves

Eval-as-CI: component + E2E suites run on every PR via GitHub Actions; delta report posts to PR.

---

## Data Sources

| Modality | Source |
|---|---|
| Vehicle damage images | CarDD, Stanford Cars |
| Document understanding | DocVQA, FUNSD |
| Tabular fraud signals | FNOL datasets (Kaggle) |
| Policy/regulatory text | NAIC model regulations, state codes, synthetic carrier templates |
| Audio | Common Voice + synthetic stress augmentation |
| Demo corpus | Synthetic "VeriClaim Mutual" policy docs (full corpus, no real PII) |

---

## Build Plan

**Weeks 1–2:** Scaffolding, ingestion, routing classifier, eval harness skeleton. Eval before features.

**Weeks 3–5:** Damage Assessor + Document Extractor end-to-end with component evals. One full vertical slice before adding agents.

**Weeks 6–8:** Policy Reasoner (RAG), Statement Analyst, Fraud Aggregator. Wire into Adjudicator.

**Weeks 9–10:** Full E2E eval, adversarial testing, LLMOps dashboard, cost optimization.

**Weeks 11–12:** Demo UI (Streamlit or Next.js), writeup with eval numbers, recorded walkthrough.

**If scope must be cut:** reduce modality breadth, not evaluation depth. Auto-only with rigorous eval > all claim types with thin eval.

---

## Conventions

- Python 3.11+
- Pydantic v2 for all inter-agent schemas
- `asyncio` for parallel execution; per-node timeouts, not per-graph
- Structured output (Pydantic) at every agent boundary — no free-text handoffs
- Idempotency key on every external call: `{claim_id}_{node_name}_{attempt}`
- Perturbation pipeline seeded and deterministic: reproducible from `(base_claim_id, axis, magnitude, seed)`
- Eval gold set (`evals/datasets/e2e_gold/`) is version-locked: never iterate prompts against it, only use for final reporting

---

## Important Anti-Patterns (explicitly avoided)

- Agents that decide the workflow dynamically
- Free-text inter-agent messages
- A "supervisor" LLM as orchestrator
- Sharing one giant context across agents
- Implicit retries inside agent code
- Naive flat chunking for policy documents
- Polling the gold eval set during development
