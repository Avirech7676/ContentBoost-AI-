"""
memory.py — Thin async wrapper over database.py for ContentBoost AI.

Maintains the same public API as the original in-memory store,
but delegates all persistence to the SQLite database.
Eliminates the O(all_data) JSON rewrite on every mutation.
"""

from __future__ import annotations

from typing import List, Optional

from backend import database
from backend.models import GenerateResponse, HistoryEntry


async def save_version(user_id: str, response: GenerateResponse) -> HistoryEntry:
    return await database.save_version(user_id, response)


async def get_version(user_id: str, version_id: str) -> Optional[HistoryEntry]:
    return await database.get_version(user_id, version_id)


async def get_product_history(user_id: str, product_name: str) -> List[HistoryEntry]:
    return await database.get_product_history(user_id, product_name)


async def get_all_history(user_id: str, limit: int = 100) -> List[HistoryEntry]:
    return await database.get_all_history(user_id, limit)


async def delete_version(user_id: str, version_id: str) -> bool:
    return await database.delete_version(user_id, version_id)


async def get_version_count(user_id: str, product_name: str) -> int:
    return await database.get_max_version_number(user_id, product_name)


async def update_version_content(
    user_id: str,
    version_id: str,
    version_type: str,
    new_title: str,
    new_description: str,
) -> bool:
    return await database.update_version_content(user_id, version_id, version_type, new_title, new_description)
