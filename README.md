# VeriClaim

A multi-modal insurance claims triage and adjudication system built to demonstrate production-grade AI engineering patterns: specialist agent orchestration, hybrid RAG with citation enforcement, a synthetic perturbation eval harness, and end-to-end LLMOps instrumentation.

> **Research prototype** — fictional carrier "VeriClaim Mutual". Not production software.

---

## What it does

An insurance claim arrives as a mix of vehicle damage photos, scanned PDFs (police reports, repair estimates), claimant audio statements, and structured form data. The system routes it to a pipeline of specialist agents, aggregates their structured findings into a typed evidence boundary, and produces an adjudication packet: coverage determination with policy citations, fraud risk score, and a draft settlement letter.

```
Intake & Router
     │
     ├── Damage Assessor      (VLM)
     ├── Document Extractor   (pypdf + LLM)
     └── Statement Analyst    (LLM)
                │
          EvidenceStore  ◄── typed schema boundary
                │
     ├── Policy Reasoner      (hybrid RAG + citation enforcement)
     ├── Fraud Aggregator     (LLM soft signals)
     └── Consistency Auditor  (LLM)
                │
          Adjudicator          ◄── blind to raw evidence
                │
          Output Drafter
```

Fully automated claims go straight to a decision. Ambiguous or high-risk claims are escalated to a human officer via a dedicated review portal.

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
| 2 — Damage Assessor + Document Extractor | First vertical slice end-to-end with component evals | ✅ Complete |
| 3 — Reasoning layer | Policy Reasoner (RAG), Statement Analyst, Fraud Aggregator, Consistency Auditor, Adjudicator, Output Drafter | ✅ Complete |
| 4 — LLMOps | Langfuse tracing, PromptRegistry, cost/latency dashboards | ✅ Complete |
| 5 — Full-stack UI | FastAPI backend, claimant portal (port 3000), officer portal (port 3001) | ✅ Complete |

---

## Stack

**Backend**
- **Python 3.13**, Pydantic v2, asyncio
- **FastAPI** — REST API, async claim pipeline runner, file serving
- **LiteLLM** — provider-agnostic LLM calls (swap backend without touching agent code)
- **HuggingFace Transformers** — `facebook/bart-large-mnli` for zero-shot claim routing
- **bge-large-en-v1.5** + **rank_bm25** + **bge-reranker-v2-m3** — RAG retrieval pipeline
- **Supabase** — claim state machine persistence
- **Langfuse** (self-hosted) — trace store, prompt versioning, LLMOps dashboards
- **pytest** + **pytest-asyncio** — test harness

**Frontend**
- **Next.js 15** (App Router), TypeScript, Tailwind CSS v4
- Claimant portal (port 3000) — claim submission, real-time status polling, outcome display
- Officer portal (port 3001) — review queue, two-column evidence review, decision panel

---

## Quickstart

### 1. Python environment

```bash
git clone https://github.com/moudywiyono/vericlaim.git
cd vericlaim

python3.13 -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"

cp .env.example .env
# Fill in ANTHROPIC_API_KEY and SUPABASE_URL + SUPABASE_SERVICE_ROLE_KEY
```

### 2. Build the RAG index

The policy reasoner requires a pre-built index from the corpus before the backend will serve claims.

```bash
source .venv/bin/activate
python -m rag.indexing.build --corpus-dir data/synthetic/vericlaim_mutual
```

This downloads the embedding and reranker models on first run (~1.5 GB). Subsequent starts are instant.

### 3. Run tests

```bash
pytest tests/ -v
```

### 4. Start the backend

```bash
source .venv/bin/activate
uvicorn backend.main:app --reload --port 8000
```

### 5. Start the frontends

```bash
# Claimant portal — http://localhost:3000
cd frontend-claimant && npm install && npm run dev

# Officer portal — http://localhost:3001 (new terminal)
cd frontend-officer && npm install && npm run dev
```

---

## Environment variables

See `.env.example` for the full list. Required to run the full stack:

| Variable | Where to get it |
|---|---|
| `ANTHROPIC_API_KEY` | console.anthropic.com |
| `SUPABASE_URL` | Supabase project settings |
| `SUPABASE_SERVICE_ROLE_KEY` | Supabase project settings → API |
| `NEXT_PUBLIC_API_URL` | Set in `frontend-claimant/.env.local` and `frontend-officer/.env.local` (defaults to `http://localhost:8000`) |
| `CORS_ORIGINS` | Comma-separated frontend URLs (defaults to `http://localhost:3000,http://localhost:3001`) |

Langfuse tracing is optional — leave `LANGFUSE_PUBLIC_KEY` and `LANGFUSE_SECRET_KEY` blank to disable.

---

## Architecture deep-dive

See [ARCHITECTURE.md](ARCHITECTURE.md) for the full design document: directory structure, EvidenceStore schema, failure handling taxonomy, eval metrics per component, RAG retrieval design, and the anti-patterns explicitly avoided.
