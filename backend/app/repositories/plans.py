"""Tariflar — to'liq dinamik (yaratish, tahrirlash, o'chirish). Standart: 1 oylik / 3 oylik / 1 yillik."""
from __future__ import annotations

_COLS = "code, name, days, price, old_price, badge, sort, is_active"


async def list_plans(conn, active_only: bool = True) -> list[dict]:
    rows = await conn.fetch(
        f"SELECT {_COLS} FROM plans WHERE NOT archived AND ($1 = false OR is_active) ORDER BY sort, days", active_only
    )
    return [dict(r) for r in rows]


async def get(conn, code: str) -> dict | None:
    r = await conn.fetchrow(f"SELECT {_COLS} FROM plans WHERE code=$1 AND NOT archived", code)
    return dict(r) if r else None


async def update(conn, code: str, patch: dict) -> dict | None:
    allowed = {"name", "days", "price", "old_price", "badge", "is_active", "sort"}
    fields = {k: v for k, v in patch.items() if k in allowed}
    if not fields:
        return await get(conn, code)
    sets, args = [], [code]
    for k, v in fields.items():
        args.append(v)
        sets.append(f"{k}=${len(args)}")
    r = await conn.fetchrow(
        f"UPDATE plans SET {', '.join(sets)}, updated_at=now() WHERE code=$1 AND NOT archived RETURNING {_COLS}", *args
    )
    return dict(r) if r else None


async def create(conn, *, name: str, days: int, price: int, old_price: int | None, badge: str | None,
                 is_active: bool = True) -> dict:
    """Kod avtomatik: p_<kun>d, band bo'lsa p_<kun>d_2 ..."""
    base = f"p_{days}d"
    code, n = base, 1
    while await conn.fetchval("SELECT 1 FROM plans WHERE code=$1", code):
        n += 1
        code = f"{base}_{n}"
    sort = await conn.fetchval("SELECT coalesce(max(sort), 0) + 10 FROM plans")
    r = await conn.fetchrow(
        f"""INSERT INTO plans (code, name, days, price, old_price, badge, sort, is_active)
            VALUES ($1,$2,$3,$4,$5,$6,$7,$8) RETURNING {_COLS}""",
        code, name, days, price, old_price, badge, sort, is_active,
    )
    return dict(r)


async def delete(conn, code: str) -> str | None:
    """'deleted' — butunlay o'chirildi; 'archived' — to'lov tarixida bor, shuning uchun arxivlandi."""
    used = await conn.fetchval("SELECT 1 FROM payment_requests WHERE plan_code=$1 LIMIT 1", code)
    if used:
        r = await conn.execute("UPDATE plans SET archived=true, is_active=false, updated_at=now() WHERE code=$1 AND NOT archived", code)
        return "archived" if r.endswith(" 1") else None
    r = await conn.execute("DELETE FROM plans WHERE code=$1", code)
    return "deleted" if r.endswith(" 1") else None
