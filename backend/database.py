"""
database.py — Async SQLite persistence layer for ContentBoost AI.
Replaces the JSON flat-file store used in memory.py.

Uses aiosqlite (no ORM) for simplicity and async compatibility.
"""

from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import List, Optional

import aiosqlite

from backend.models import (
    DescriptionVersion,
    GenerateResponse,
    HistoryEntry,
    SEOMetrics,
    Suggestion,
)

# ── Config ─────────────────────────────────────────────────────────────────────

_DB_PATH = Path(os.getenv("DB_FILE", "data/contentboost.db"))
MAX_PER_PRODUCT = int(os.getenv("MAX_HISTORY_PER_PRODUCT", "50"))


def _resolve_db() -> Path:
    """Always resolve DB path relative to project root, not CWD."""
    env_val = os.getenv("DB_FILE", "")
    if env_val and Path(env_val).is_absolute():
        return Path(env_val)
    # Default: <project_root>/data/contentboost.db
    root = Path(__file__).resolve().parent.parent
    return root / "data" / "contentboost.db"


DB_PATH: Path = _resolve_db()


# ── Schema ─────────────────────────────────────────────────────────────────────

_DDL = """
CREATE TABLE IF NOT EXISTS users (
    id TEXT PRIMARY KEY,
    username TEXT UNIQUE NOT NULL,
    hashed_password TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS versions (
    version_id            TEXT PRIMARY KEY,
    user_id               TEXT NOT NULL,
    version_number        INTEGER NOT NULL,
    product_name          TEXT NOT NULL,
    tone                  TEXT NOT NULL,
    timestamp             TEXT NOT NULL,
    seo_title             TEXT NOT NULL DEFAULT '',
    seo_description       TEXT NOT NULL DEFAULT '',
    marketing_title       TEXT NOT NULL DEFAULT '',
    marketing_description TEXT NOT NULL DEFAULT '',
    technical_title       TEXT NOT NULL DEFAULT '',
    technical_description TEXT NOT NULL DEFAULT '',
    keywords              TEXT NOT NULL DEFAULT '[]',
    competitor_insights   TEXT NOT NULL DEFAULT '[]',
    suggestions           TEXT NOT NULL DEFAULT '[]',
    readability_score     REAL DEFAULT 0,
    keyword_density       REAL DEFAULT 0,
    title_length          INTEGER DEFAULT 0,
    description_length    INTEGER DEFAULT 0,
    flesch_score          REAL DEFAULT 0,
    overall_score         REAL DEFAULT 0,
    FOREIGN KEY(user_id) REFERENCES users(id)
);
CREATE INDEX IF NOT EXISTS idx_user_product ON versions (user_id, product_name);
CREATE INDEX IF NOT EXISTS idx_timestamp ON versions (timestamp);
"""


# ── Init ───────────────────────────────────────────────────────────────────────

async def init_db() -> None:
    """Create tables and indexes. Safe to call on every startup."""
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    async with aiosqlite.connect(DB_PATH) as db:
        await db.executescript(_DDL)
        await db.commit()
    print(f"[ContentBoost AI] Database ready -> {DB_PATH}")


# ── Row → Model ────────────────────────────────────────────────────────────────

def _row_to_entry(row: aiosqlite.Row) -> HistoryEntry:
    ts_str = row["timestamp"]
    # Handle both naive and aware ISO strings
    try:
        ts = datetime.fromisoformat(ts_str)
    except ValueError:
        ts = datetime.now(timezone.utc)
    if ts.tzinfo is None:
        ts = ts.replace(tzinfo=timezone.utc)

    return HistoryEntry(
        version_id=row["version_id"],
        version_number=row["version_number"],
        product_name=row["product_name"],
        tone=row["tone"],
        timestamp=ts,
        seo_version=DescriptionVersion(
            title=row["seo_title"],
            description=row["seo_description"],
        ),
        marketing_version=DescriptionVersion(
            title=row["marketing_title"],
            description=row["marketing_description"],
        ),
        technical_version=DescriptionVersion(
            title=row["technical_title"],
            description=row["technical_description"],
        ),
        keywords=json.loads(row["keywords"] or "[]"),
        competitor_insights=json.loads(row["competitor_insights"] or "[]"),
        suggestions=[Suggestion(**s) for s in json.loads(row["suggestions"] or "[]")],
        seo_metrics=SEOMetrics(
            readability_score=row["readability_score"] or 0,
            keyword_density=row["keyword_density"] or 0,
            title_length=row["title_length"] or 0,
            description_length=row["description_length"] or 0,
            flesch_score=row["flesch_score"] or 0,
            overall_score=row["overall_score"] or 0,
        ),
    )


# ── Public API ─────────────────────────────────────────────────────────────────

async def get_max_version_number(user_id: str, product_name: str) -> int:
    """Return the highest stored version number for a product for a specific user."""
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            "SELECT MAX(version_number) AS mx FROM versions WHERE user_id = ? AND product_name = ?",
            (user_id, product_name,),
        ) as cur:
            row = await cur.fetchone()
    return row["mx"] if row and row["mx"] is not None else 0


async def save_version(user_id: str, response: GenerateResponse) -> HistoryEntry:
    """Persist a GenerateResponse, enforcing MAX_PER_PRODUCT cap per user."""
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row

        # Enforce cap — delete oldest entries beyond the limit
        async with db.execute(
            "SELECT version_id FROM versions WHERE user_id = ? AND product_name = ? ORDER BY timestamp ASC",
            (user_id, response.product_name,),
        ) as cur:
            existing = await cur.fetchall()
        overflow = len(existing) - MAX_PER_PRODUCT + 1
        if overflow > 0:
            for r in existing[:overflow]:
                await db.execute("DELETE FROM versions WHERE version_id = ?", (r["version_id"],))

        ts = response.timestamp
        if ts.tzinfo is None:
            ts = ts.replace(tzinfo=timezone.utc)

        await db.execute(
            """
            INSERT OR REPLACE INTO versions (
                version_id, user_id, version_number, product_name, tone, timestamp,
                seo_title, seo_description, marketing_title, marketing_description,
                technical_title, technical_description, keywords, competitor_insights,
                suggestions, readability_score, keyword_density, title_length,
                description_length, flesch_score, overall_score
            ) VALUES (
                ?,?,?,?,?, ?, ?,?,?,?,?, ?,?,?, ?,?,?,?,?,?,?
            )
            """,
            (
                response.version_id,
                user_id,
                response.version_number,
                response.product_name,
                response.tone,
                ts.isoformat(),
                response.seo_version.title,
                response.seo_version.description,
                response.marketing_version.title,
                response.marketing_version.description,
                response.technical_version.title,
                response.technical_version.description,
                json.dumps(response.keywords),
                json.dumps(response.competitor_insights),
                json.dumps([s.model_dump() for s in response.suggestions]),
                response.seo_metrics.readability_score,
                response.seo_metrics.keyword_density,
                response.seo_metrics.title_length,
                response.seo_metrics.description_length,
                response.seo_metrics.flesch_score,
                response.seo_metrics.overall_score,
            ),
        )
        await db.commit()

    # Build HistoryEntry from response to avoid a second round-trip
    return HistoryEntry(
        version_id=response.version_id,
        version_number=response.version_number,
        product_name=response.product_name,
        tone=response.tone,
        timestamp=ts,
        seo_version=response.seo_version,
        marketing_version=response.marketing_version,
        technical_version=response.technical_version,
        keywords=response.keywords,
        competitor_insights=response.competitor_insights,
        suggestions=response.suggestions,
        seo_metrics=response.seo_metrics,
    )


async def get_version(user_id: str, version_id: str) -> Optional[HistoryEntry]:
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            "SELECT * FROM versions WHERE user_id = ? AND version_id = ?", (user_id, version_id,)
        ) as cur:
            row = await cur.fetchone()
    return _row_to_entry(row) if row else None


async def get_product_history(user_id: str, product_name: str) -> List[HistoryEntry]:
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            "SELECT * FROM versions WHERE user_id = ? AND product_name = ? ORDER BY timestamp DESC",
            (user_id, product_name,),
        ) as cur:
            rows = await cur.fetchall()
    return [_row_to_entry(r) for r in rows]


async def get_all_history(user_id: str, limit: int = 100) -> List[HistoryEntry]:
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            "SELECT * FROM versions WHERE user_id = ? ORDER BY timestamp DESC LIMIT ?", (user_id, limit,)
        ) as cur:
            rows = await cur.fetchall()
    return [_row_to_entry(r) for r in rows]


async def delete_version(user_id: str, version_id: str) -> bool:
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute(
            "SELECT 1 FROM versions WHERE user_id = ? AND version_id = ?", (user_id, version_id,)
        ) as cur:
            exists = await cur.fetchone()
        if not exists:
            return False
        await db.execute("DELETE FROM versions WHERE user_id = ? AND version_id = ?", (user_id, version_id,))
        await db.commit()
    return True


async def update_version_content(
    user_id: str,
    version_id: str,
    version_type: str,
    new_title: str,
    new_description: str,
) -> bool:
    col_map = {
        "seo_version": ("seo_title", "seo_description"),
        "marketing_version": ("marketing_title", "marketing_description"),
        "technical_version": ("technical_title", "technical_description"),
    }
    cols = col_map.get(version_type)
    if not cols:
        return False
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            f"UPDATE versions SET {cols[0]} = ?, {cols[1]} = ? WHERE user_id = ? AND version_id = ?",
            (new_title, new_description, user_id, version_id),
        )
        await db.commit()
    return True
