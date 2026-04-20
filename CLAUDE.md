# Dev Productivity Platform

> "Given a PR + ticket + optional Slack thread, detect divergence, calibrate severity against
> this team's historical baseline, and flag if this pattern is recurring — producing a grounded,
> confidence-gated InsightPayload."

This is a portfolio project targeting a Senior AI Engineer role. Code quality, eval harness, explainability, and abstention behavior matter as much as features.

**Background reading (understand before changing things):**
- [Architecture & stack rationale](docs/architecture.md)
- [Data schemas](docs/schemas.md)
- [Abstention & confidence gates](docs/abstention.md)
- [Eval harness & metrics](docs/evals.md)
- [LLM + embedding provider config](docs/providers.md)

---

## Coding conventions

- All Pydantic models live in `backend/schemas/models.py` — never define schemas inline
- All prompts live in `backend/agent/prompts.py` with a version comment — never inline strings
- Every LangGraph node must be decorated with `@traceable` for LangSmith
- Never parse LLM free-form text — always use tool use with a typed schema
- Adapters are pure functions, no side effects, fully testable without mocking LLMs
- Token budget is enforced in `backend/context/assembly.py` before any LLM call — not inside nodes (max 80k tokens total)

## Hard rules (enforced in code, not prompts)

- `owner` is never assigned when `owner_confidence < 0.65`
- `status = "insufficient_evidence"` when `confidence < 0.5` — never speculate
- `baseline_cycle_p85_days = None` and severity capped at 2 when `history_sample_size < 5`
- Write-back to pgvector only when `insight.status == "insight"` and `insight.confidence >= 0.7`
- Retrieval queries filter to the last 90 days by default — never let stale history silently dominate

---

## Build order

1. `fixtures/personas.py` + `fixtures/generate.py` — synthetic data first; everything depends on it
2. `fixtures/seed_db.py` + `db/migrations/001_init.sql` — pgvector running with seeded data
3. `backend/schemas/models.py` — all Pydantic types, SourceType enum, SignalExtractor ABC
4. `backend/adapters/` — fixture-backed adapters, unit-tested against scenario files
5. `backend/context/embeddings.py` + `backend/context/assembly.py` — retrieval queries against seeded pgvector
6. `backend/agent/state.py` + `backend/agent/nodes.py` — nodes with mocked LLM calls initially
7. `backend/agent/graph.py` — wire the graph, test deterministic nodes end-to-end
8. `backend/agent/prompts.py` + real Claude calls — replace mocks, enforce tool use schema
9. `backend/evals/` — build dataset + runner, run against all 15–20 scenarios, commit report
10. `backend/main.py` — FastAPI endpoints with AnalysisRun persistence
11. `frontend/` — results page last

---

## Deferred to phase 2

Do not implement these in MVP:

- Live GitHub / Jira / Slack API calls (replace fixture adapters)
- Webhook ingestion + event-driven re-analysis
- Sprint velocity signals
- `RepoHistoryExtractor` + `WebhookEventExtractor`
- Multi-workspace support
- Full dashboard beyond the results card
- Cross-platform identity resolution (GitHub ↔ Jira ↔ Slack user mapping)

---

## Environment variables

See `.env.example` for the full list. Required for MVP:

```
ANTHROPIC_API_KEY=
DATABASE_URL=postgresql://localhost:5432/devplatform
LANGCHAIN_API_KEY=
LANGCHAIN_TRACING_V2=true
LANGCHAIN_PROJECT=dev-productivity-platform
```

Provider switching (`LLM_PROVIDER`, `EMBED_PROVIDER`) is documented in [docs/providers.md](docs/providers.md).
