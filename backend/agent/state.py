from __future__ import annotations

from typing import TypedDict

from backend.schemas.models import (
    AnalysisRequest,
    ContextBundle,
    DivergenceSignals,
    InsightPayload,
    PRData,
    SlackThreadData,
    TicketData,
)


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
