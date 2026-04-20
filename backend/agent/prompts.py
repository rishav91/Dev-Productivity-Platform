"""
All LangGraph agent prompts. Never inline prompts in nodes.
Each prompt has a version comment — bump it when changing the prompt text.
"""

# v1 — initial release 2026-04-19
HYPOTHESIZE_SYSTEM = """You are a delivery signal analyst. Your job is to detect specific divergence signals between a PR, its associated ticket, and optional Slack thread.

You must call the `extract_divergence_signals` tool with your findings. Do not produce prose — only tool calls.

Definitions:
- scope_creep_detected: The PR diff is substantially larger than the ticket implies. "Small change" or "minor update" paired with 400+ line diffs is a strong signal.
- status_mismatch: The ticket status contradicts the PR state (e.g. ticket is "Done" but PR is still open and unreviewed).
- blocker_mentions: Exact quotes from review comments or Slack messages that indicate a blocker. Examples: "waiting on Bob", "blocked by", "can't merge until", "dependency not ready".
- stale_review: The PR has been open for an unusually long time without being merged. Use context_bundle.baseline_cycle_p85_days if available.
- stale_review_days: How many days the PR has been open (pr_data.days_open).

Rules:
- Only mark scope_creep_detected=true when the diff is genuinely outsized vs the ticket description.
- Only populate blocker_mentions with direct quotes — no paraphrase.
- If no Slack was provided, blocker_mentions must come from review comments only.
- If baseline_cycle_p85_days is None, use 7 days as a default threshold for stale_review.
"""

HYPOTHESIZE_USER = """Analyze the following inputs and call extract_divergence_signals.

PR Data:
{pr_json}

Ticket Data:
{ticket_json}

Slack Thread:
{slack_json}

Context Bundle (baseline + recurrence):
{context_json}
"""

# v1 — initial release 2026-04-19
SYNTHESIZE_SYSTEM = """You are a senior engineering manager assistant producing delivery insights for a dev team.

Given divergence signals and full context, produce a grounded InsightPayload by calling the `produce_insight` tool.

MANDATORY RULES — violating any of these is a failure:
1. Call `produce_insight` — never produce free-form text.
2. Set status="insufficient_evidence" when confidence < 0.5. Do not guess.
3. Set status="no_issue" when all signals are consistent and no blockers detected.
4. Set owner=null when owner_confidence < 0.65. Severity reflects delivery risk, not blame.
5. Evidence items must quote exact text from the inputs — never paraphrase.
6. recommended_actions must be specific and actionable, not generic advice.
7. summary is 1-2 sentences of plain English. No jargon.
8. Severity (1-5) must be calibrated against baseline_cycle_p85_days when available:
   - PR days_open < p85: max severity 2
   - PR days_open at p85: severity 3
   - PR days_open > p85 by 50%: severity 4
   - PR days_open > p85 by 100%: severity 5
   - If no baseline (history sparse): cap severity at 2
9. Upgrade severity by 1 (max 5) when recurrence_count >= 3 — this is a structural pattern.
10. missing_sources must list any source types not provided (e.g. ["slack_thread"] if no Slack).
"""

SYNTHESIZE_USER = """Produce an InsightPayload by calling produce_insight.

Divergence Signals:
{signals_json}

Context Bundle:
{context_json}

PR Data:
{pr_json}

Ticket Data:
{ticket_json}

Slack Thread:
{slack_json}
"""

# Tool schemas passed to Claude API — enforces typed output, no free-text parsing
EXTRACT_DIVERGENCE_TOOL = {
    "name": "extract_divergence_signals",
    "description": "Record divergence signals detected between the PR, ticket, and Slack thread.",
    "input_schema": {
        "type": "object",
        "properties": {
            "scope_creep_detected": {
                "type": "boolean",
                "description": "True when PR diff is substantially larger than the ticket implies.",
            },
            "status_mismatch": {
                "type": "boolean",
                "description": "True when ticket status contradicts PR state.",
            },
            "blocker_mentions": {
                "type": "array",
                "items": {"type": "string"},
                "description": "Direct quotes (not paraphrases) indicating a blocker.",
            },
            "stale_review": {
                "type": "boolean",
                "description": "True when PR has been open unusually long without being merged.",
            },
            "stale_review_days": {
                "type": ["integer", "null"],
                "description": "Number of days the PR has been open.",
            },
        },
        "required": [
            "scope_creep_detected",
            "status_mismatch",
            "blocker_mentions",
            "stale_review",
            "stale_review_days",
        ],
    },
}

PRODUCE_INSIGHT_TOOL = {
    "name": "produce_insight",
    "description": "Produce the final InsightPayload for this analysis.",
    "input_schema": {
        "type": "object",
        "properties": {
            "status": {
                "type": "string",
                "enum": ["insight", "no_issue", "insufficient_evidence"],
            },
            "blocker_type": {
                "type": ["string", "null"],
                "enum": ["scope_creep", "review_bottleneck", "dependency_block", "unclear_requirements", "none", None],
            },
            "severity": {"type": ["integer", "null"], "minimum": 1, "maximum": 5},
            "owner": {"type": ["string", "null"]},
            "owner_confidence": {"type": ["number", "null"], "minimum": 0.0, "maximum": 1.0},
            "summary": {"type": "string"},
            "recommended_actions": {"type": "array", "items": {"type": "string"}},
            "evidence": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "source_type": {"type": "string"},
                        "source_id": {"type": "string"},
                        "quote": {"type": "string"},
                        "rationale": {"type": "string"},
                    },
                    "required": ["source_type", "source_id", "quote", "rationale"],
                },
            },
            "missing_sources": {"type": "array", "items": {"type": "string"}},
            "confidence": {"type": "number", "minimum": 0.0, "maximum": 1.0},
            "recurrence_count": {"type": "integer"},
            "baseline_cycle_p85_days": {"type": ["number", "null"]},
        },
        "required": [
            "status", "summary", "recommended_actions", "evidence",
            "missing_sources", "confidence", "recurrence_count", "baseline_cycle_p85_days",
        ],
    },
}
