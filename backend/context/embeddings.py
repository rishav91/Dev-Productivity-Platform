from __future__ import annotations

import json
import os
from datetime import datetime, timedelta, timezone
from typing import Any

import asyncpg
from openai import AsyncOpenAI

from backend.schemas.models import InsightPayload, PRData

EMBED_MODEL = "text-embedding-3-small"
_oai_client: AsyncOpenAI | None = None


def _client() -> AsyncOpenAI:
    global _oai_client
    if _oai_client is None:
        _oai_client = AsyncOpenAI(api_key=os.environ["OPENAI_API_KEY"])
    return _oai_client


async def embed(text: str) -> list[float]:
    resp = await _client().embeddings.create(input=text, model=EMBED_MODEL)
    return resp.data[0].embedding


def _vec_literal(embedding: list[float]) -> str:
    return f"[{','.join(str(x) for x in embedding)}]"


async def query_similar_prs(
    conn: asyncpg.Connection,
    author: str,
    file_paths: list[str],
    limit: int = 10,
) -> list[dict[str, Any]]:
    """
    Retrieve historical PRs by the same author or overlapping files for p85 baseline.
    Uses cosine similarity on file-path embedding, filtered by author first.
    Falls back to any PRs by author when file overlap is sparse.
    """
    query_text = f"{author} {' '.join(file_paths)}"
    embedding = await embed(query_text)

    rows = await conn.fetch(
        """
        SELECT raw, days_open, (embedding <=> $1::vector) AS distance
        FROM pr_history
        WHERE author = $2
        ORDER BY embedding <=> $1::vector
        LIMIT $3
        """,
        _vec_literal(embedding),
        author,
        limit,
    )

    if len(rows) < 3:
        # Broaden to any PRs touching same files regardless of author
        rows = await conn.fetch(
            """
            SELECT raw, days_open, (embedding <=> $1::vector) AS distance
            FROM pr_history
            ORDER BY embedding <=> $1::vector
            LIMIT $2
            """,
            _vec_literal(embedding),
            limit,
        )

    return [dict(r) for r in rows]


async def query_past_insights(
    conn: asyncpg.Connection,
    component: str,
    blocker_types: list[str],
    limit: int = 5,
    days_window: int = 90,
) -> list[dict[str, Any]]:
    """
    Retrieve past InsightPayload records for recurrence detection.
    Filters to the last `days_window` days to avoid stale history.
    """
    cutoff = datetime.now(tz=timezone.utc) - timedelta(days=days_window)

    placeholders = ", ".join(f"${i+3}" for i in range(len(blocker_types)))
    query = f"""
        SELECT raw
        FROM insight_history
        WHERE component = $1
          AND created_at >= $2
          AND blocker_type IN ({placeholders})
        ORDER BY created_at DESC
        LIMIT ${3 + len(blocker_types)}
    """

    rows = await conn.fetch(
        query,
        component,
        cutoff,
        *blocker_types,
        limit,
    )

    return [dict(r) for r in rows]


async def upsert_embedding(
    conn: asyncpg.Connection,
    run_id: str,
    embedding: list[float],
    metadata: dict[str, Any],
) -> None:
    """Write a high-confidence insight embedding into pgvector for future retrieval."""
    await conn.execute(
        """
        INSERT INTO insight_embeddings
            (id, embedding, component, blocker_type, severity, owner, summary, created_at)
        VALUES ($1, $2::vector, $3, $4, $5, $6, $7, $8)
        ON CONFLICT (id) DO UPDATE SET
            embedding = EXCLUDED.embedding,
            component = EXCLUDED.component,
            blocker_type = EXCLUDED.blocker_type,
            severity = EXCLUDED.severity,
            owner = EXCLUDED.owner,
            summary = EXCLUDED.summary
        """,
        run_id,
        _vec_literal(embedding),
        metadata["component"],
        metadata["blocker_type"],
        metadata.get("severity"),
        metadata.get("owner"),
        metadata["summary"],
        metadata.get("created_at", datetime.now(tz=timezone.utc)),
    )
