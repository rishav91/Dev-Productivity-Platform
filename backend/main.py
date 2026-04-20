from __future__ import annotations

import os
from contextlib import asynccontextmanager
from typing import AsyncGenerator

import asyncpg
from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware

load_dotenv()

from backend.agent.graph import run_analysis
from backend.schemas.models import AnalysisRequest, ArtifactSnapshot

_pool: asyncpg.Pool | None = None


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    global _pool
    _pool = await asyncpg.create_pool(
        dsn=os.environ["DATABASE_URL"],
        min_size=2,
        max_size=10,
    )
    yield
    if _pool:
        await _pool.close()


app = FastAPI(
    title="Dev Productivity Platform",
    description="Contextual insight engine — PR + ticket + Slack → InsightPayload",
    version="0.1.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000"],
    allow_methods=["GET", "POST"],
    allow_headers=["*"],
)


def _get_pool() -> asyncpg.Pool:
    if _pool is None:
        raise RuntimeError("Database pool not initialized")
    return _pool


@app.post("/analyze", response_model=ArtifactSnapshot, status_code=202)
async def analyze(request: AnalysisRequest) -> ArtifactSnapshot:
    """
    Run analysis for a PR + ticket (+ optional Slack thread).
    Returns an ArtifactSnapshot with the InsightPayload and LangSmith trace URL.
    """
    async with _get_pool().acquire() as conn:
        run, snapshot = await run_analysis(request=request, conn=conn)

    if snapshot is None:
        raise HTTPException(
            status_code=500,
            detail=f"Analysis failed for run {run.run_id}. Check logs.",
        )

    return snapshot


@app.get("/runs/{run_id}", response_model=ArtifactSnapshot)
async def get_run(run_id: str) -> ArtifactSnapshot:
    """Retrieve a completed analysis by run_id for the results page."""
    import json

    async with _get_pool().acquire() as conn:
        row = await conn.fetchrow(
            "SELECT insight, langsmith_trace_url FROM analysis_runs WHERE run_id = $1",
            run_id,
        )

    if row is None:
        raise HTTPException(status_code=404, detail=f"Run {run_id!r} not found")

    if row["insight"] is None:
        raise HTTPException(status_code=422, detail=f"Run {run_id!r} has no insight (failed or pending)")

    from backend.schemas.models import InsightPayload

    insight_data = row["insight"]
    if isinstance(insight_data, str):
        insight_data = json.loads(insight_data)

    return ArtifactSnapshot(
        run_id=run_id,
        insight=InsightPayload.model_validate(insight_data),
        langsmith_trace_url=row["langsmith_trace_url"],
    )


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}
