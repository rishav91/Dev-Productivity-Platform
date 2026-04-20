from __future__ import annotations

import json
import asyncpg
from langsmith import traceable

from backend.adapters.github import GitHubPRExtractor
from backend.adapters.jira import JiraTicketExtractor
from backend.adapters.slack import SlackThreadExtractor
from backend.agent.prompts import (
    EXTRACT_DIVERGENCE_TOOL,
    HYPOTHESIZE_SYSTEM,
    HYPOTHESIZE_USER,
    PRODUCE_INSIGHT_TOOL,
    SYNTHESIZE_SYSTEM,
    SYNTHESIZE_USER,
)
from backend.agent.state import AgentState
from backend.context.assembly import assemble
from backend.providers.llm import call_with_tool
from backend.schemas.models import (
    ContextBundle,
    DivergenceSignals,
    EvidenceItem,
    InsightPayload,
    SourceType,
)


def _get_db_conn() -> asyncpg.Connection:
    # Connection is injected via state at graph invocation time
    # Nodes access it from the context var set in graph.py
    from backend.agent.graph import _db_conn_var
    conn = _db_conn_var.get()
    if conn is None:
        raise RuntimeError("DB connection not set — invoke graph via run_analysis()")
    return conn


@traceable(name="extract_node")
async def extract_node(state: AgentState) -> AgentState:
    """Deterministic: load primary inputs from fixture adapters. Fails fast on missing data."""
    req = state["request"]
    scenario_id = req.pr_id  # scenario lookup key

    try:
        pr = await GitHubPRExtractor().extract(scenario_id)
        ticket = await JiraTicketExtractor().extract(scenario_id)
        slack = await SlackThreadExtractor().extract(scenario_id)
    except FileNotFoundError as e:
        return {**state, "error": f"extract_node: {e}"}

    return {
        **state,
        "pr_data": pr,
        "ticket_data": ticket,
        "slack_data": slack,
    }


@traceable(name="assemble_node")
async def assemble_node(state: AgentState) -> AgentState:
    """Deterministic + retrieval: build ContextBundle with baseline and recurrence data."""
    if state.get("error"):
        return state

    conn = _get_db_conn()
    bundle = await assemble(
        conn=conn,
        pr=state["pr_data"],
        ticket=state["ticket_data"],
        slack=state["slack_data"],
    )
    return {**state, "context_bundle": bundle}


@traceable(name="hypothesize_node")
async def hypothesize_node(state: AgentState) -> AgentState:
    """LLM: detect divergence signals. Returns DivergenceSignals via tool use."""
    if state.get("error"):
        return state

    bundle: ContextBundle = state["context_bundle"]
    pr = state["pr_data"]
    ticket = state["ticket_data"]
    slack = state["slack_data"]

    user_msg = HYPOTHESIZE_USER.format(
        pr_json=json.dumps(pr.model_dump(mode="json"), indent=2),
        ticket_json=json.dumps(ticket.model_dump(mode="json"), indent=2),
        slack_json=json.dumps(slack.model_dump(mode="json") if slack else None, indent=2),
        context_json=json.dumps(bundle.model_dump(mode="json"), indent=2),
    )

    try:
        _, args, cost, elapsed_ms = await call_with_tool(
            system=HYPOTHESIZE_SYSTEM,
            user=user_msg,
            tool=EXTRACT_DIVERGENCE_TOOL,
            max_tokens=1024,
            temperature=0.1,
        )
    except RuntimeError as e:
        return {**state, "error": f"hypothesize_node: {e}"}

    signals = DivergenceSignals.model_validate(args)

    return {
        **state,
        "divergence_signals": signals,
        "cost_usd": state.get("cost_usd", 0.0) + cost,
        "latency_ms": state.get("latency_ms", 0) + elapsed_ms,
    }


@traceable(name="synthesize_and_gate_node")
async def synthesize_and_gate_node(state: AgentState) -> AgentState:
    """LLM + confidence gate: produce InsightPayload via tool use, enforce abstention rules."""
    if state.get("error"):
        return state

    bundle: ContextBundle = state["context_bundle"]
    signals: DivergenceSignals = state["divergence_signals"]
    pr = state["pr_data"]
    ticket = state["ticket_data"]
    slack = state["slack_data"]

    user_msg = SYNTHESIZE_USER.format(
        signals_json=json.dumps(signals.model_dump(mode="json"), indent=2),
        context_json=json.dumps(bundle.model_dump(mode="json"), indent=2),
        pr_json=json.dumps(pr.model_dump(mode="json"), indent=2),
        ticket_json=json.dumps(ticket.model_dump(mode="json"), indent=2),
        slack_json=json.dumps(slack.model_dump(mode="json") if slack else None, indent=2),
    )

    try:
        _, raw, cost, elapsed_ms = await call_with_tool(
            system=SYNTHESIZE_SYSTEM,
            user=user_msg,
            tool=PRODUCE_INSIGHT_TOOL,
            max_tokens=2048,
            temperature=0.2,
        )
    except RuntimeError as e:
        return {**state, "error": f"synthesize_node: {e}"}

    # Parse evidence items
    evidence = [EvidenceItem.model_validate(e) for e in raw.get("evidence", [])]

    # Build InsightPayload and enforce confidence gates
    insight = InsightPayload(
        status=raw["status"],
        blocker_type=raw.get("blocker_type"),
        severity=raw.get("severity"),
        owner=raw.get("owner"),
        owner_confidence=raw.get("owner_confidence"),
        summary=raw["summary"],
        recommended_actions=raw.get("recommended_actions", []),
        evidence=evidence,
        missing_sources=raw.get("missing_sources", []),
        confidence=raw["confidence"],
        recurrence_count=raw.get("recurrence_count", bundle.recurrence_count),
        baseline_cycle_p85_days=raw.get("baseline_cycle_p85_days", bundle.baseline_cycle_p85_days),
    )

    # Confidence gate: abstain rather than speculate
    if insight.confidence < 0.5:
        insight = insight.model_copy(update={"status": "insufficient_evidence", "owner": None})

    # Owner gate
    if insight.owner_confidence is not None and insight.owner_confidence < 0.65:
        insight = insight.model_copy(update={"owner": None})

    return {
        **state,
        "insight": insight,
        "cost_usd": state.get("cost_usd", 0.0) + cost,
        "latency_ms": state.get("latency_ms", 0) + elapsed_ms,
    }
