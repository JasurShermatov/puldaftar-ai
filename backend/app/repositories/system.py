"""Tizim jadvallari: settings, audit, analytics, idempotency, reports, AI insights, pending parse."""
from __future__ import annotations

import json
from datetime import date
from uuid import UUID

from app.core.security import cipher, user_aad

# ---------------- Settings (kesh bilan) ----------------
_settings_cache: dict[str, tuple[float, dict]] = {}
_TTL = 30.0


async def get_setting(conn, key: str) -> dict:
    import time
    hit = _settings_cache.get(key)
    if hit and time.monotonic() - hit[0] < _TTL:
        return hit[1]
    val = await conn.fetchval("SELECT value FROM app_settings WHERE key=$1", key) or {}
    _settings_cache[key] = (time.monotonic(), val)
    return val


async def set_setting(conn, key: str, patch: dict) -> dict:
    val = await conn.fetchval(
        """INSERT INTO app_settings (key, value) VALUES ($1, $2::jsonb)
           ON CONFLICT (key) DO UPDATE SET value = app_settings.value || EXCLUDED.value, updated_at=now()
           RETURNING value""",
        key, patch,
    )
    _settings_cache.pop(key, None)
    return val


# ---------------- Audit ----------------
async def audit(conn, actor_tg_id: int, action: str, target_user_id: UUID | None = None, meta: dict | None = None):
    await conn.execute(
        "INSERT INTO audit_logs (actor_tg_id, action, target_user_id, meta) VALUES ($1,$2,$3,$4)",
        actor_tg_id, action, target_user_id, meta or {},
    )


async def audit_list(conn, limit: int = 100, offset: int = 0) -> list[dict]:
    rows = await conn.fetch(
        """SELECT a.id, a.actor_tg_id, a.action, a.target_user_id, a.meta, a.created_at,
                  u.username AS target_username, u.telegram_id AS target_tg_id
           FROM audit_logs a LEFT JOIN users u ON u.id=a.target_user_id
           ORDER BY a.id DESC LIMIT $1 OFFSET $2""",
        limit, offset,
    )
    return [dict(r) for r in rows]


# ---------------- Analytics (xom summa/tavsif yuborilmaydi) ----------------
async def event(conn, name: str, user_id: UUID | None = None, props: dict | None = None):
    await conn.execute("INSERT INTO analytics_events (user_id, name, props) VALUES ($1,$2,$3)", user_id, name, props or {})


async def event_counts(conn, hours: int = 24) -> dict:
    rows = await conn.fetch(
        "SELECT name, count(*) c FROM analytics_events WHERE created_at > now() - make_interval(hours => $1) GROUP BY name",
        hours,
    )
    return {r["name"]: r["c"] for r in rows}


# ---------------- Idempotency ----------------
async def claim_update(conn, key: str) -> bool:
    """True — birinchi marta. False — bu update allaqachon ishlangan."""
    r = await conn.fetchval(
        "INSERT INTO processed_updates (update_key) VALUES ($1) ON CONFLICT DO NOTHING RETURNING 1", key
    )
    return r == 1


async def cleanup(conn) -> None:
    await conn.execute("DELETE FROM processed_updates WHERE created_at < now() - interval '3 days'")
    await conn.execute("DELETE FROM pending_parses WHERE created_at < now() - interval '2 days'")
    await conn.execute("DELETE FROM analytics_events WHERE created_at < now() - interval '180 days'")


# ---------------- Reports (bir marta yuborish kafolati) ----------------
async def claim_report(conn, user_id: UUID, period_type: str, period_start: date) -> bool:
    r = await conn.fetchval(
        """INSERT INTO reports (user_id, period_type, period_start, status) VALUES ($1,$2,$3,'sending')
           ON CONFLICT (user_id, period_type, period_start) DO UPDATE SET status='sending', sent_at=now()
             WHERE reports.status='sending' AND reports.sent_at < now() - interval '10 minutes'
           RETURNING 1""",
        user_id, period_type, period_start,
    )
    return r == 1


async def mark_report(conn, user_id: UUID, period_type: str, period_start: date, status: str) -> None:
    await conn.execute(
        "UPDATE reports SET status=$4, sent_at=now() WHERE user_id=$1 AND period_type=$2 AND period_start=$3",
        user_id, period_type, period_start, status,
    )


async def report_stats(conn) -> dict:
    r = await conn.fetchrow(
        """SELECT count(*) FILTER (WHERE status='sent' AND sent_at > now() - interval '1 day') AS sent_24h,
                  count(*) FILTER (WHERE status='failed' AND sent_at > now() - interval '7 days') AS failed_7d
           FROM reports WHERE period_type='daily'"""
    )
    return dict(r)


# ---------------- AI insights (kesh) ----------------
async def get_insight(conn, user_id: UUID, period_type: str, period_start: date) -> str | None:
    blob = await conn.fetchval(
        "SELECT text_enc FROM ai_insights WHERE user_id=$1 AND period_type=$2 AND period_start=$3",
        user_id, period_type, period_start,
    )
    return cipher().decrypt(blob, user_aad(user_id)) if blob else None


async def save_insight(conn, user_id: UUID, period_type: str, period_start: date, text: str) -> None:
    await conn.execute(
        """INSERT INTO ai_insights (user_id, period_type, period_start, text_enc) VALUES ($1,$2,$3,$4)
           ON CONFLICT (user_id, period_type, period_start) DO UPDATE SET text_enc=EXCLUDED.text_enc, created_at=now()""",
        user_id, period_type, period_start, cipher().encrypt(text, user_aad(user_id)),
    )


# ---------------- Pending parse (tasdiq kutayotgan) ----------------
async def save_pending(conn, user_id: UUID, payload: dict, source: str, source_key: str | None) -> UUID:
    return await conn.fetchval(
        "INSERT INTO pending_parses (user_id, payload_enc, source, source_key) VALUES ($1,$2,$3,$4) RETURNING id",
        user_id, cipher().encrypt(json.dumps(payload, default=str), user_aad(user_id)), source, source_key,
    )


async def pop_pending(conn, user_id: UUID, pending_id: UUID) -> tuple[dict, str, str | None] | None:
    r = await conn.fetchrow(
        "DELETE FROM pending_parses WHERE id=$1 AND user_id=$2 RETURNING payload_enc, source, source_key",
        pending_id, user_id,
    )
    if not r:
        return None
    return json.loads(cipher().decrypt(r["payload_enc"], user_aad(user_id))), r["source"], r["source_key"]


async def get_pending(conn, user_id: UUID, pending_id: UUID) -> dict | None:
    blob = await conn.fetchval("SELECT payload_enc FROM pending_parses WHERE id=$1 AND user_id=$2", pending_id, user_id)
    return json.loads(cipher().decrypt(blob, user_aad(user_id))) if blob else None


async def update_pending(conn, user_id: UUID, pending_id: UUID, payload: dict) -> None:
    await conn.execute(
        "UPDATE pending_parses SET payload_enc=$3 WHERE id=$1 AND user_id=$2",
        pending_id, user_id, cipher().encrypt(json.dumps(payload, default=str), user_aad(user_id)),
    )
