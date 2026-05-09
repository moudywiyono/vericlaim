# VeriClaim

A multi-modal insurance claims triage and adjudication system built to demonstrate production-grade AI engineering patterns: specialist agent orchestration, hybrid RAG with citation enforcement, a synthetic perturbation eval harness, and end-to-end LLMOps instrumentation.

> **Research prototype** — fictional carrier "VeriClaim Mutual". Not deployable software.

---

## What it does

An insurance claim arrives as a mix of vehicle damage photos, scanned PDFs (police reports, repair estimates), claimant audio statements, and structured form data. The system routes it to a pipeline of specialist agents, aggregates their structured findings into a typed evidence boundary, and produces an adjudication packet: coverage determination with policy citations, fraud risk score, and a draft settlement letter.

```
Intake & Router
     │
     ├── Damage Assessor      (YOLO-World + SAM + VLM)
     ├── Document Extractor   (DocVQA)
     └── Statement Analyst    (Whisper + audio classifier + LLM)
                │
          EvidenceStore  ◄── typed schema boundary
                │
     ├── Policy Reasoner      (hybrid RAG + citation enforcement)
     ├── Fraud Aggregator     (gradient-boosted tabular + LLM soft signals)
     └── Consistency Auditor  (LLM)
                │
          Adjudicator          ◄── blind to raw evidence
                │
          Output Drafter
```

---

## Why this is hard to build well

Most "multi-modal AI" projects pass an image to a frontier model and call it done. The interesting problems here are:

**Hallucination in high-stakes decisions.** The Adjudicator is architecturally blind to raw evidence — it only sees structured `EvidenceStore` output from specialists. Every claim in its reasoning must cite a specific finding ID. Outputs that cite nonexistent evidence are rejected and regenerated. This makes failures auditable and localised.

**Evaluation when ground truth is fuzzy.** There is no clean ground truth for "correct adjudication." The eval harness uses a synthetic perturbation generator, component-level metrics appropriate to each modality, LLM-as-judge in pairwise mode (validated against a human-labelled gold set), and a protected 200-sample gold set that is never iterated against during development.

**Orchestrating specialists that fail differently.** A blurry image, a 429 rate limit, and a malformed LLM output are three different failure types that need three different responses. Every specialist failure is a first-class state in `EvidenceStore.specialist_status` — the graph always runs to completion, and downstream agents adapt their prompts based on what's missing.

**RAG over legal text.** Insurance policies break every assumption general-purpose RAG tutorials make: meaning lives in cross-references, negation dominates, and endorsements silently override master clauses. The retrieval layer uses section-aware chunking, hybrid BM25 + dense retrieval with RRF fusion, a cross-encoder reranker, and a three-layer citation validator (exists / supports / covers).

---

## Key design decisions

| Decision | Why |
|---|---|
| Static DAG, not agent swarm | Dynamic agent-calling is undebuggable in production. The orchestrator is ~300 lines of Python, not a framework magic box. |
| Adjudicator blind to raw evidence | Forces auditable reasoning, limits prompt injection surface, and localises failures to specific specialists. |
| Four RAG corpora, not one | Policy / endorsements / regulations / guidelines have different authority levels. The adjudicator must know which corpus a finding came from. |
| Custom orchestrator over LangGraph | The graph is small and rigid. Fine-grained tracing is required. Custom wins on debuggability. |
| Eval harness built first | Component evals go live before the full agent graph. This is the discipline that separates the system from vibes-driven development. |

---

## Project status

| Phase | Scope | Status |
|---|---|---|
| 1 — Foundation | Orchestration scaffold, EvidenceStore schema, ingestion & routing, eval harness skeleton | ✅ Complete |
| 2 — Damage Assessor + Document Extractor | First vertical slice end-to-end with component evals | 🔜 Next |
| 3 — Policy Reasoner (RAG) + Statement Analyst + Fraud Aggregator | Full agent graph wired into Adjudicator | Planned |
| 4 — E2E eval, adversarial testing, LLMOps dashboards | Full evaluation suite, cost optimisation | Planned |
| 5 — Demo UI + writeup | Streamlit or Next.js, recorded walkthrough | Planned |

**Phase 1 test coverage:** 156 tests across state immutability, DAG topology, retry/circuit-breaker state machines, SQLite persistence, JSONL tracing, and eval harness contracts.

---

## Stack

- **Python 3.13**, Pydantic v2, asyncio
- **LiteLLM** — provider-agnostic LLM calls (swap backend without touching agent code)
- **HuggingFace Transformers** — `facebook/bart-large-mnli` for zero-shot claim routing
- **bge-large-en-v1.5** + **rank_bm25** + **bge-reranker-v2-m3** — RAG retrieval pipeline
- **SQLite** (→ Postgres migration path documented) — claim state machine persistence
- **Langfuse** (self-hosted) — trace store, prompt versioning, LLMOps dashboards
- **pytest** + **pytest-asyncio** — test harness

---

## Quickstart

```bash
git clone https://github.com/moudywiyono/vericlaim.git
cd vericlaim

python3.13 -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"

cp .env.example .env
# Add ANTHROPIC_API_KEY or OPENAI_API_KEY to .env

pytest tests/
```

To run the stub pipeline end-to-end:

```bash
# Create a minimal claim directory
mkdir -p data/sample_claim
echo '{"claim_id":"demo-001","claim_type":"auto","images":[],"pdfs":[],"audio":[],"form_data":{"description":"Minor rear-end collision at low speed."}}' \
  > data/sample_claim/manifest.json

python -m orchestration.orchestrator --manifest-dir data/sample_claim
```

---

## Architecture deep-dive

See [ARCHITECTURE.md](ARCHITECTURE.md) for the full design document: directory structure, EvidenceStore schema, failure handling taxonomy, eval metrics per component, RAG retrieval design, and the anti-patterns explicitly avoided.
