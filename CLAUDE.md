# Dev Productivity Platform — Vertical Slice

## Core question

> "Given a PR + ticket + optional Slack thread, detect divergence, calibrate severity against
> this team's historical baseline, and flag if this pattern is recurring — producing a grounded,
> confidence-gated InsightPayload."

This is not a one-shot divergence classifier. It is a contextual insight engine that reasons
against team history. Retrieval is load-bearing: severity calibration and recurrence detection
cannot be answered from primary inputs alone.

This is also a portfolio project targeting a Senior AI Engineer role. Code quality, eval harness,
explainability, and abstention behavior matter as much as features.

---

## Stack

| Layer | Choice | Why |
|---|---|---|
| Agent orchestration | LangGraph | Explicit stateful graph, mixed deterministic + LLM nodes |
| LLM | Claude API (claude-sonnet-4-20250514) | Long context, reliable tool use for structured output |
| Vector store | pgvector (PostgreSQL) | Baseline retrieval + recurrence detection |
| Backend | FastAPI | Async, Pydantic-native |
| Frontend | Thin Next.js results page | Show InsightPayload card only — no full dashboard yet |
| Tracing / evals | LangSmith | Trace every agent run from day one |
| Integrations | Fixture-backed adapters only in MVP | Replay mode, no live API calls required |

---

## Architecture

```
GitHub PR ──┐
Jira ticket ─┼── Ingestion adapters ── Context assembly
Slack thread ┘   (fixture-backed)      (pgvector retrieval)
                                               │
                                    ┌──────────▼──────────┐
                                    │   LangGraph agent   │
                                    │                     │
                                    │  1. extract         │  ← deterministic
                                    │       ↓             │
                                    │  2. assemble        │  ← deterministic + retrieval
                                    │       ↓             │
                                    │  3. hypothesize     │  ← LLM (divergence signals)
                                    │       ↓             │
                                    │  4. synthesize+gate │  ← LLM + confidence gate
                                    └──────────┬──────────┘
                                               │
                                    Claude API (tool use)
                                               │
                                    InsightPayload (typed)
                                               │
                              ┌────────────────┴────────────────┐
                              │  Postgres: AnalysisRun + result  │
                              └────────────────┬────────────────┘
                                               │
                                    FastAPI → results page
```

---

## Why retrieval is load-bearing

The primary inputs (PR + ticket + Slack) contain evidence for divergence detection but not for
severity calibration or recurrence. Two retrieval queries are genuinely necessary:

**Baseline severity calibration**
"PR open 6 days" has no meaning in isolation. Severity is only meaningful relative to that
team's historical review cycle. The `assemble` node retrieves historical PRs by the same author
and overlapping files to compute a p85 baseline. Without this, severity is arbitrary.

**Recurrence detection**
"Has this blocker pattern appeared before on this component?" requires retrieving past
InsightPayload records for similar tickets. If review bottlenecks on `payments/` have fired
4 times this sprint, that is a structural problem. The `synthesize` node uses recurrence count
to upgrade severity and shift recommended actions toward structural fixes.

```python
# context/assembly.py — retrieval answers specific questions the LLM cannot answer alone
async def assemble(pr: PRData, ticket: TicketData) -> ContextBundle:
    similar_prs = await retrieve_similar_prs(
        author=pr.author,
        file_paths=pr.changed_files,
        limit=10
    )
    past_insights = await retrieve_past_insights(
        component=ticket.component,
        blocker_types=["review_bottleneck", "scope_creep"],
        limit=5
    )
    return ContextBundle(
        primary_pr=pr,
        primary_ticket=ticket,
        baseline_cycle_p85_days=compute_p85(similar_prs),
        recurrence_count=len(past_insights),
        past_insight_summaries=[i.summary for i in past_insights],
        history_sample_size=len(similar_prs),
    )
```

---

## Knowledge accumulation (write-back loop)

Every completed analysis is written back into pgvector, turning the retrieval layer into a
self-improving knowledge base. Severity calibration and recurrence detection get sharper over
time as real team data replaces synthetic baselines.

```python
# After synthesize_and_gate completes — called from main.py
async def persist_and_index(run: AnalysisRun, insight: InsightPayload):
    # 1. Always save to Postgres for querying and debugging
    await db.save_analysis_run(run, insight)

    # 2. Only index high-confidence findings into pgvector
    if insight.status == "insight" and insight.confidence >= 0.7:
        embedding = await embed(insight.summary + " " + insight.blocker_type)
        await pgvector.upsert(
            id=run.run_id,
            embedding=embedding,
            metadata={
                "component": run.request.ticket_component,
                "blocker_type": insight.blocker_type,
                "severity": insight.severity,
                "owner": insight.owner,
                "created_at": run.completed_at,
            }
        )
```

**Two guardrails are mandatory:**

**Index only high-confidence findings.** `status = "insufficient_evidence"` results are stored
in Postgres for debugging but never written to pgvector. Indexing low-confidence outputs
pollutes the retrieval index and degrades future severity calibration.

**Decay old embeddings.** Retrieval queries filter to insights from the last 90 days by default.
A blocker pattern from 18 months ago reflects a team dynamic that may no longer exist. Expand
the window explicitly when needed — don't let stale history silently dominate recency.

Over time the value compounds in two specific ways:
- Severity baselines shift from synthetic persona approximations to real team-specific p85s
- Recurrence detection fires against actual historical blockers, not seeded fixtures

This makes the system meaningfully different from RAG over a static corpus — every production
analysis enriches future analyses.

## Synthetic data strategy

Because there is no demo-safe real data, the fixture layer is core MVP scope — not a nice-to-have.

### Why data must be statistically shaped, not random

Random cycle times produce noise baselines and meaningless retrieval context. The generator
must encode realistic team dynamics so the retrieval layer produces genuine signal.

### Parametric generation model

```python
# fixtures/personas.py
TEAM_PERSONAS = [
    TeamMember(id="eng_alice", avg_review_days=1.5, stddev=0.8),   # fast reviewer
    TeamMember(id="eng_bob",   avg_review_days=6.2, stddev=2.1),   # consistent bottleneck
    TeamMember(id="eng_carol", avg_review_days=2.8, stddev=1.2),
    TeamMember(id="eng_dave",  avg_review_days=3.1, stddev=0.9),
    TeamMember(id="eng_eve",   avg_review_days=4.5, stddev=1.8),   # slow on reviews
    TeamMember(id="eng_frank", avg_review_days=2.0, stddev=0.6),
]

COMPONENTS = [
    Component(name="payments",  blocker_rate=0.60, common_blocker="review_bottleneck"),
    Component(name="auth",      blocker_rate=0.40, common_blocker="unclear_requirements"),
    Component(name="api",       blocker_rate=0.25, common_blocker="scope_creep"),
    Component(name="dashboard", blocker_rate=0.10, common_blocker="none"),
    Component(name="infra",     blocker_rate=0.30, common_blocker="dependency_block"),
]
```

### Dataset targets

| Dataset | Volume | Purpose |
|---|---|---|
| Historical PRData records | 220–250 | p85 baseline per author + file |
| Historical InsightPayload records | 50–60 | Recurrence detection per component |
| Primary input scenarios | 15–20 | Eval dataset + demo cases |
| Gold-labeled outputs | 15–20 | Eval ground truth |

### Generation script

`fixtures/generate.py` produces all records from personas + components. Outputs:

- `fixtures/history/prs.json` — historical PR records with embeddings pre-computed
- `fixtures/history/insights.json` — past InsightPayload records
- `fixtures/scenarios/` — 15–20 labeled primary input scenarios
- `fixtures/seed_db.py` — loads all history into pgvector + Postgres

**Replay mode:** `python fixtures/seed_db.py` spins up a fully populated local environment
with no external API calls. Every eval, demo, and CI run uses this.

### 3 polished demo scenarios (always fixture-backed)

| # | Scenario | Expected output |
|---|---|---|
| 1 | PR open 9 days, `payments/`, eng_bob as reviewer, Slack has "waiting on Bob" | `review_bottleneck`, severity 4, owner=eng_bob, 3rd recurrence |
| 2 | PR diff +800 lines vs ticket estimate of "small change", no Slack | `scope_creep`, severity 3, owner=PR author, no recurrence |
| 3 | PR merged, ticket closed, all signals consistent | `no_issue`, status=no_issue, no owner assigned |

---

## Core data schemas

```python
# schemas/models.py — single source of truth for all types

class SourceType(str, Enum):
    github_pr     = "github_pr"
    jira_ticket   = "jira_ticket"
    slack_thread  = "slack_thread"
    repo_history  = "repo_history"      # reserved for phase 2
    webhook_event = "webhook_event"     # reserved for phase 2

class EvidenceItem(BaseModel):
    source_type: SourceType
    source_id: str
    quote: str
    rationale: str                      # why this quote supports the finding

class PRData(BaseModel):
    pr_id: str
    title: str
    author: str
    changed_files: list[str]
    diff_chunks: list[str]
    review_comments: list[str]
    created_at: datetime
    days_open: int
    diff_line_count: int

class TicketData(BaseModel):
    ticket_id: str
    title: str
    description: str
    status: str
    assignee: str
    component: str
    created_at: datetime
    sprint_name: str | None

class SlackMessage(BaseModel):
    user_id: str
    text: str
    ts: str

class SlackThreadData(BaseModel):
    thread_ts: str
    channel: str
    messages: list[SlackMessage]
    participant_ids: list[str]

class ContextBundle(BaseModel):
    primary_pr: PRData
    primary_ticket: TicketData
    primary_slack: SlackThreadData | None
    baseline_cycle_p85_days: float | None  # None if history too sparse
    recurrence_count: int
    past_insight_summaries: list[str]
    history_sample_size: int               # used for confidence gating

class DivergenceSignals(BaseModel):
    scope_creep_detected: bool
    status_mismatch: bool
    blocker_mentions: list[str]
    stale_review: bool
    stale_review_days: int | None

class InsightPayload(BaseModel):
    # Status — explicit abstention
    status: Literal["insight", "no_issue", "insufficient_evidence"]

    # Only populated when status == "insight"
    blocker_type: Literal[
        "scope_creep", "review_bottleneck",
        "dependency_block", "unclear_requirements", "none"
    ] | None
    severity: int | None                   # 1–5, calibrated against baseline
    owner: str | None                      # None if confidence below threshold
    owner_confidence: float | None         # 0.0–1.0

    # Always populated
    summary: str                           # 1–2 sentence plain English
    recommended_actions: list[str]
    evidence: list[EvidenceItem]
    missing_sources: list[str]            # e.g. ["slack_thread"] if not provided
    confidence: float                      # 0.0–1.0 overall
    recurrence_count: int
    baseline_cycle_p85_days: float | None

# Persistence model
class AnalysisRequest(BaseModel):
    pr_id: str
    ticket_id: str
    slack_thread_id: str | None

class AnalysisRun(BaseModel):
    run_id: str
    request: AnalysisRequest
    status: Literal["pending", "running", "complete", "failed"]
    created_at: datetime
    completed_at: datetime | None
    cost_usd: float | None
    latency_ms: int | None

class ArtifactSnapshot(BaseModel):
    run_id: str
    insight: InsightPayload
    langsmith_trace_url: str | None
```

---

## Abstention and degraded-mode behavior

First-class design requirement, not an afterthought.

| Condition | System behavior |
|---|---|
| History sample size < 5 PRs | `baseline_cycle_p85_days = None`, severity capped at 2 |
| Slack thread not provided | `missing_sources = ["slack_thread"]`, blocker_mentions = [] |
| Overall confidence < 0.5 | `status = "insufficient_evidence"`, owner = None |
| No divergence signals detected | `status = "no_issue"`, no owner or severity assigned |
| Jira and PR contradict but evidence weak | `status = "insufficient_evidence"`, summary explains contradiction |
| PR merged + ticket closed, all consistent | `status = "no_issue"` |

Owner assignment rule: `owner` is only populated when `owner_confidence >= 0.65`.
Severity reflects delivery risk, not people judgment.
Low-confidence outputs abstain rather than speculate.

---

## LangGraph agent

### State

```python
class AgentState(TypedDict):
    request: AnalysisRequest
    pr_data: PRData | None
    ticket_data: TicketData | None
    slack_data: SlackThreadData | None
    context_bundle: ContextBundle | None
    divergence_signals: DivergenceSignals | None
    insight: InsightPayload | None
    error: str | None
    cost_usd: float
    latency_ms: int
```

### Four nodes (2 deterministic, 2 LLM)

**Node 1 — `extract` (deterministic)**
Calls fixture-backed adapters. Normalizes to typed dataclasses. No LLM. Fully unit-testable.
Fails fast with clear error if primary inputs are missing or malformed.

**Node 2 — `assemble` (deterministic + retrieval)**
Runs pgvector queries for baseline cycle time and past insights.
Computes `baseline_cycle_p85_days` and `recurrence_count`.
Enforces token budget: primary inputs first, retrieved context second.
Max 80k tokens to Claude total.

**Node 3 — `hypothesize` (LLM)**
Focused prompt: given normalized inputs + context bundle, identify specific divergence signals.
Returns `DivergenceSignals`. Does not produce recommendations — only detects signals.
Cheaper, faster call. Low temperature.

**Node 4 — `synthesize_and_gate` (LLM + confidence gate)**
Receives divergence signals + full context bundle.
Produces `InsightPayload` via Claude tool use (typed schema enforced — never parse free text).
Applies confidence gate: if `confidence < 0.5`, sets `status = "insufficient_evidence"`.
Applies owner gate: if `owner_confidence < 0.65`, sets `owner = None`.
Records cost and latency to state.

### Graph definition

```python
graph = StateGraph(AgentState)
graph.add_node("extract", extract_node)
graph.add_node("assemble", assemble_node)
graph.add_node("hypothesize", hypothesize_node)
graph.add_node("synthesize_and_gate", synthesize_and_gate_node)

graph.set_entry_point("extract")
graph.add_edge("extract", "assemble")
graph.add_edge("assemble", "hypothesize")
graph.add_edge("hypothesize", "synthesize_and_gate")
graph.set_finish_point("synthesize_and_gate")
```

---

## SignalExtractor interface (extensibility stub)

Define now so phase 2 integrations slot in without schema changes.

```python
class SignalExtractor(ABC):
    source_type: SourceType

    @abstractmethod
    async def extract(self, source_id: str) -> PRData | TicketData | SlackThreadData:
        ...

# Phase 1 implementations (fixture-backed)
class GitHubPRExtractor(SignalExtractor):
    source_type = SourceType.github_pr

class JiraTicketExtractor(SignalExtractor):
    source_type = SourceType.jira_ticket

class SlackThreadExtractor(SignalExtractor):
    source_type = SourceType.slack_thread

# Phase 2 stubs — not implemented in MVP
# class RepoHistoryExtractor(SignalExtractor): ...
# class WebhookEventExtractor(SignalExtractor): ...
```

---

## Eval harness

Build this before calling the pipeline "done."

```python
# evals/dataset.py — example case structure
{
    "id": "eval_001",
    "scenario": "fixtures/scenarios/001_review_bottleneck.json",
    "expected_status": "insight",
    "expected_blocker_type": "review_bottleneck",
    "expected_severity_min": 3,
    "expected_owner": "eng_bob",
    "expected_recurrence_min": 2,
    "notes": "eng_bob p85 cycle is 6.2 days, history sample >= 10"
}
```

### Metrics

| Metric | Target |
|---|---|
| Blocker type accuracy | >= 80% |
| False positive rate | <= 15% |
| False negative rate | <= 20% |
| Severity within ±1 | >= 85% |
| Abstention correct rate | >= 90% |
| Owner assignment precision | >= 75% |

Run with: `python -m backend.evals.runner`
Outputs: `evals/reports/latest.json` with per-case results + aggregate metrics.
Commit this report to the repo — it should be visible to any reviewer.

---

## Project structure

```
/
├── CLAUDE.md
├── pyproject.toml
├── .env.example
│
├── fixtures/
│   ├── personas.py                  # TeamMember + Component definitions
│   ├── generate.py                  # Generates all synthetic data
│   ├── seed_db.py                   # Loads history into pgvector + Postgres
│   ├── history/
│   │   ├── prs.json                 # 220-250 historical PRData records
│   │   └── insights.json            # 50-60 historical InsightPayload records
│   └── scenarios/
│       ├── 001_review_bottleneck.json
│       ├── 002_scope_creep.json
│       ├── 003_no_issue.json
│       └── ...                      # 15-20 labeled scenarios with gold outputs
│
├── backend/
│   ├── main.py                      # FastAPI app
│   ├── adapters/
│   │   ├── base.py                  # SignalExtractor ABC
│   │   ├── github.py                # GitHubPRExtractor (fixture-backed in MVP)
│   │   ├── jira.py                  # JiraTicketExtractor (fixture-backed in MVP)
│   │   └── slack.py                 # SlackThreadExtractor (fixture-backed in MVP)
│   ├── context/
│   │   ├── assembly.py              # Context builder + pgvector queries
│   │   └── embeddings.py            # Embed + store helpers
│   ├── agent/
│   │   ├── graph.py                 # LangGraph graph definition
│   │   ├── nodes.py                 # All four nodes
│   │   ├── state.py                 # AgentState TypedDict
│   │   └── prompts.py               # All prompts, versioned with comments
│   ├── schemas/
│   │   └── models.py                # Single source of truth for all types
│   └── evals/
│       ├── dataset.py               # Labeled test cases
│       ├── runner.py                # Eval harness
│       ├── scorers.py               # Per-metric scoring functions
│       └── reports/
│           └── latest.json          # Committed eval results
│
├── frontend/
│   └── app/
│       └── result/[run_id]/
│           └── page.tsx             # InsightPayload card + LangSmith trace link
│
└── db/
    └── migrations/
        └── 001_init.sql             # pgvector extension + analysis_runs table
```

---

## Coding conventions

- All Pydantic models live in `schemas/models.py` — never define schemas inline
- All prompts live in `agent/prompts.py` with a version comment — never inline strings
- Every LangGraph node is decorated with `@traceable` for LangSmith
- Never parse LLM free-form text — always use Claude tool use with typed schema
- Adapters are pure functions, no side effects, fully testable without mocking LLMs
- Token budget enforced in `context/assembly.py` before any LLM call — not inside nodes
- `owner` is never assigned when `owner_confidence < 0.65`
- `status = "insufficient_evidence"` when `confidence < 0.5` — never speculate
- Write-back only on `insight.status == "insight"` and `insight.confidence >= 0.7` — never index low-confidence outputs into pgvector

---

## Build order

1. `fixtures/personas.py` + `fixtures/generate.py` — synthetic data first, everything depends on it
2. `fixtures/seed_db.py` + `db/migrations/001_init.sql` — pgvector running with seeded data
3. `schemas/models.py` — all Pydantic types, SourceType enum, SignalExtractor ABC
4. `adapters/` — fixture-backed adapters, unit-tested against scenario files
5. `context/embeddings.py` + `context/assembly.py` — retrieval queries against seeded pgvector
6. `agent/state.py` + `agent/nodes.py` — nodes with mocked LLM calls initially
7. `agent/graph.py` — wire the graph, test deterministic nodes end-to-end
8. `agent/prompts.py` + real Claude calls — replace mocks, enforce tool use schema
9. `evals/` — build dataset + runner, run against all 15-20 scenarios, commit report
10. `backend/main.py` — FastAPI endpoints with AnalysisRun persistence
11. `frontend/` — results page last

---

## Deferred to phase 2

- Live GitHub / Jira / Slack API calls (replace fixture adapters)
- Webhook ingestion + event-driven re-analysis
- Sprint velocity signals
- RepoHistoryExtractor + WebhookEventExtractor implementations
- Multi-workspace support
- Full dashboard beyond the results card
- Cross-platform identity resolution (GitHub username ↔ Jira assignee ↔ Slack user ID mapping)
- Webhook-driven re-analysis on PR update / ticket status change

---

## Environment variables

```
ANTHROPIC_API_KEY=
DATABASE_URL=postgresql://localhost:5432/devplatform
LANGCHAIN_API_KEY=
LANGCHAIN_TRACING_V2=true
LANGCHAIN_PROJECT=dev-productivity-platform

# Phase 2 — not needed for MVP
# GITHUB_TOKEN=
# JIRA_BASE_URL=
# JIRA_EMAIL=
# JIRA_API_TOKEN=
# SLACK_BOT_TOKEN=
```
