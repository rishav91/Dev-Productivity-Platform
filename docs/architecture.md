# Architecture

## System flow

```
┌─────────────────────────────────────────────────────┐
│                    Inputs                           │
│  GitHub PR ──┐                                      │
│  Jira ticket ─┼── fixture-backed adapters           │
│  Slack thread ┘   (replay mode, no live API calls)  │
└────────────────────────┬────────────────────────────┘
                         │
                         ▼
┌─────────────────────────────────────────────────────┐
│              LangGraph Agent (4 nodes)              │
│                                                     │
│  1. extract          deterministic                  │
│       ↓              load typed data from fixtures  │
│  2. assemble         deterministic + retrieval      │
│       ↓              pgvector: baseline + recurrence│
│  3. hypothesize      LLM (focused)                  │
│       ↓              detect divergence signals only │
│  4. synthesize+gate  LLM + confidence gate          │
│                      produce InsightPayload via     │
│                      Claude tool use (typed schema) │
└────────────────────────┬────────────────────────────┘
                         │
            ┌────────────┴────────────┐
            ▼                         ▼
    Postgres (always)          pgvector (if confidence ≥ 0.7)
    full run record            enrich future retrieval
```

---

## The two retrieval queries

**Why retrieval is load-bearing, not optional:**

`assemble` runs two pgvector queries before any LLM call:

1. **Baseline calibration** — fetch historical PRs by the same author + overlapping files, compute p85 cycle time. Without this, severity is arbitrary.
2. **Recurrence detection** — fetch past `InsightPayload` records for the same component + blocker type. A pattern that has fired 4× this sprint is structural, not incidental.

The LLM receives these as grounding facts in the context bundle. It does not infer them.

---

## Node design

| Node | Type | Why separate |
|---|---|---|
| `extract` | Deterministic | Adapter calls are pure and testable without mocking LLMs |
| `assemble` | Deterministic + retrieval | Token budget enforced here, before any LLM call |
| `hypothesize` | LLM (cheap) | Narrow focus: detect signals only. Cheaper, faster, lower temperature |
| `synthesize_and_gate` | LLM + gate | Full reasoning + explicit confidence/owner gates |

Splitting `hypothesize` and `synthesize_and_gate` keeps each LLM call focused. The first detects; the second reasons and recommends. This reduces hallucination surface and makes prompts debuggable independently.

---

## Write-back loop

Every high-confidence result (`status = "insight"`, `confidence ≥ 0.7`) is embedded and written back into pgvector. This turns the retrieval layer into a self-improving knowledge base — severity baselines shift from synthetic approximations to real team-specific p85s over time.

Low-confidence results are stored in Postgres for debugging but **never** indexed into pgvector. Polluting the retrieval index with uncertain findings would degrade all future severity calibration.

---

## Stack rationale

**LangGraph over raw LLM calls**
The pipeline has two deterministic nodes and two LLM nodes with different roles. LangGraph makes the state explicit and each node independently testable. A chain or simple loop would obscure state transitions and make partial failures harder to debug.

**pgvector over a dedicated vector DB (Pinecone, Weaviate, etc.)**
The system already needs Postgres for `analysis_runs` persistence. Adding a second infrastructure dependency for embeddings creates ops overhead with no benefit at this scale. pgvector runs in the same container and supports the filtering needed (by component, blocker type, recurrence window).

**litellm provider abstraction**
The two LLM nodes use `litellm` via a thin wrapper in `backend/providers/llm.py`. This lets you swap `LLM_PROVIDER=groq` or `LLM_PROVIDER=ollama` without touching node code — useful for cost-sensitive eval runs. The default (Claude Sonnet) uses tool use with a typed schema; the wrapper normalizes Anthropic's `input_schema` field to the OpenAI `parameters` format litellm expects.

**FastAPI over Django/Flask**
Async-native and Pydantic-native. The agent is fully async; FastAPI is the only backend framework where that doesn't require bolted-on compatibility shims.

**Fixture-backed adapters**
All adapters read from JSON fixtures in `fixtures/scenarios/`. This enables deterministic eval runs, reproducible CI, and demos with no external API credentials. Phase 2 replaces the fixture reads with live API calls behind the same `SignalExtractor` interface.
