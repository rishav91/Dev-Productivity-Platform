from __future__ import annotations

import asyncio
import json
from datetime import datetime, timedelta, timezone
from typing import Any

import asyncpg
import litellm

from backend.providers.config import get_embed_model
from backend.schemas.models import InsightPayload, PRData

# sentence-transformers model cache — populated lazily when EMBED_PROVIDER=local
_local_st_model: Any = None
_local_st_model_name: str | None = None


async def embed(text: str) -> list[float]:
    """Embed text using the configured provider (openai / ollama / local)."""
    spec = get_embed_model()  # e.g. "openai/text-embedding-3-small" or "local/all-MiniLM-L6-v2"

    if spec.startswith("local/"):
        model_name = spec.removeprefix("local/")
        return await asyncio.get_event_loop().run_in_executor(None, _embed_local, model_name, text)

    resp = await litellm.aembedding(model=spec, input=text)
    return resp.data[0]["embedding"]


def _embed_local(model_name: str, text: str) -> list[float]:
    """sentence-transformers inference — runs in a thread pool to avoid blocking the event loop."""
    global _local_st_model, _local_st_model_name
    try:
        from sentence_transformers import SentenceTransformer  # type: ignore[import]
    except ImportError as exc:
        raise RuntimeError(
            "sentence-transformers not installed. "
            "Run: pip install sentence-transformers"
        ) from exc

    if _local_st_model is None or _local_st_model_name != model_name:
        _local_st_model = SentenceTransformer(model_name)
        _local_st_model_name = model_name

    return _local_st_model.encode(text).tolist()


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
