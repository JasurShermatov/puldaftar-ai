from __future__ import annotations

import re
from uuid import UUID

from app.core.security import phrase_hash


async def list_for_user(conn, user_id: UUID, include_inactive: bool = False) -> list[dict]:
    """Tizim + userning shaxsiy kategoriyalari. RLS boshqa userlarnikini baribir yashiradi."""
    rows = await conn.fetch(
        """SELECT id, user_id, type, key, name, emoji, sort, is_active FROM categories
           WHERE (user_id IS NULL OR user_id=$1) AND ($2 OR is_active)
           ORDER BY type, sort, name""",
        user_id, include_inactive,
    )
    return [dict(r) for r in rows]


async def key_map(conn, user_id: UUID) -> dict[str, dict]:
    """key → kategoriya (user'niki tizimnikini ustiga yozadi)."""
    out: dict[str, dict] = {}
    for c in await list_for_user(conn, user_id):
        if c["key"] not in out or c["user_id"] is not None:
            out[c["key"]] = c
    return out


async def create_custom(conn, user_id: UUID, type_: str, name: str, emoji: str = "•") -> dict:
    key = "u_" + re.sub(r"[^a-z0-9]+", "_", name.lower()).strip("_")[:30]
    row = await conn.fetchrow(
        """INSERT INTO categories (user_id, type, key, name, emoji, sort)
           VALUES ($1,$2,$3,$4,$5,500)
           ON CONFLICT (user_id, type, key) WHERE user_id IS NOT NULL
           DO UPDATE SET name=EXCLUDED.name, emoji=EXCLUDED.emoji, is_active=true
           RETURNING id, user_id, type, key, name, emoji, sort, is_active""",
        user_id, type_, key, name[:40], emoji[:4],
    )
    return dict(row)


async def update_custom(conn, user_id: UUID, cat_id: int, name: str | None, is_active: bool | None) -> bool:
    r = await conn.execute(
        "UPDATE categories SET name=coalesce($3,name), is_active=coalesce($4,is_active) WHERE id=$1 AND user_id=$2",
        cat_id, user_id, name, is_active,
    )
    return r.endswith("1")


# ---------------- Kategoriya o'rganish ----------------

def _words(description: str) -> list[str]:
    return [w for w in re.findall(r"[a-zа-яё'ʻ’0-9]+", description.lower()) if len(w) >= 3][:4]


async def learned_category(conn, user_id: UUID, description: str) -> int | None:
    hashes = [phrase_hash(user_id, w) for w in _words(description)]
    if not hashes:
        return None
    return await conn.fetchval(
        """SELECT category_id FROM category_rules WHERE user_id=$1 AND phrase_hash = ANY($2::text[]) AND hits >= 1
           ORDER BY hits DESC, updated_at DESC LIMIT 1""",
        user_id, hashes,
    )


async def learn(conn, user_id: UUID, description: str, category_id: int) -> None:
    for w in _words(description):
        await conn.execute(
            """INSERT INTO category_rules (user_id, phrase_hash, category_id) VALUES ($1,$2,$3)
               ON CONFLICT (user_id, phrase_hash) DO UPDATE SET
                 hits = CASE WHEN category_rules.category_id = EXCLUDED.category_id THEN category_rules.hits + 1 ELSE 1 END,
                 category_id = EXCLUDED.category_id, updated_at = now()""",
            user_id, phrase_hash(user_id, w), category_id,
        )
