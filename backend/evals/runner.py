"""
Eval harness — runs all labeled cases through the graph and writes a report.

Usage: python -m backend.evals.runner

Outputs: backend/evals/reports/latest.json
"""
from __future__ import annotations

import asyncio
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from dotenv import load_dotenv

load_dotenv()

import asyncpg

from backend.agent.graph import run_analysis
from backend.evals.dataset import EVAL_DATASET, EvalCase, load_scenario_for_case
from backend.evals.scorers import AggregateMetrics, CaseResult, compute_metrics, score_case
from backend.schemas.models import AnalysisRequest, InsightPayload

REPORTS_DIR = Path(__file__).parent / "reports"
TARGETS = {
    "blocker_type_accuracy": 0.80,
    "false_positive_rate": 0.15,   # lower is better
    "false_negative_rate": 0.20,   # lower is better
    "severity_within_1_rate": 0.85,
    "abstention_correct_rate": 0.90,
    "owner_precision": 0.75,
}


async def run_case(
    case: EvalCase,
    conn: asyncpg.Connection,
) -> CaseResult | None:
    """Run a single eval case through the graph. Returns None on graph failure."""
    try:
        scenario = load_scenario_for_case(case)
    except FileNotFoundError as e:
        print(f"  [SKIP] {case.id}: {e}")
        return None

    request = AnalysisRequest(
        pr_id=case.scenario_id,  # adapters look up by scenario_id
        ticket_id=case.scenario_id,
        slack_thread_id=case.scenario_id if scenario.get("slack") else None,
    )

    print(f"  Running {case.id} ({case.description})...")
    run, snapshot = await run_analysis(request=request, conn=conn)

    if snapshot is None:
        print(f"  [FAIL] {case.id}: graph returned no snapshot")
        # Return a worst-case result for scoring
        dummy = InsightPayload(
            status="insufficient_evidence",
            summary="Graph failed to produce output.",
            recommended_actions=[],
            evidence=[],
            missing_sources=[],
            confidence=0.0,
            recurrence_count=0,
            baseline_cycle_p85_days=None,
        )
        return score_case(case, dummy)

    return score_case(case, snapshot.insight)


async def main() -> None:
    print("Starting eval run...\n")

    db_url = os.environ["DATABASE_URL"].replace("postgresql://", "")
    conn: asyncpg.Connection = await asyncpg.connect(f"postgresql://{db_url}")

    results: list[CaseResult] = []

    try:
        for case in EVAL_DATASET:
            result = await run_case(case, conn)
            if result is not None:
                results.append(result)
                status = "PASS" if result.passed else "FAIL"
                print(f"  [{status}] {case.id} — status={result.actual_status} "
                      f"blocker={result.actual_blocker_type} conf={result.confidence:.2f}")
    finally:
        await conn.close()

    if not results:
        print("\nNo results — check fixture generation and database seeding.")
        return

    metrics = compute_metrics(results)
    _print_summary(metrics)

    report = {
        "run_at": datetime.now(tz=timezone.utc).isoformat(),
        "total_cases": metrics.total_cases,
        "passed": metrics.passed,
        "pass_rate": round(metrics.pass_rate, 3),
        "metrics": {
            "blocker_type_accuracy": round(metrics.blocker_type_accuracy, 3),
            "false_positive_rate": round(metrics.false_positive_rate, 3),
            "false_negative_rate": round(metrics.false_negative_rate, 3),
            "severity_within_1_rate": round(metrics.severity_within_1_rate, 3),
            "abstention_correct_rate": round(metrics.abstention_correct_rate, 3),
            "owner_precision": round(metrics.owner_precision, 3),
        },
        "targets": TARGETS,
        "targets_met": _check_targets(metrics),
        "per_case": metrics.per_case,
    }

    REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    report_path = REPORTS_DIR / "latest.json"
    report_path.write_text(json.dumps(report, indent=2))
    print(f"\nReport written → {report_path}")


def _print_summary(m: AggregateMetrics) -> None:
    print("\n" + "=" * 60)
    print(f"EVAL RESULTS: {m.passed}/{m.total_cases} cases passed ({m.pass_rate:.0%})")
    print("=" * 60)

    rows = [
        ("Blocker type accuracy", m.blocker_type_accuracy, TARGETS["blocker_type_accuracy"], True),
        ("False positive rate", m.false_positive_rate, TARGETS["false_positive_rate"], False),
        ("False negative rate", m.false_negative_rate, TARGETS["false_negative_rate"], False),
        ("Severity within ±1", m.severity_within_1_rate, TARGETS["severity_within_1_rate"], True),
        ("Abstention correct", m.abstention_correct_rate, TARGETS["abstention_correct_rate"], True),
        ("Owner precision", m.owner_precision, TARGETS["owner_precision"], True),
    ]

    for label, value, target, higher_is_better in rows:
        if higher_is_better:
            ok = value >= target
        else:
            ok = value <= target
        marker = "✓" if ok else "✗"
        print(f"  {marker} {label:<28} {value:.1%}  (target: {'>=' if higher_is_better else '<='}{target:.0%})")

    print()


def _check_targets(m: AggregateMetrics) -> dict[str, bool]:
    return {
        "blocker_type_accuracy": m.blocker_type_accuracy >= TARGETS["blocker_type_accuracy"],
        "false_positive_rate": m.false_positive_rate <= TARGETS["false_positive_rate"],
        "false_negative_rate": m.false_negative_rate <= TARGETS["false_negative_rate"],
        "severity_within_1_rate": m.severity_within_1_rate >= TARGETS["severity_within_1_rate"],
        "abstention_correct_rate": m.abstention_correct_rate >= TARGETS["abstention_correct_rate"],
        "owner_precision": m.owner_precision >= TARGETS["owner_precision"],
    }


if __name__ == "__main__":
    asyncio.run(main())
