from __future__ import annotations

from datetime import datetime, timedelta
from uuid import UUID

import asyncpg

from app.domain.models import User

_COLS = ("id, telegram_id, username, first_name, language, timezone, report_enabled, "
         "to_char(report_time, 'HH24:MI') AS report_time, role, is_blocked, trial_ends_at, pro_until, "
         "created_at, last_active_at")


def _to_user(r: asyncpg.Record | None) -> User | None:
    return User(**dict(r)) if r else None


async def get_by_tg(conn, tg_id: int) -> User | None:
    return _to_user(await conn.fetchrow(f"SELECT {_COLS} FROM users WHERE telegram_id=$1", tg_id))


async def get(conn, user_id: UUID) -> User | None:
    return _to_user(await conn.fetchrow(f"SELECT {_COLS} FROM users WHERE id=$1", user_id))


async def create(conn, *, tg_id: int, username: str | None, first_name: str | None, language: str,
                 trial_days: int, role: str) -> tuple[User, bool]:
    """(user, created). Parallel /start bo'lsa ham bitta user (ON CONFLICT)."""
    row = await conn.fetchrow(
        f"""INSERT INTO users (telegram_id, username, first_name, language, trial_ends_at, role)
            VALUES ($1,$2,$3,$4, now() + make_interval(days => $5), $6)
            ON CONFLICT (telegram_id) DO NOTHING
            RETURNING {_COLS}""",
        tg_id, username, first_name, language, trial_days, role,
    )
    if row:
        return _to_user(row), True
    return await get_by_tg(conn, tg_id), False


async def touch(conn, user_id: UUID, username: str | None, first_name: str | None, role: str | None = None) -> None:
    await conn.execute(
        """UPDATE users SET last_active_at=now(), username=coalesce($2, username),
               first_name=coalesce($3, first_name), role=coalesce($4, role)
           WHERE id=$1 AND last_active_at < now() - interval '30 seconds'""",
        user_id, username, first_name, role,
    )


async def update_settings(conn, user_id: UUID, *, report_enabled: bool | None = None,
                          report_time: str | None = None, timezone: str | None = None,
                          language: str | None = None) -> None:
    await conn.execute(
        """UPDATE users SET report_enabled=coalesce($2, report_enabled),
               report_time=coalesce($3::text::time, report_time), timezone=coalesce($4, timezone),
               language=coalesce($5, language) WHERE id=$1""",
        user_id, report_enabled, report_time, timezone, language,
    )


# ---------------- Admin ----------------

async def search(conn, q: str | None, status: str | None, limit: int, offset: int) -> tuple[list[dict], int]:
    where = ["TRUE"]
    args: list = []
    if q:
        q = q.strip().lstrip("@")
        if q.isdigit():
            args.append(int(q))
            where.append(f"telegram_id=${len(args)}")
        else:
            args.append(f"%{q}%")
            where.append(f"(username ILIKE ${len(args)} OR first_name ILIKE ${len(args)})")
    if status == "blocked":
        where.append("is_blocked")
    elif status == "pro":
        where.append("pro_until > now()")
    elif status == "trial":
        where.append("trial_ends_at > now() AND (pro_until IS NULL OR pro_until <= now())")
    elif status == "expired":
        where.append("trial_ends_at <= now() AND (pro_until IS NULL OR pro_until <= now())")
    w = " AND ".join(where)
    total = await conn.fetchval(f"SELECT count(*) FROM users WHERE {w}", *args)
    args += [limit, offset]
    rows = await conn.fetch(
        f"""SELECT {_COLS},
               (SELECT count(*) FROM transactions t WHERE t.user_id=users.id AND t.deleted_at IS NULL) AS tx_count
            FROM users WHERE {w} ORDER BY created_at DESC LIMIT ${len(args)-1} OFFSET ${len(args)}""",
        *args,
    )
    return [dict(r) for r in rows], total


async def set_blocked(conn, user_id: UUID, blocked: bool, reason: str | None) -> None:
    await conn.execute("UPDATE users SET is_blocked=$2, blocked_reason=$3 WHERE id=$1", user_id, blocked, reason)


async def extend_pro(conn, user_id: UUID, days: int) -> datetime:
    """Aktiv PRO bo'lsa ustiga qo'shadi, bo'lmasa hozirdan boshlaydi."""
    return await conn.fetchval(
        """UPDATE users SET pro_until = greatest(coalesce(pro_until, now()), now()) + make_interval(days => $2)
           WHERE id=$1 RETURNING pro_until""",
        user_id, days,
    )


async def revoke_pro(conn, user_id: UUID) -> None:
    await conn.execute("UPDATE users SET pro_until=NULL WHERE id=$1", user_id)


async def extend_trial(conn, user_id: UUID, days: int) -> datetime:
    return await conn.fetchval(
        """UPDATE users SET trial_ends_at = greatest(trial_ends_at, now()) + make_interval(days => $2)
           WHERE id=$1 RETURNING trial_ends_at""",
        user_id, days,
    )


async def set_role(conn, user_id: UUID, role: str) -> None:
    await conn.execute("UPDATE users SET role=$2 WHERE id=$1", user_id, role)


async def delete(conn, user_id: UUID) -> None:
    """Hard delete: CASCADE barcha tranzaksiya, kategoriya, hisobot va h.k.ni o'chiradi.
    Faqat Telegram ID ning HMAC hash'i qoladi — qayta ro'yxatdan o'tganda trial qayta berilmasligi uchun."""
    tg_id = await conn.fetchval("SELECT telegram_id FROM users WHERE id=$1", user_id)
    if tg_id is not None:
        await conn.execute("INSERT INTO trial_guard (tg_hash) VALUES ($1) ON CONFLICT DO NOTHING", tg_guard_hash(tg_id))
    await conn.execute("DELETE FROM users WHERE id=$1", user_id)


def tg_guard_hash(tg_id: int) -> str:
    from app.core.security import phrase_hash
    return phrase_hash("trial", str(tg_id))


async def had_trial_before(conn, tg_id: int) -> bool:
    return bool(await conn.fetchval("SELECT 1 FROM trial_guard WHERE tg_hash=$1", tg_guard_hash(tg_id)))


async def due_reports(conn, limit: int = 500) -> list[asyncpg.Record]:
    """Hisobot vaqti kelgan userlar (bugun) + 2 soat ichida o'tkazib yuborilgan kechagilar (catch-up)."""
    return await conn.fetch(
        """
        WITH l AS (
          SELECT u.id, u.telegram_id, u.timezone, u.report_time, u.created_at,
                 (now() AT TIME ZONE u.timezone) AS lnow
          FROM users u
          WHERE u.report_enabled AND NOT u.is_blocked
        )
        SELECT id, telegram_id, timezone, lnow::date AS day FROM l
        WHERE lnow::time >= report_time
          AND NOT EXISTS (SELECT 1 FROM reports r WHERE r.user_id=l.id AND r.period_type='daily' AND r.period_start=lnow::date
                           AND (r.status <> 'sending' OR r.sent_at > now() - interval '10 minutes'))
        UNION ALL
        SELECT id, telegram_id, timezone, (lnow::date - 1) AS day FROM l
        WHERE lnow::time < time '02:00'
          AND created_at < ((lnow::date - 1) + report_time) AT TIME ZONE timezone
          AND NOT EXISTS (SELECT 1 FROM reports r WHERE r.user_id=l.id AND r.period_type='daily' AND r.period_start=lnow::date - 1
                           AND (r.status <> 'sending' OR r.sent_at > now() - interval '10 minutes'))
        LIMIT $1
        """,
        limit,
    )


_REMINDERS = {
    "trial_d2": ("trial_ends_at", "trial_ends_at BETWEEN now() + interval '1 day' AND now() + interval '2 days' AND (pro_until IS NULL OR pro_until < now())"),
    "trial_end": ("trial_ends_at", "trial_ends_at <= now() AND trial_ends_at > now() - interval '3 days' AND (pro_until IS NULL OR pro_until < now())"),
    "pro_d3": ("pro_until", "pro_until BETWEEN now() + interval '2 days' AND now() + interval '3 days'"),
    "pro_end": ("pro_until", "pro_until <= now() AND pro_until > now() - interval '3 days'"),
}


async def list_for_reminders(conn, kind: str) -> list[asyncpg.Record]:
    """Trial/PRO eslatmalari; har biri (user, kind, sana) bo'yicha bir marta."""
    col, cond = _REMINDERS[kind]
    return await conn.fetch(
        f"""SELECT id, telegram_id, {col}::date AS key_day, {col} AS ends_at
            FROM users WHERE NOT is_blocked AND {cond}
              AND NOT EXISTS (SELECT 1 FROM reports r WHERE r.user_id=users.id
                              AND r.period_type=$1 AND r.period_start={col}::date)
            LIMIT 500""",
        kind,
    )


async def stats(conn) -> dict:
    r = await conn.fetchrow(
        """SELECT count(*) AS users_total,
                  count(*) FILTER (WHERE created_at > now() - interval '1 day') AS users_new_24h,
                  count(*) FILTER (WHERE last_active_at > now() - interval '1 day') AS dau,
                  count(*) FILTER (WHERE last_active_at > now() - interval '7 days') AS wau,
                  count(*) FILTER (WHERE pro_until > now()) AS pro_active,
                  count(*) FILTER (WHERE trial_ends_at > now() AND (pro_until IS NULL OR pro_until <= now())) AS trial_active,
                  count(*) FILTER (WHERE trial_ends_at <= now() AND (pro_until IS NULL OR pro_until <= now())) AS expired,
                  count(*) FILTER (WHERE is_blocked) AS blocked
           FROM users"""
    )
    return dict(r)


def now_plus(days: int) -> datetime:
    from app.core.timeutil import now_utc
    return now_utc() + timedelta(days=days)
