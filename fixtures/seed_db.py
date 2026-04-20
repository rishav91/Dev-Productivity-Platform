"""
Seeds pgvector + Postgres from generated fixture files.

Run after: python fixtures/generate.py
Usage:     python fixtures/seed_db.py

Idempotent — safe to re-run (uses INSERT ... ON CONFLICT DO NOTHING).
Requires DATABASE_URL and OPENAI_API_KEY in environment.
"""
from __future__ import annotations

import asyncio
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).parent.parent))

from dotenv import load_dotenv

load_dotenv()

import asyncpg
from openai import AsyncOpenAI

FIXTURES_DIR = Path(__file__).parent
DATABASE_URL = os.environ["DATABASE_URL"]
EMBED_MODEL = "text-embedding-3-small"
EMBED_DIM = 1536
EMBED_BATCH = 100  # OpenAI allows up to 2048 inputs per request


async def get_embedding(client: AsyncOpenAI, text: str) -> list[float]:
    resp = await client.embeddings.create(input=text, model=EMBED_MODEL)
    return resp.data[0].embedding


async def get_embeddings_batch(client: AsyncOpenAI, texts: list[str]) -> list[list[float]]:
    resp = await client.embeddings.create(input=texts, model=EMBED_MODEL)
    return [item.embedding for item in sorted(resp.data, key=lambda x: x.index)]


async def seed_pr_history(conn: asyncpg.Connection, client: AsyncOpenAI) -> int:
    path = FIXTURES_DIR / "history" / "prs.json"
    if not path.exists():
        print("  ⚠  fixtures/history/prs.json not found — run generate.py first")
        return 0

    prs: list[dict[str, Any]] = json.loads(path.read_text())

    # Build embedding texts in batch
    embed_texts = [f"{pr['title']} {' '.join(pr['changed_files'])}" for pr in prs]

    print(f"  Computing {len(embed_texts)} PR embeddings...")
    all_embeddings: list[list[float]] = []
    for i in range(0, len(embed_texts), EMBED_BATCH):
        batch = embed_texts[i : i + EMBED_BATCH]
        all_embeddings.extend(await get_embeddings_batch(client, batch))

    inserted = 0
    for pr, embedding in zip(prs, all_embeddings):
        created_at = datetime.fromisoformat(pr["created_at"])
        if created_at.tzinfo is None:
            created_at = created_at.replace(tzinfo=timezone.utc)

        await conn.execute(
            """
            INSERT INTO pr_history
                (pr_id, author, title, changed_files, days_open, diff_line_count, created_at, embedding, raw)
            VALUES ($1, $2, $3, $4, $5, $6, $7, $8::vector, $9::jsonb)
            ON CONFLICT (pr_id) DO NOTHING
            """,
            pr["pr_id"],
            pr["author"],
            pr["title"],
            pr["changed_files"],
            pr["days_open"],
            pr["diff_line_count"],
            created_at,
            f"[{','.join(str(x) for x in embedding)}]",
            json.dumps(pr),
        )
        inserted += 1

    return inserted


async def seed_insight_history(conn: asyncpg.Connection, client: AsyncOpenAI) -> int:
    path = FIXTURES_DIR / "history" / "insights.json"
    if not path.exists():
        print("  ⚠  fixtures/history/insights.json not found — run generate.py first")
        return 0

    insights: list[dict[str, Any]] = json.loads(path.read_text())

    embed_texts = [
        f"{ins['summary']} {ins['blocker_type'] or ''} {ins['component']}"
        for ins in insights
    ]

    print(f"  Computing {len(embed_texts)} insight embeddings...")
    all_embeddings: list[list[float]] = []
    for i in range(0, len(embed_texts), EMBED_BATCH):
        batch = embed_texts[i : i + EMBED_BATCH]
        all_embeddings.extend(await get_embeddings_batch(client, batch))

    inserted = 0
    for ins, embedding in zip(insights, all_embeddings):
        created_at = datetime.fromisoformat(ins["created_at"])
        if created_at.tzinfo is None:
            created_at = created_at.replace(tzinfo=timezone.utc)

        await conn.execute(
            """
            INSERT INTO insight_history
                (insight_id, component, blocker_type, severity, summary, confidence,
                 status, created_at, embedding, raw)
            VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9::vector, $10::jsonb)
            ON CONFLICT (insight_id) DO NOTHING
            """,
            ins["insight_id"],
            ins["component"],
            ins.get("blocker_type"),
            ins.get("severity"),
            ins["summary"],
            float(ins["confidence"]),
            ins["status"],
            created_at,
            f"[{','.join(str(x) for x in embedding)}]",
            json.dumps(ins),
        )
        inserted += 1

    return inserted


async def apply_ivfflat_index(conn: asyncpg.Connection) -> None:
    """Build IVFFlat ANN indexes after data is loaded (requires >= 1 row)."""
    await conn.execute(
        "CREATE INDEX IF NOT EXISTS pr_history_embedding_idx "
        "ON pr_history USING ivfflat (embedding vector_cosine_ops) WITH (lists = 20)"
    )
    await conn.execute(
        "CREATE INDEX IF NOT EXISTS insight_history_embedding_idx "
        "ON insight_history USING ivfflat (embedding vector_cosine_ops) WITH (lists = 10)"
    )


async def main() -> None:
    print("Seeding database from fixture files...\n")

    # Convert postgresql:// to asyncpg-compatible URL
    db_url = DATABASE_URL.replace("postgresql://", "")
    conn: asyncpg.Connection = await asyncpg.connect(f"postgresql://{db_url}")

    try:
        oai = AsyncOpenAI(api_key=os.environ["OPENAI_API_KEY"])

        print("Seeding PR history...")
        n_prs = await seed_pr_history(conn, oai)
        print(f"  Inserted {n_prs} PR records\n")

        print("Seeding insight history...")
        n_ins = await seed_insight_history(conn, oai)
        print(f"  Inserted {n_ins} insight records\n")

        print("Building IVFFlat indexes...")
        await apply_ivfflat_index(conn)
        print("  Indexes created\n")

        print("Done. Database is seeded and ready.")
    finally:
        await conn.close()


if __name__ == "__main__":
    asyncio.run(main())
