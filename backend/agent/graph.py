from __future__ import annotations

import asyncio
import os
import uuid
from contextvars import ContextVar
from datetime import datetime, timezone

import asyncpg
from langgraph.graph import StateGraph

from backend.agent.nodes import (
    assemble_node,
    extract_node,
    hypothesize_node,
    synthesize_and_gate_node,
)
from backend.agent.state import AgentState
from backend.context.embeddings import embed, upsert_embedding
from backend.schemas.models import AnalysisRequest, AnalysisRun, ArtifactSnapshot, InsightPayload

# Context variable for injecting the DB connection into nodes
_db_conn_var: ContextVar[asyncpg.Connection | None] = ContextVar("db_conn", default=None)


def _build_graph() -> StateGraph:
    graph = StateGraph(AgentState)

    graph.add_node("extract", extract_node)
    graph.add_node("assemble", assemble_node)
    graph.add_node("hypothesize", hypothesize_node)
    graph.add_node("synthesize_and_gate", synthesize_and_gate_node)

    graph.set_entry_point("extract")
    graph.add_edge("extract", "assemble")
    graph.add_edge("assemble", "hypothesize")
    graph.add_edge("hypothesize", "synthesize_and_gate")
    graph.set_finish_point("synthesize_and_gate")

    return graph


workflow = _build_graph().compile()


async def run_analysis(
    request: AnalysisRequest,
    conn: asyncpg.Connection,
) -> tuple[AnalysisRun, ArtifactSnapshot | None]:
    """
    Run the full analysis graph and persist the result.

    Returns (run, snapshot) — snapshot is None when the graph fails.
    """
    run_id = str(uuid.uuid4())
    created_at = datetime.now(tz=timezone.utc)

    run = AnalysisRun(
        run_id=run_id,
        request=request,
        status="running",
        created_at=created_at,
    )

    # Inject DB connection into context var so nodes can access it
    token = _db_conn_var.set(conn)

    initial_state: AgentState = {
        "request": request,
        "pr_data": None,
        "ticket_data": None,
        "slack_data": None,
        "context_bundle": None,
        "divergence_signals": None,
        "insight": None,
        "error": None,
        "cost_usd": 0.0,
        "latency_ms": 0,
    }

    try:
        final_state: AgentState = await workflow.ainvoke(initial_state)
    finally:
        _db_conn_var.reset(token)

    completed_at = datetime.now(tz=timezone.utc)

    if final_state.get("error") or final_state.get("insight") is None:
        run = run.model_copy(update={
            "status": "failed",
            "completed_at": completed_at,
        })
        await _save_run(conn, run, insight=None, langsmith_url=None)
        return run, None

    insight: InsightPayload = final_state["insight"]
    run = run.model_copy(update={
        "status": "complete",
        "completed_at": completed_at,
        "cost_usd": final_state.get("cost_usd"),
        "latency_ms": final_state.get("latency_ms"),
    })

    langsmith_url = _get_langsmith_url(run_id)
    snapshot = ArtifactSnapshot(run_id=run_id, insight=insight, langsmith_trace_url=langsmith_url)

    await _save_run(conn, run, insight=insight, langsmith_url=langsmith_url)
    await _maybe_index(conn, run_id, insight, request)

    return run, snapshot


async def _save_run(
    conn: asyncpg.Connection,
    run: AnalysisRun,
    insight: InsightPayload | None,
    langsmith_url: str | None,
) -> None:
    import json

    await conn.execute(
        """
        INSERT INTO analysis_runs
            (run_id, pr_id, ticket_id, slack_thread_id, status, created_at,
             completed_at, cost_usd, latency_ms, insight, langsmith_trace_url)
        VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9,$10::jsonb,$11)
        ON CONFLICT (run_id) DO UPDATE SET
            status=EXCLUDED.status,
            completed_at=EXCLUDED.completed_at,
            cost_usd=EXCLUDED.cost_usd,
            latency_ms=EXCLUDED.latency_ms,
            insight=EXCLUDED.insight,
            langsmith_trace_url=EXCLUDED.langsmith_trace_url
        """,
        run.run_id,
        run.request.pr_id,
        run.request.ticket_id,
        run.request.slack_thread_id,
        run.status,
        run.created_at,
        run.completed_at,
        run.cost_usd,
        run.latency_ms,
        json.dumps(insight.model_dump(mode="json")) if insight else None,
        langsmith_url,
    )


async def _maybe_index(
    conn: asyncpg.Connection,
    run_id: str,
    insight: InsightPayload,
    request: AnalysisRequest,
) -> None:
    """Index high-confidence insights into pgvector for future retrieval."""
    if insight.status != "insight" or insight.confidence < 0.7:
        return  # Never index low-confidence outputs — protects retrieval quality

    # Fetch ticket component from the state stored in DB
    ticket_component = await conn.fetchval(
        "SELECT raw->>'component' FROM insight_history WHERE insight_id = $1", run_id
    ) or "unknown"

    embedding = await embed(f"{insight.summary} {insight.blocker_type or ''}")
    await upsert_embedding(
        conn=conn,
        run_id=run_id,
        embedding=embedding,
        metadata={
            "component": ticket_component,
            "blocker_type": insight.blocker_type or "none",
            "severity": insight.severity,
            "owner": insight.owner,
            "summary": insight.summary,
        },
    )


def _get_langsmith_url(run_id: str) -> str | None:
    project = os.environ.get("LANGCHAIN_PROJECT", "dev-productivity-platform")
    if os.environ.get("LANGCHAIN_TRACING_V2") == "true":
        return f"https://smith.langchain.com/projects/{project}/runs/{run_id}"
    return None
