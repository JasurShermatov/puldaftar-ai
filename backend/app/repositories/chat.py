"""AI suhbat tarixi (shifrlangan). Har bir user faqat o'z xabarlarini ko'radi (RLS)."""
from __future__ import annotations

from uuid import UUID

from app.core.security import cipher, user_aad

KEEP_LAST = 60


async def add(conn, user_id: UUID, role: str, content: str) -> dict:
    r = await conn.fetchrow(
        "INSERT INTO ai_chat_messages (user_id, role, content_enc) VALUES ($1,$2,$3) RETURNING id, role, created_at",
        user_id, role, cipher().encrypt(content, user_aad(user_id)),
    )
    return {"id": r["id"], "role": r["role"], "content": content, "created_at": r["created_at"].isoformat()}


async def recent(conn, user_id: UUID, limit: int = 20) -> list[dict]:
    rows = await conn.fetch(
        "SELECT id, role, content_enc, created_at FROM ai_chat_messages WHERE user_id=$1 ORDER BY id DESC LIMIT $2",
        user_id, limit,
    )
    c = cipher()
    out = [{"id": r["id"], "role": r["role"], "content": c.decrypt(r["content_enc"], user_aad(user_id)) or "",
            "created_at": r["created_at"].isoformat()} for r in rows]
    return list(reversed(out))


async def trim(conn, user_id: UUID, keep: int = KEEP_LAST) -> None:
    await conn.execute(
        """DELETE FROM ai_chat_messages WHERE user_id=$1 AND id < (
             SELECT coalesce(min(id), 0) FROM (SELECT id FROM ai_chat_messages WHERE user_id=$1 ORDER BY id DESC LIMIT $2) t)""",
        user_id, keep,
    )


async def clear(conn, user_id: UUID) -> None:
    await conn.execute("DELETE FROM ai_chat_messages WHERE user_id=$1", user_id)
