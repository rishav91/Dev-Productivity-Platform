"""
Labeled eval dataset — one entry per scenario file.
Each case describes what output to expect so scorers can compare against actual output.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Literal

SCENARIOS_DIR = Path(__file__).parent.parent.parent / "fixtures" / "scenarios"


@dataclass
class EvalCase:
    id: str
    scenario_id: str                            # maps to fixtures/scenarios/<id>_scenario.json
    description: str

    # Expected outputs (gold labels)
    expected_status: Literal["insight", "no_issue", "insufficient_evidence"]
    expected_blocker_type: str | None = None    # None for no_issue / insufficient_evidence
    expected_severity_min: int | None = None    # insight must have severity >= this
    expected_owner: str | None = None           # None means owner should be unset
    expected_recurrence_min: int = 0            # recurrence_count must be >= this
    notes: str = ""


# ---------------------------------------------------------------------------
# Gold-labeled cases for the 3 polished demo scenarios
# ---------------------------------------------------------------------------

EVAL_DATASET: list[EvalCase] = [
    EvalCase(
        id="eval_001",
        scenario_id="001",
        description="Review bottleneck in payments/ — eng_bob blocking",
        expected_status="insight",
        expected_blocker_type="review_bottleneck",
        expected_severity_min=3,
        expected_owner="eng_bob",
        expected_recurrence_min=2,
        notes="eng_bob p85 cycle is 6.2 days, PR at 9 days is above p85. "
              "Slack explicitly mentions 'waiting on Bob'.",
    ),
    EvalCase(
        id="eval_002",
        scenario_id="002",
        description="Scope creep in api/ — 847 lines vs 'small change' estimate",
        expected_status="insight",
        expected_blocker_type="scope_creep",
        expected_severity_min=3,
        expected_owner="eng_frank",
        expected_recurrence_min=0,
        notes="Ticket says '2-3 hours / small change', PR diff is 847 lines. No Slack.",
    ),
    EvalCase(
        id="eval_003",
        scenario_id="003",
        description="No issue — PR merged in 2 days, ticket done",
        expected_status="no_issue",
        expected_blocker_type=None,
        expected_severity_min=None,
        expected_owner=None,
        expected_recurrence_min=0,
        notes="Dashboard PR, 2 days, merged, ticket closed. No signals.",
    ),
    EvalCase(
        id="eval_004",
        scenario_id="004",
        description="Dependency block in infra/ — waiting on networking team",
        expected_status="insight",
        expected_blocker_type="dependency_block",
        expected_severity_min=2,
        expected_owner=None,  # owner less certain here
        expected_recurrence_min=0,
        notes="Ticket status=Blocked, Slack mentions 'next week earliest'.",
    ),
    EvalCase(
        id="eval_005",
        scenario_id="005",
        description="Unclear requirements in auth/ — TBD on isolation approach",
        expected_status="insight",
        expected_blocker_type="unclear_requirements",
        expected_severity_min=2,
        expected_owner=None,
        expected_recurrence_min=0,
        notes="Ticket description says 'TBD on isolation approach', reviewer also flags vagueness.",
    ),
    EvalCase(
        id="eval_006",
        scenario_id="006",
        description="Trivial change — no issue expected",
        expected_status="no_issue",
        expected_blocker_type=None,
        expected_severity_min=None,
        expected_owner=None,
        expected_recurrence_min=0,
        notes="3-line config change, 1 day open, no review comments, no Slack.",
    ),
]


def load_scenario_for_case(case: EvalCase) -> dict:
    """Load the raw scenario JSON for an eval case."""
    import json

    for path in SCENARIOS_DIR.glob("*.json"):
        data = json.loads(path.read_text())
        if data.get("scenario_id") == case.scenario_id:
            return data

    raise FileNotFoundError(
        f"Scenario {case.scenario_id!r} not found in {SCENARIOS_DIR}. "
        "Run: python fixtures/generate.py"
    )
