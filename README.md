# Dev Productivity Platform

A contextual insight engine that detects when a PR, ticket, and team communication are diverging — and explains why it matters, calibrated against your team's actual history.

**The core question:** Given a PR + ticket + optional Slack thread, is something going wrong? If so, how bad is it *for this team*, and has it happened before?

---

## Why this exists

"PR open 6 days" means nothing without context. Is that normal for this author? This component? This reviewer? The system answers severity relative to a team-specific baseline — not generic thresholds.

This is not a one-shot classifier. Two retrieval queries are genuinely load-bearing:

1. **Baseline calibration** — compute p85 review cycle from the author's and component's history before assigning severity
2. **Recurrence detection** — check whether this blocker pattern has fired before on this component, upgrading severity if it's structural

→ See [docs/architecture.md](docs/architecture.md) for a full explanation of why each node exists.

---

## Quick start

```bash
# 1. Start Postgres with pgvector
docker compose up -d

# 2. Install dependencies
pip install -e ".[dev]"

# 3. Copy env and configure
cp .env.example .env
# Set ANTHROPIC_API_KEY (and optionally LANGCHAIN_API_KEY for tracing)

# 4. Run migrations + seed synthetic history
psql $DATABASE_URL -f db/migrations/001_init.sql
python fixtures/seed_db.py

# 5. Start the API
uvicorn backend.main:app --reload

# 6. Run evals
python -m backend.evals.runner
```

The system runs fully offline (no live GitHub/Jira/Slack calls). All data comes from fixture files.

---

## What it produces

```json
{
  "status": "insight",
  "blocker_type": "review_bottleneck",
  "severity": 4,
  "owner": "eng_bob",
  "owner_confidence": 0.91,
  "summary": "PR has been open 9 days, exceeding eng_bob's p85 review cycle of 6.2 days. Slack confirms the team is actively waiting.",
  "recommended_actions": ["Escalate review to eng_bob directly", "Consider reassigning reviewer"],
  "confidence": 0.80,
  "recurrence_count": 3,
  "baseline_cycle_p85_days": 6.2
}
```

When evidence is thin, it abstains: `status = "insufficient_evidence"`, `owner = null`. See [docs/abstention.md](docs/abstention.md).

---

## Docs

- [Architecture & design decisions](docs/architecture.md)
- [Data schemas](docs/schemas.md)
- [Eval harness & results](docs/evals.md)
- [Abstention & degraded-mode behavior](docs/abstention.md)
- [Provider configuration (LLM + embeddings)](docs/providers.md)

---

## Stack

| Layer | Choice |
|---|---|
| Agent orchestration | LangGraph |
| LLM | Claude Sonnet (default), swappable via `LLM_PROVIDER` |
| Vector store | pgvector (PostgreSQL) |
| Backend | FastAPI |
| Tracing | LangSmith |
| Frontend | Next.js results card |

Reasons for each choice: [docs/architecture.md#stack-rationale](docs/architecture.md#stack-rationale)
