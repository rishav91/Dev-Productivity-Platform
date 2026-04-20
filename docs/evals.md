# Eval Harness

## Running

```bash
python -m backend.evals.runner
# outputs: backend/evals/reports/latest.json
```

The runner loads scenarios from `fixtures/scenarios/`, runs the full agent pipeline against each, and scores the result against gold labels in `backend/evals/dataset.py`.

---

## Metrics & targets

| Metric | Target | Latest |
|---|---|---|
| Blocker type accuracy | ≥ 80% | **100%** ✓ |
| False positive rate | ≤ 15% | **0%** ✓ |
| False negative rate | ≤ 20% | **0%** ✓ |
| Severity within ±1 | ≥ 85% | **50%** ✗ |
| Abstention correct rate | ≥ 90% | **100%** ✓ |
| Owner assignment precision | ≥ 75% | **100%** ✓ |

The severity gap is the main open issue — the model tends toward severity 4–5 in ambiguous cases where the expected value is lower. Improving baseline calibration signal in the context bundle is the likely fix.

---

## Scenario coverage

Three demo scenarios are always included and manually verified:

| Scenario | Expected output |
|---|---|
| PR open 9 days, `payments/`, eng_bob as reviewer, Slack: "waiting on Bob" | `review_bottleneck`, severity 4, owner=eng_bob, 3rd recurrence |
| PR diff +800 lines vs ticket estimate "small change", no Slack | `scope_creep`, severity 3, owner=PR author, no recurrence |
| PR merged, ticket closed, all signals consistent | `no_issue`, no owner or severity |

Full scenario files: `fixtures/scenarios/`

---

## Eval case structure

```json
{
  "id": "eval_001",
  "scenario": "fixtures/scenarios/001_scenario.json",
  "expected_status": "insight",
  "expected_blocker_type": "review_bottleneck",
  "expected_severity_min": 3,
  "expected_owner": "eng_bob",
  "expected_recurrence_min": 2
}
```

A case **passes** only when all five dimensions match (status, blocker type, severity within ±1, owner, recurrence ≥ min). A correct blocker type with a wrong severity is a partial success in the metrics but a failed case overall.

---

## Committed report

`backend/evals/reports/latest.json` is committed to the repo. Any reviewer can see the current eval state without running the pipeline.
