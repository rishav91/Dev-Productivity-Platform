from __future__ import annotations

from abc import ABC, abstractmethod
from datetime import datetime
from enum import Enum
from typing import Literal

from pydantic import BaseModel, Field


class SourceType(str, Enum):
    github_pr = "github_pr"
    jira_ticket = "jira_ticket"
    slack_thread = "slack_thread"
    repo_history = "repo_history"       # reserved for phase 2
    webhook_event = "webhook_event"     # reserved for phase 2


class EvidenceItem(BaseModel):
    source_type: SourceType
    source_id: str
    quote: str
    rationale: str  # why this quote supports the finding


class PRData(BaseModel):
    pr_id: str
    title: str
    author: str
    changed_files: list[str]
    diff_chunks: list[str]
    review_comments: list[str]
    created_at: datetime
    days_open: int
    diff_line_count: int


class TicketData(BaseModel):
    ticket_id: str
    title: str
    description: str
    status: str
    assignee: str
    component: str
    created_at: datetime
    sprint_name: str | None = None


class SlackMessage(BaseModel):
    user_id: str
    text: str
    ts: str


class SlackThreadData(BaseModel):
    thread_ts: str
    channel: str
    messages: list[SlackMessage]
    participant_ids: list[str]


class ContextBundle(BaseModel):
    primary_pr: PRData
    primary_ticket: TicketData
    primary_slack: SlackThreadData | None
    baseline_cycle_p85_days: float | None  # None when history sample < 5
    recurrence_count: int
    past_insight_summaries: list[str]
    history_sample_size: int  # used for confidence gating


class DivergenceSignals(BaseModel):
    scope_creep_detected: bool
    status_mismatch: bool
    blocker_mentions: list[str]
    stale_review: bool
    stale_review_days: int | None


class InsightPayload(BaseModel):
    # Explicit abstention — never speculate
    status: Literal["insight", "no_issue", "insufficient_evidence"]

    # Only populated when status == "insight"
    blocker_type: Literal[
        "scope_creep", "review_bottleneck",
        "dependency_block", "unclear_requirements", "none"
    ] | None = None
    severity: int | None = Field(None, ge=1, le=5)  # calibrated against baseline
    owner: str | None = None                         # None if owner_confidence < 0.65
    owner_confidence: float | None = Field(None, ge=0.0, le=1.0)

    # Always populated
    summary: str                      # 1–2 sentence plain English
    recommended_actions: list[str]
    evidence: list[EvidenceItem]
    missing_sources: list[str]        # e.g. ["slack_thread"] if not provided
    confidence: float = Field(ge=0.0, le=1.0)
    recurrence_count: int
    baseline_cycle_p85_days: float | None


class AnalysisRequest(BaseModel):
    pr_id: str
    ticket_id: str
    slack_thread_id: str | None = None


class AnalysisRun(BaseModel):
    run_id: str
    request: AnalysisRequest
    status: Literal["pending", "running", "complete", "failed"]
    created_at: datetime
    completed_at: datetime | None = None
    cost_usd: float | None = None
    latency_ms: int | None = None


class ArtifactSnapshot(BaseModel):
    run_id: str
    insight: InsightPayload
    langsmith_trace_url: str | None = None


# ---------------------------------------------------------------------------
# SignalExtractor ABC — phase 1 implementations are fixture-backed
# Phase 2 stubs: RepoHistoryExtractor, WebhookEventExtractor
# ---------------------------------------------------------------------------

class SignalExtractor(ABC):
    source_type: SourceType

    @abstractmethod
    async def extract(self, source_id: str) -> PRData | TicketData | SlackThreadData:
        ...
