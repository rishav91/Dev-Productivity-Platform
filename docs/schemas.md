# Data Schemas

All types live in `backend/schemas/models.py` — never defined inline elsewhere.

## Input types

```
PRData          ← from GitHub adapter
TicketData      ← from Jira adapter
SlackThreadData ← from Slack adapter (optional)
```

## Pipeline types

```
ContextBundle       ← assembled by assemble node; carries retrieval results
DivergenceSignals   ← produced by hypothesize node
InsightPayload      ← final output of synthesize_and_gate
```

## Persistence types

```
AnalysisRequest     ← API input (pr_id, ticket_id, slack_thread_id?)
AnalysisRun         ← run record stored in Postgres
ArtifactSnapshot    ← insight + LangSmith trace URL
```

---

## InsightPayload

The core output type. Three possible statuses:

| `status` | Meaning |
|---|---|
| `insight` | Divergence detected with sufficient confidence |
| `no_issue` | Signals examined; nothing actionable found |
| `insufficient_evidence` | Evidence present but below confidence threshold — abstains |

`blocker_type`, `severity`, `owner`, and `owner_confidence` are only populated when `status = "insight"`.

`evidence` always contains grounded quotes from source inputs with a `rationale` field explaining why each quote supports the finding. No evidence → no claim.

---

## Confidence gates (hard rules, not prompts)

| Condition | Effect |
|---|---|
| `confidence < 0.5` | `status = "insufficient_evidence"`, regardless of signals |
| `owner_confidence < 0.65` | `owner = null` |
| `history_sample_size < 5` | `baseline_cycle_p85_days = null`, severity capped at 2 |

These are enforced in the `synthesize_and_gate` node after the LLM call — not left to the model.

---

## SourceType enum

```python
class SourceType(str, Enum):
    github_pr     = "github_pr"
    jira_ticket   = "jira_ticket"
    slack_thread  = "slack_thread"
    repo_history  = "repo_history"      # phase 2
    webhook_event = "webhook_event"     # phase 2
```

The `EvidenceItem.source_type` field uses this enum, so every evidence quote is traceable to its origin.
