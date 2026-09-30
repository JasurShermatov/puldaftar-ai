"""Superadmin amallari. Har bir amal audit_logs ga yoziladi (o'zgartirib bo'lmaydigan jurnal)."""
from __future__ import annotations

import asyncio
import html
import logging
from uuid import UUID

from app.core.timeutil import fmt_money, tz
from app.db.database import db
from app.repositories import payments as payrepo
from app.repositories import plans as planrepo
from app.repositories import system as sysrepo
from app.repositories import transactions as txrepo
from app.repositories import users as userrepo
from app.services import notifier

log = logging.getLogger(__name__)
_bg_tasks: set[asyncio.Task] = set()


async def block(admin_tg: int, user_id: UUID, blocked: bool, reason: str | None) -> bool:
    async with db.system_tx() as conn:
        u = await userrepo.get(conn, user_id)
        if not u or u.is_superadmin:
            return False
        await userrepo.set_blocked(conn, user_id, blocked, reason)
        await sysrepo.audit(conn, admin_tg, "user.block" if blocked else "user.unblock", user_id, {"reason": reason})
    if blocked:
        await notifier.send(u.telegram_id, "⛔️ Hisobingiz administrator tomonidan bloklandi."
                            + (f"\nSabab: {reason}" if reason else ""))
    else:
        await notifier.send(u.telegram_id, "✅ Hisobingiz blokdan chiqarildi. Xush kelibsiz!")
    return True


async def grant_pro(admin_tg: int, user_id: UUID, days: int) -> str | None:
    async with db.system_tx() as conn:
        u = await userrepo.get(conn, user_id)
        if not u:
            return None
        until = await userrepo.extend_pro(conn, user_id, days)
        await sysrepo.audit(conn, admin_tg, "user.pro_grant", user_id, {"days": days})
    s = until.astimezone(tz(u.timezone)).strftime("%d.%m.%Y")
    await notifier.send(u.telegram_id, f"🎁 Sizga <b>{days} kun</b> PRO berildi. Muddati: <b>{s}</b> gacha.")
    return s


async def grant_plan(admin_tg: int, user_id: UUID, plan_code: str) -> str | None:
    async with db.system_tx() as conn:
        plan = await planrepo.get(conn, plan_code)
        u = await userrepo.get(conn, user_id)
        if not plan or not u:
            return None
        until = await userrepo.extend_pro(conn, user_id, plan["days"])
        await sysrepo.audit(conn, admin_tg, "user.plan_grant", user_id, {"plan": plan_code, "days": plan["days"]})
    s = until.astimezone(tz(u.timezone)).strftime("%d.%m.%Y")
    await notifier.send(u.telegram_id, f"🎁 Sizga <b>{html.escape(plan['name'])}</b> PRO obuna ochildi!\n"
                                       f"Muddati: <b>{s}</b> gacha. Yoqimli foydalaning ✅")
    return s


async def revoke_pro(admin_tg: int, user_id: UUID) -> bool:
    async with db.system_tx() as conn:
        await userrepo.revoke_pro(conn, user_id)
        await sysrepo.audit(conn, admin_tg, "user.pro_revoke", user_id)
    return True


async def extend_trial(admin_tg: int, user_id: UUID, days: int) -> str | None:
    async with db.system_tx() as conn:
        u = await userrepo.get(conn, user_id)
        if not u:
            return None
        until = await userrepo.extend_trial(conn, user_id, days)
        await sysrepo.audit(conn, admin_tg, "user.trial_extend", user_id, {"days": days})
    return until.isoformat()


async def delete_user(admin_tg: int, user_id: UUID) -> bool:
    async with db.system_tx() as conn:
        u = await userrepo.get(conn, user_id)
        if not u or u.is_superadmin:
            return False
        await userrepo.delete(conn, user_id)
        await sysrepo.audit(conn, admin_tg, "user.delete", None, {"telegram_id": u.telegram_id})
    return True


async def user_detail(user_id: UUID) -> dict | None:
    """Maxfiylik: admin faqat agregatlarni ko'radi, tranzaksiya tavsiflarini emas."""
    async with db.system_tx() as conn:
        u = await userrepo.get(conn, user_id)
        if not u:
            return None
        tot = await conn.fetchrow(
            """SELECT count(*) AS tx_count,
                      coalesce(sum(amount) FILTER (WHERE type='expense'),0)::bigint AS expense_total,
                      coalesce(sum(amount) FILTER (WHERE type='income'),0)::bigint AS income_total,
                      max(created_at) AS last_tx_at
               FROM transactions WHERE user_id=$1 AND deleted_at IS NULL""",
            user_id,
        )
        pays = await conn.fetch(
            "SELECT id, amount, days, status, created_at, decided_at FROM payment_requests WHERE user_id=$1 ORDER BY created_at DESC LIMIT 20",
            user_id,
        )
        blocked_reason = await conn.fetchval("SELECT blocked_reason FROM users WHERE id=$1", user_id)
    return {"user": u.model_dump(mode="json"), "blocked_reason": blocked_reason, "totals": dict(tot),
            "payments": [dict(p) for p in pays]}


async def dashboard_stats() -> dict:
    async with db.system_tx() as conn:
        users = await userrepo.stats(conn)
        tx = await txrepo.global_stats(conn)
        pay = await payrepo.stats(conn)
        rep = await sysrepo.report_stats(conn)
        ev = await sysrepo.event_counts(conn, 24)
        daily = await txrepo.daily_counts(conn, 30)
    return {"users": users, "transactions": tx, "payments": pay, "reports": rep, "events_24h": ev,
            "daily": [{"day": d["day"].isoformat(), "tx": d["tx"], "new_users": d["new_users"]} for d in daily]}


def money(v: int) -> str:
    return fmt_money(v)
