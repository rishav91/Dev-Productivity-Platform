from __future__ import annotations

import numpy as np
import asyncpg

from backend.context.embeddings import query_past_insights, query_similar_prs
from backend.schemas.models import ContextBundle, PRData, SlackThreadData, TicketData

# Max tokens sent to Claude. Primary inputs first, retrieved context second.
MAX_CONTEXT_TOKENS = 80_000
# Rough estimate: 1 token ≈ 4 chars. Used for budget enforcement.
_CHARS_PER_TOKEN = 4

# Minimum sample size for a meaningful baseline; below this severity is capped at 2
MIN_HISTORY_SAMPLE = 5


def _estimate_tokens(text: str) -> int:
    return len(text) // _CHARS_PER_TOKEN


async def assemble(
    conn: asyncpg.Connection,
    pr: PRData,
    ticket: TicketData,
    slack: SlackThreadData | None,
) -> ContextBundle:
    """
    Build a ContextBundle by retrieving historical baselines and past insights.

    Retrieval answers two specific questions the LLM cannot answer alone:
      1. What is this team's p85 review cycle for this author + files?
      2. Has this blocker pattern fired before on this component?

    Token budget is enforced here (not inside nodes).
    """
    # --- Baseline severity calibration ---
    similar_prs = await query_similar_prs(
        conn=conn,
        author=pr.author,
        file_paths=pr.changed_files,
        limit=10,
    )

    cycle_days = [float(row["days_open"]) for row in similar_prs if row.get("days_open") is not None]
    history_sample_size = len(cycle_days)

    if history_sample_size >= MIN_HISTORY_SAMPLE:
        baseline_p85 = float(np.percentile(cycle_days, 85))
    else:
        baseline_p85 = None  # Sparse history — severity will be capped at 2

    # --- Recurrence detection ---
    blocker_types_to_check = ["review_bottleneck", "scope_creep", "dependency_block", "unclear_requirements"]
    past_insights_rows = await query_past_insights(
        conn=conn,
        component=ticket.component,
        blocker_types=blocker_types_to_check,
        limit=5,
        days_window=90,
    )

    recurrence_count = len(past_insights_rows)
    past_summaries: list[str] = []

    # Respect token budget: primary inputs consume most of the budget
    primary_char_budget = MAX_CONTEXT_TOKENS * _CHARS_PER_TOKEN
    retrieved_budget = primary_char_budget // 4  # allow 25% of budget for retrieved context

    chars_used = 0
    for row in past_insights_rows:
        import json
        raw = row.get("raw")
        if isinstance(raw, str):
            data = json.loads(raw)
        else:
            data = raw or {}
        summary = data.get("summary", "")
        if chars_used + len(summary) > retrieved_budget:
            break
        past_summaries.append(summary)
        chars_used += len(summary)

    return ContextBundle(
        primary_pr=pr,
        primary_ticket=ticket,
        primary_slack=slack,
        baseline_cycle_p85_days=round(baseline_p85, 2) if baseline_p85 is not None else None,
        recurrence_count=recurrence_count,
        past_insight_summaries=past_summaries,
        history_sample_size=history_sample_size,
    )
