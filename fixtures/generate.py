"""
Generates all synthetic fixture data from team personas + component definitions.

Outputs:
  fixtures/history/prs.json       — 220-250 historical PRData records
  fixtures/history/insights.json  — 50-60 historical InsightPayload records
  fixtures/scenarios/             — 15-20 labeled primary input scenarios

Run: python fixtures/generate.py
"""
from __future__ import annotations

import json
import random
import sys
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

import numpy as np

# Allow imports from project root
sys.path.insert(0, str(Path(__file__).parent.parent))

from fixtures.personas import (
    COMPONENT_FILES,
    COMPONENT_REVIEWERS,
    COMPONENTS,
    TEAM_MEMBER_IDS,
    TEAM_PERSONAS,
    Component,
    TeamMember,
)

SEED = 42
rng = random.Random(SEED)
np_rng = np.random.default_rng(SEED)

NOW = datetime(2026, 4, 19, tzinfo=timezone.utc)
HISTORY_WINDOW_DAYS = 180  # generate history over past 6 months


def _rand_date(days_back_max: int = HISTORY_WINDOW_DAYS) -> datetime:
    delta = timedelta(days=rng.randint(1, days_back_max))
    return NOW - delta


def _sample_cycle_days(member: TeamMember) -> float:
    """Sample a review cycle time from member's distribution, clamped to [0.5, 20]."""
    raw = np_rng.normal(member.avg_review_days, member.stddev)
    return float(np.clip(raw, 0.5, 20.0))


def _sample_files(component_name: str, n: int = None) -> list[str]:
    files = COMPONENT_FILES[component_name]
    k = n or rng.randint(1, min(4, len(files)))
    return rng.sample(files, k)


def _pr_title(component_name: str, diff_size: str) -> str:
    templates = {
        "payments": [
            "Fix payment processor retry logic",
            "Add webhook signature validation",
            "Refactor payment models for new schema",
            "Update payment validator edge cases",
        ],
        "auth": [
            "Add OAuth2 PKCE support",
            "Fix token refresh race condition",
            "Refactor permissions middleware",
            "Update auth models for multi-tenant",
        ],
        "api": [
            "Add pagination to list endpoints",
            "Fix throttling for burst requests",
            "Refactor route handlers",
            "Update serializers for v2 schema",
        ],
        "dashboard": [
            "Add new chart component",
            "Fix filter state bug",
            "Refactor dashboard views",
            "Update dashboard tests",
        ],
        "infra": [
            "Update Kubernetes deployment config",
            "Add monitoring alerts for latency",
            "Fix Terraform variable references",
            "Refactor deploy pipeline",
        ],
    }
    return rng.choice(templates.get(component_name, ["Miscellaneous change"]))


def generate_pr_history(target: int = 235) -> list[dict[str, Any]]:
    """Generate 220-250 historical PRData records with realistic distributions."""
    records = []
    component_lookup = {c.name: c for c in COMPONENTS}
    member_lookup = {m.id: m for m in TEAM_PERSONAS}

    for i in range(target):
        component: Component = rng.choice(COMPONENTS)
        author_id: str = rng.choice(TEAM_MEMBER_IDS)
        author: TeamMember = member_lookup[author_id]

        cycle_days = _sample_cycle_days(author)
        days_open = max(1, int(round(cycle_days)))

        # Diff size: small (50-200), medium (200-600), large (600-1500)
        size_bucket = rng.choices(["small", "medium", "large"], weights=[0.5, 0.35, 0.15])[0]
        diff_line_count = {
            "small": rng.randint(50, 200),
            "medium": rng.randint(200, 600),
            "large": rng.randint(600, 1500),
        }[size_bucket]

        changed_files = _sample_files(component.name)
        created_at = _rand_date()

        reviewer = rng.choice(COMPONENT_REVIEWERS.get(component.name, TEAM_MEMBER_IDS))
        review_comments = _generate_review_comments(component.name, days_open, reviewer)

        records.append({
            "pr_id": f"PR-{1000 + i}",
            "title": _pr_title(component.name, size_bucket),
            "author": author_id,
            "changed_files": changed_files,
            "diff_chunks": [f"# diff chunk for {f}" for f in changed_files],
            "review_comments": review_comments,
            "created_at": created_at.isoformat(),
            "days_open": days_open,
            "diff_line_count": diff_line_count,
            # Extra metadata for retrieval — not in PRData schema but useful for seeding
            "_component": component.name,
            "_reviewer": reviewer,
            "_cycle_days": round(cycle_days, 2),
        })

    return records


def _generate_review_comments(component: str, days_open: int, reviewer: str) -> list[str]:
    comments = []
    if days_open > 5:
        comments.append(f"@{reviewer} can you take a look at this?")
    if days_open > 8:
        comments.append("Bumping this — been open a while")
    if component == "payments":
        comments.append("Needs security review before merge")
    if rng.random() < 0.4:
        comments.append("LGTM, minor nits inline")
    return comments


def generate_insight_history(target: int = 55) -> list[dict[str, Any]]:
    """Generate 50-60 historical InsightPayload records for recurrence detection."""
    records = []
    blocker_types = ["scope_creep", "review_bottleneck", "dependency_block", "unclear_requirements"]

    for i in range(target):
        component: Component = rng.choice(COMPONENTS)
        has_blocker = rng.random() < component.blocker_rate
        blocker_type = component.common_blocker if has_blocker else "none"
        severity = rng.randint(2, 5) if has_blocker else rng.randint(1, 2)
        confidence = round(rng.uniform(0.65, 0.95) if has_blocker else rng.uniform(0.5, 0.8), 3)
        owner_id = rng.choice(TEAM_MEMBER_IDS) if has_blocker and rng.random() > 0.3 else None
        created_at = _rand_date()

        records.append({
            "insight_id": f"INS-{2000 + i}",
            "component": component.name,
            "blocker_type": blocker_type if blocker_type != "none" else None,
            "severity": severity if has_blocker else None,
            "owner": owner_id,
            "owner_confidence": round(rng.uniform(0.65, 0.95), 3) if owner_id else None,
            "status": "insight" if has_blocker else "no_issue",
            "summary": _insight_summary(component.name, blocker_type, severity if has_blocker else 1),
            "recommended_actions": _recommended_actions(blocker_type),
            "evidence": [],
            "missing_sources": [],
            "confidence": confidence,
            "recurrence_count": rng.randint(0, 3),
            "baseline_cycle_p85_days": round(rng.uniform(3.0, 8.0), 1),
            "created_at": created_at.isoformat(),
        })

    return records


def _insight_summary(component: str, blocker_type: str, severity: int) -> str:
    if blocker_type == "review_bottleneck":
        return f"PR in {component}/ has been awaiting review for an extended period, severity {severity}/5."
    if blocker_type == "scope_creep":
        return f"Diff in {component}/ significantly exceeds ticket estimate, indicating scope creep."
    if blocker_type == "dependency_block":
        return f"PR in {component}/ is blocked on an external dependency resolution."
    if blocker_type == "unclear_requirements":
        return f"Ticket for {component}/ lacks sufficient acceptance criteria for implementation."
    return f"No delivery blocker detected for this {component}/ change."


def _recommended_actions(blocker_type: str) -> list[str]:
    actions = {
        "review_bottleneck": [
            "Assign a backup reviewer to unblock the PR",
            "Add this reviewer to the sprint retrospective discussion",
        ],
        "scope_creep": [
            "Split the PR into smaller focused changes",
            "Update the ticket with revised estimate",
        ],
        "dependency_block": [
            "Escalate dependency to owning team with deadline",
            "Evaluate if the PR can be scoped to avoid the dependency",
        ],
        "unclear_requirements": [
            "Schedule a requirements clarification session with PM",
            "Document agreed acceptance criteria in the ticket",
        ],
        "none": ["No action required — delivery is on track"],
    }
    return actions.get(blocker_type, ["No action required"])


# ---------------------------------------------------------------------------
# Demo scenarios (polished, fixture-backed, always deterministic)
# ---------------------------------------------------------------------------

def generate_scenarios() -> list[dict[str, Any]]:
    return [
        _scenario_001_review_bottleneck(),
        _scenario_002_scope_creep(),
        _scenario_003_no_issue(),
        *_scenario_bulk(start_id=4, count=15),
    ]


def _scenario_001_review_bottleneck() -> dict[str, Any]:
    """PR open 9 days, payments/, eng_bob as reviewer, Slack has 'waiting on Bob'."""
    return {
        "scenario_id": "001",
        "description": "Review bottleneck in payments/ — eng_bob blocking",
        "pr": {
            "pr_id": "PR-DEMO-001",
            "title": "Add idempotency keys to payment processor",
            "author": "eng_alice",
            "changed_files": ["payments/processor.py", "payments/models.py"],
            "diff_chunks": [
                "- process_payment(amount, card)\n+ process_payment(amount, card, idempotency_key=None)",
                "+ if idempotency_key:\n+     return check_idempotency_cache(idempotency_key)",
            ],
            "review_comments": [
                "@eng_bob can you review this? It's been sitting for a week",
                "Bumping — this is blocking our Q2 payment reliability initiative",
            ],
            "created_at": (NOW - timedelta(days=9)).isoformat(),
            "days_open": 9,
            "diff_line_count": 145,
        },
        "ticket": {
            "ticket_id": "PROJ-441",
            "title": "Add idempotency to payment processor",
            "description": "Payment processor must support idempotency keys to prevent duplicate charges on retry.",
            "status": "In Progress",
            "assignee": "eng_alice",
            "component": "payments",
            "created_at": (NOW - timedelta(days=12)).isoformat(),
            "sprint_name": "Sprint 24",
        },
        "slack": {
            "thread_ts": "1745000000.000001",
            "channel": "C_PAYMENTS",
            "messages": [
                {"user_id": "eng_alice", "text": "Hey, anyone know when Bob will review PR-DEMO-001?", "ts": "1745000100.000001"},
                {"user_id": "eng_carol", "text": "Yeah we're waiting on Bob, he's been swamped", "ts": "1745000200.000001"},
                {"user_id": "eng_alice", "text": "This is blocking the sprint goal", "ts": "1745000300.000001"},
            ],
            "participant_ids": ["eng_alice", "eng_carol"],
        },
        "gold_output": {
            "status": "insight",
            "blocker_type": "review_bottleneck",
            "expected_severity_min": 3,
            "expected_owner": "eng_bob",
            "expected_recurrence_min": 2,
            "notes": "eng_bob p85 cycle is 6.2 days, PR at 9 days is above p85, history sample >= 10",
        },
    }


def _scenario_002_scope_creep() -> dict[str, Any]:
    """PR diff +800 lines vs ticket estimate of 'small change', no Slack."""
    return {
        "scenario_id": "002",
        "description": "Scope creep in api/ — PR diff far exceeds ticket estimate",
        "pr": {
            "pr_id": "PR-DEMO-002",
            "title": "Update serializers for v2 schema",
            "author": "eng_frank",
            "changed_files": ["api/serializers.py", "api/routes.py", "api/pagination.py", "api/tests/test_routes.py"],
            "diff_chunks": [
                "# Major refactor of serialization layer",
                "# Added 12 new endpoint handlers",
                "# Rewrote pagination logic",
            ],
            "review_comments": [
                "This is much bigger than the ticket described",
                "Should we split this into smaller PRs?",
            ],
            "created_at": (NOW - timedelta(days=3)).isoformat(),
            "days_open": 3,
            "diff_line_count": 847,
        },
        "ticket": {
            "ticket_id": "PROJ-502",
            "title": "Update API serializers for v2 schema",
            "description": "Small change to update serializer field names to match v2 schema. Estimate: 2-3 hours.",
            "status": "In Progress",
            "assignee": "eng_frank",
            "component": "api",
            "created_at": (NOW - timedelta(days=5)).isoformat(),
            "sprint_name": "Sprint 24",
        },
        "slack": None,
        "gold_output": {
            "status": "insight",
            "blocker_type": "scope_creep",
            "expected_severity_min": 3,
            "expected_owner": "eng_frank",
            "expected_recurrence_min": 0,
            "notes": "847 lines vs 'small change' estimate (2-3 hours), no Slack provided",
        },
    }


def _scenario_003_no_issue() -> dict[str, Any]:
    """PR merged, ticket closed, all signals consistent."""
    return {
        "scenario_id": "003",
        "description": "No issue — PR merged, ticket closed, all signals consistent",
        "pr": {
            "pr_id": "PR-DEMO-003",
            "title": "Add filter state persistence to dashboard",
            "author": "eng_carol",
            "changed_files": ["dashboard/filters.py", "dashboard/tests/test_views.py"],
            "diff_chunks": [
                "+ class FilterStateManager:\n+     def persist(self, state): ...",
                "+ def test_filter_persistence(): ...",
            ],
            "review_comments": ["LGTM! Nice clean implementation", "Merged"],
            "created_at": (NOW - timedelta(days=2)).isoformat(),
            "days_open": 2,
            "diff_line_count": 87,
        },
        "ticket": {
            "ticket_id": "PROJ-488",
            "title": "Persist filter state in dashboard",
            "description": "Users should retain their filter selections after page reload.",
            "status": "Done",
            "assignee": "eng_carol",
            "component": "dashboard",
            "created_at": (NOW - timedelta(days=4)).isoformat(),
            "sprint_name": "Sprint 24",
        },
        "slack": None,
        "gold_output": {
            "status": "no_issue",
            "blocker_type": None,
            "expected_severity_min": None,
            "expected_owner": None,
            "expected_recurrence_min": 0,
            "notes": "PR merged in 2 days (well within baseline), ticket closed, no blocker signals",
        },
    }


def _scenario_bulk(start_id: int, count: int) -> list[dict[str, Any]]:
    """Generate additional labeled scenarios covering edge cases and abstention paths."""
    scenarios = []
    edge_cases = [
        # Dependency block in infra
        {
            "scenario_id": f"{start_id:03d}",
            "description": "Dependency block in infra/ — waiting on external team",
            "pr": {
                "pr_id": f"PR-DEMO-{start_id:03d}",
                "title": "Update Terraform to use new VPC module",
                "author": "eng_dave",
                "changed_files": ["infra/terraform/main.tf"],
                "diff_chunks": ["- vpc_module = \"v1.2\"\n+ vpc_module = \"v2.0\""],
                "review_comments": ["Blocked — waiting on networking team to publish v2.0 module"],
                "created_at": (NOW - timedelta(days=5)).isoformat(),
                "days_open": 5,
                "diff_line_count": 23,
            },
            "ticket": {
                "ticket_id": "PROJ-510",
                "title": "Upgrade VPC Terraform module to v2",
                "description": "Upgrade to v2.0 of internal VPC module for improved security groups.",
                "status": "Blocked",
                "assignee": "eng_dave",
                "component": "infra",
                "created_at": (NOW - timedelta(days=7)).isoformat(),
                "sprint_name": "Sprint 24",
            },
            "slack": {
                "thread_ts": "1745001000.000001",
                "channel": "C_INFRA",
                "messages": [
                    {"user_id": "eng_dave", "text": "Still waiting on networking team for VPC v2 module", "ts": "1745001100.000001"},
                    {"user_id": "eng_eve", "text": "They said next week earliest", "ts": "1745001200.000001"},
                ],
                "participant_ids": ["eng_dave", "eng_eve"],
            },
            "gold_output": {
                "status": "insight",
                "blocker_type": "dependency_block",
                "expected_severity_min": 2,
                "expected_owner": "eng_dave",
                "expected_recurrence_min": 0,
                "notes": "Clear dependency block signal in ticket status + Slack",
            },
        },
        # Unclear requirements in auth
        {
            "scenario_id": f"{start_id+1:03d}",
            "description": "Unclear requirements in auth/ — no acceptance criteria",
            "pr": {
                "pr_id": f"PR-DEMO-{start_id+1:03d}",
                "title": "Implement multi-tenant auth middleware",
                "author": "eng_bob",
                "changed_files": ["auth/middleware.py", "auth/models.py"],
                "diff_chunks": ["+ class MultiTenantMiddleware: # TODO: clarify tenant isolation rules"],
                "review_comments": ["What are the isolation requirements here? The ticket is vague"],
                "created_at": (NOW - timedelta(days=4)).isoformat(),
                "days_open": 4,
                "diff_line_count": 210,
            },
            "ticket": {
                "ticket_id": "PROJ-519",
                "title": "Multi-tenant auth support",
                "description": "Support multiple tenants. TBD on isolation approach.",
                "status": "In Progress",
                "assignee": "eng_bob",
                "component": "auth",
                "created_at": (NOW - timedelta(days=6)).isoformat(),
                "sprint_name": "Sprint 24",
            },
            "slack": None,
            "gold_output": {
                "status": "insight",
                "blocker_type": "unclear_requirements",
                "expected_severity_min": 2,
                "expected_owner": None,
                "expected_recurrence_min": 0,
                "notes": "Ticket description is vague (TBD), reviewer also flags in comments",
            },
        },
        # Insufficient evidence (sparse history)
        {
            "scenario_id": f"{start_id+2:03d}",
            "description": "Insufficient evidence — sparse history, weak signals",
            "pr": {
                "pr_id": f"PR-DEMO-{start_id+2:03d}",
                "title": "Minor config update",
                "author": "eng_alice",
                "changed_files": ["api/routes.py"],
                "diff_chunks": ["+ MAX_PAGE_SIZE = 100"],
                "review_comments": [],
                "created_at": (NOW - timedelta(days=1)).isoformat(),
                "days_open": 1,
                "diff_line_count": 3,
            },
            "ticket": {
                "ticket_id": "PROJ-525",
                "title": "Increase max page size for API",
                "description": "Increase page size limit from 50 to 100.",
                "status": "In Progress",
                "assignee": "eng_alice",
                "component": "api",
                "created_at": (NOW - timedelta(days=2)).isoformat(),
                "sprint_name": "Sprint 24",
            },
            "slack": None,
            "gold_output": {
                "status": "no_issue",
                "blocker_type": None,
                "expected_severity_min": None,
                "expected_owner": None,
                "expected_recurrence_min": 0,
                "notes": "Trivial change, 1 day open, no signals — expect no_issue",
            },
        },
    ]

    # Fill remaining slots with generated scenarios
    remaining = count - len(edge_cases)
    for j in range(remaining):
        idx = start_id + len(edge_cases) + j
        component = COMPONENTS[j % len(COMPONENTS)]
        author = TEAM_MEMBER_IDS[j % len(TEAM_MEMBER_IDS)]
        days = rng.randint(1, 12)
        has_blocker = rng.random() < component.blocker_rate

        scenarios_entry: dict[str, Any] = {
            "scenario_id": f"{idx:03d}",
            "description": f"Generated scenario — {component.name}/ {'with blocker' if has_blocker else 'clean'}",
            "pr": {
                "pr_id": f"PR-GEN-{idx:03d}",
                "title": _pr_title(component.name, "medium"),
                "author": author,
                "changed_files": _sample_files(component.name),
                "diff_chunks": ["# Generated diff chunk"],
                "review_comments": [f"Awaiting review — day {days}"] if days > 5 else [],
                "created_at": (NOW - timedelta(days=days)).isoformat(),
                "days_open": days,
                "diff_line_count": rng.randint(50, 500),
            },
            "ticket": {
                "ticket_id": f"PROJ-GEN-{idx:03d}",
                "title": _pr_title(component.name, "medium"),
                "description": "Task description for generated scenario.",
                "status": "In Progress",
                "assignee": author,
                "component": component.name,
                "created_at": (NOW - timedelta(days=days + 2)).isoformat(),
                "sprint_name": "Sprint 24",
            },
            "slack": None,
            "gold_output": {
                "status": "insight" if has_blocker else "no_issue",
                "blocker_type": component.common_blocker if has_blocker else None,
                "expected_severity_min": 2 if has_blocker else None,
                "expected_owner": None,
                "expected_recurrence_min": 0,
                "notes": "Generated scenario — loose gold labels",
            },
        }
        scenarios.append(scenarios_entry)

    return edge_cases + scenarios


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def main() -> None:
    out_dir = Path(__file__).parent

    # Historical PRs
    prs = generate_pr_history(target=235)
    pr_path = out_dir / "history" / "prs.json"
    pr_path.write_text(json.dumps(prs, indent=2, default=str))
    print(f"Generated {len(prs)} PR records → {pr_path}")

    # Historical insights
    insights = generate_insight_history(target=55)
    ins_path = out_dir / "history" / "insights.json"
    ins_path.write_text(json.dumps(insights, indent=2, default=str))
    print(f"Generated {len(insights)} insight records → {ins_path}")

    # Scenarios
    scenarios = generate_scenarios()
    scenarios_dir = out_dir / "scenarios"
    for scenario in scenarios:
        sid = scenario["scenario_id"]
        path = scenarios_dir / f"{sid:>03}_scenario.json"
        path.write_text(json.dumps(scenario, indent=2, default=str))
    print(f"Generated {len(scenarios)} scenarios → {scenarios_dir}/")


if __name__ == "__main__":
    main()
