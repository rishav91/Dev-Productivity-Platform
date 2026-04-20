"""
Per-metric scoring functions.

Each scorer takes an EvalCase and an InsightPayload and returns a score dict.
All scores are 0.0 or 1.0 per case (for aggregate averaging).
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from backend.evals.dataset import EvalCase
from backend.schemas.models import InsightPayload


@dataclass
class CaseResult:
    case_id: str
    scenario_id: str
    description: str
    passed: bool

    expected_status: str
    actual_status: str
    status_match: bool

    expected_blocker_type: str | None
    actual_blocker_type: str | None
    blocker_type_match: bool

    expected_severity_min: int | None
    actual_severity: int | None
    severity_within_1: bool  # actual within ±1 of the min threshold

    expected_owner: str | None
    actual_owner: str | None
    owner_match: bool

    expected_recurrence_min: int
    actual_recurrence: int
    recurrence_ok: bool

    abstention_correct: bool   # True when abstention decision was correct
    confidence: float
    notes: str


def score_case(case: EvalCase, insight: InsightPayload) -> CaseResult:
    status_match = insight.status == case.expected_status

    blocker_match = (
        insight.blocker_type == case.expected_blocker_type
        if case.expected_status == "insight"
        else True  # don't penalize blocker_type when status is already wrong
    )

    # Severity: allow within ±1 of expected minimum
    sev_within_1 = _score_severity(case.expected_severity_min, insight.severity)

    # Owner: exact match or both None
    owner_match = _score_owner(case.expected_owner, insight.owner)

    recurrence_ok = insight.recurrence_count >= case.expected_recurrence_min

    # Abstention: correct when insufficient_evidence maps to a case where we want that,
    # OR when status=no_issue is correctly called for a no-blocker case.
    abstention_correct = _score_abstention(case, insight)

    passed = (
        status_match
        and blocker_match
        and sev_within_1
        and owner_match
        and recurrence_ok
    )

    return CaseResult(
        case_id=case.id,
        scenario_id=case.scenario_id,
        description=case.description,
        passed=passed,
        expected_status=case.expected_status,
        actual_status=insight.status,
        status_match=status_match,
        expected_blocker_type=case.expected_blocker_type,
        actual_blocker_type=insight.blocker_type,
        blocker_type_match=blocker_match,
        expected_severity_min=case.expected_severity_min,
        actual_severity=insight.severity,
        severity_within_1=sev_within_1,
        expected_owner=case.expected_owner,
        actual_owner=insight.owner,
        owner_match=owner_match,
        expected_recurrence_min=case.expected_recurrence_min,
        actual_recurrence=insight.recurrence_count,
        recurrence_ok=recurrence_ok,
        abstention_correct=abstention_correct,
        confidence=insight.confidence,
        notes=case.notes,
    )


def _score_severity(expected_min: int | None, actual: int | None) -> bool:
    if expected_min is None:
        # No severity expected — pass if no severity assigned
        return actual is None
    if actual is None:
        return False
    # Allow within ±1 of the minimum threshold
    return abs(actual - expected_min) <= 1


def _score_owner(expected: str | None, actual: str | None) -> bool:
    if expected is None:
        # No specific owner expected — pass whether or not one was assigned
        return True
    return expected == actual


def _score_abstention(case: EvalCase, insight: InsightPayload) -> bool:
    """Abstention is correct when:
    - Expected no_issue and got no_issue
    - Expected insufficient_evidence and got insufficient_evidence
    - Expected insight and got insight (not abstaining when evidence exists)
    """
    return insight.status == case.expected_status


@dataclass
class AggregateMetrics:
    total_cases: int
    passed: int
    pass_rate: float

    blocker_type_accuracy: float    # target >= 80%
    false_positive_rate: float      # target <= 15%
    false_negative_rate: float      # target <= 20%
    severity_within_1_rate: float   # target >= 85%
    abstention_correct_rate: float  # target >= 90%
    owner_precision: float          # target >= 75%

    per_case: list[dict]


def compute_metrics(results: list[CaseResult]) -> AggregateMetrics:
    n = len(results)
    if n == 0:
        raise ValueError("No results to compute metrics from")

    insight_cases = [r for r in results if r.expected_status == "insight"]
    no_blocker_cases = [r for r in results if r.expected_status in ("no_issue", "insufficient_evidence")]

    # False positive: predicted insight when truth is no_issue/insufficient_evidence
    fp_count = sum(1 for r in no_blocker_cases if r.actual_status == "insight")
    fp_rate = fp_count / len(no_blocker_cases) if no_blocker_cases else 0.0

    # False negative: predicted no_issue/insufficient_evidence when truth is insight
    fn_count = sum(1 for r in insight_cases if r.actual_status != "insight")
    fn_rate = fn_count / len(insight_cases) if insight_cases else 0.0

    # Blocker type accuracy — only on cases where we expected insight
    blocker_acc = (
        sum(1 for r in insight_cases if r.blocker_type_match) / len(insight_cases)
        if insight_cases else 1.0
    )

    # Severity within ±1 — only on cases with expected severity
    sev_cases = [r for r in insight_cases if r.expected_severity_min is not None]
    sev_rate = (
        sum(1 for r in sev_cases if r.severity_within_1) / len(sev_cases)
        if sev_cases else 1.0
    )

    abstention_rate = sum(1 for r in results if r.abstention_correct) / n

    # Owner precision — only on cases where a specific owner was expected
    owner_cases = [r for r in insight_cases if r.expected_owner is not None]
    owner_precision = (
        sum(1 for r in owner_cases if r.owner_match) / len(owner_cases)
        if owner_cases else 1.0
    )

    passed = sum(1 for r in results if r.passed)

    return AggregateMetrics(
        total_cases=n,
        passed=passed,
        pass_rate=passed / n,
        blocker_type_accuracy=blocker_acc,
        false_positive_rate=fp_rate,
        false_negative_rate=fn_rate,
        severity_within_1_rate=sev_rate,
        abstention_correct_rate=abstention_rate,
        owner_precision=owner_precision,
        per_case=[_case_to_dict(r) for r in results],
    )


def _case_to_dict(r: CaseResult) -> dict:
    return {
        "case_id": r.case_id,
        "scenario_id": r.scenario_id,
        "description": r.description,
        "passed": r.passed,
        "status_match": r.status_match,
        "blocker_type_match": r.blocker_type_match,
        "severity_within_1": r.severity_within_1,
        "owner_match": r.owner_match,
        "recurrence_ok": r.recurrence_ok,
        "abstention_correct": r.abstention_correct,
        "confidence": r.confidence,
        "expected": {
            "status": r.expected_status,
            "blocker_type": r.expected_blocker_type,
            "severity_min": r.expected_severity_min,
            "owner": r.expected_owner,
        },
        "actual": {
            "status": r.actual_status,
            "blocker_type": r.actual_blocker_type,
            "severity": r.actual_severity,
            "owner": r.actual_owner,
            "recurrence_count": r.actual_recurrence,
        },
        "notes": r.notes,
    }
