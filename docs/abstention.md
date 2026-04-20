# Abstention & Degraded-Mode Behavior

Abstention is a first-class design requirement. The system explicitly signals what it doesn't know rather than speculating.

## Abstention rules

| Condition | Behavior |
|---|---|
| `confidence < 0.5` | `status = "insufficient_evidence"`, `owner = null` |
| `owner_confidence < 0.65` | `owner = null` even if status is `"insight"` |
| `history_sample_size < 5` | `baseline_cycle_p85_days = null`, severity capped at 2 |
| No divergence signals | `status = "no_issue"`, no owner or severity |
| Slack thread not provided | `missing_sources = ["slack_thread"]`, `blocker_mentions = []` |
| Contradictory signals, weak evidence | `status = "insufficient_evidence"`, summary explains the contradiction |
| PR merged + ticket closed, consistent | `status = "no_issue"` |

## Why this matters

A system that always produces confident-sounding output is not trustworthy. The confidence gate (`< 0.5 → abstain`) and the owner gate (`owner_confidence < 0.65 → owner = null`) are enforced in code after the LLM call — not left to the model's discretion.

`missing_sources` is always populated when an optional input wasn't provided, so callers know *why* a finding is absent rather than inferring it from a null field.

## Degraded mode example

If Slack is not provided and history is sparse:

```json
{
  "status": "insufficient_evidence",
  "summary": "PR has been open 4 days, but review cycle baseline is unavailable (fewer than 5 historical PRs for this author). No Slack thread provided.",
  "missing_sources": ["slack_thread"],
  "confidence": 0.35,
  "baseline_cycle_p85_days": null,
  "recurrence_count": 0,
  "owner": null,
  "severity": null
}
```

The response is still useful — it tells the caller exactly what's missing and why no insight was produced.
