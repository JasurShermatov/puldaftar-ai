from __future__ import annotations

from uuid import UUID


async def create_pending(conn, user_id: UUID, plan: dict) -> tuple[dict, bool]:
    """Userda bitta pending ariza bo'ladi (unique index). Boshqa tarif tanlasa — mavjud ariza shu tarifga
    o'zgartiriladi. Qaytaradi: (row, yangi_yaratildimi)."""
    cols = "id, user_id, plan_code, amount, days, status, created_at"
    r = await conn.fetchrow(
        f"""INSERT INTO payment_requests (user_id, plan_code, amount, days) VALUES ($1,$2,$3,$4)
            ON CONFLICT (user_id) WHERE status='pending' DO NOTHING
            RETURNING {cols}""",
        user_id, plan["code"], plan["price"], plan["days"],
    )
    if r:
        return dict(r), True
    r = await conn.fetchrow(
        f"""UPDATE payment_requests SET plan_code=$2, amount=$3, days=$4
            WHERE user_id=$1 AND status='pending' RETURNING {cols}""",
        user_id, plan["code"], plan["price"], plan["days"],
    )
    return dict(r), False


async def get_for_update(conn, req_id: UUID) -> dict | None:
    r = await conn.fetchrow("SELECT * FROM payment_requests WHERE id=$1 FOR UPDATE", req_id)
    return dict(r) if r else None


async def decide(conn, req_id: UUID, status: str, admin_tg_id: int, note: str | None = None) -> None:
    await conn.execute(
        "UPDATE payment_requests SET status=$2, decided_at=now(), decided_by=$3, note=$4 WHERE id=$1",
        req_id, status, admin_tg_id, note,
    )


async def list_requests(conn, status: str | None, limit: int = 50, offset: int = 0) -> list[dict]:
    rows = await conn.fetch(
        """SELECT p.id, p.user_id, p.plan_code, pl.name AS plan_name, p.amount, p.days, p.status, p.note,
                  p.created_at, p.decided_at, p.decided_by,
                  u.telegram_id, u.username, u.first_name, u.pro_until,
                  (SELECT count(*) FROM payment_requests x WHERE x.user_id=p.user_id AND x.status='approved') AS approved_before
           FROM payment_requests p JOIN users u ON u.id=p.user_id LEFT JOIN plans pl ON pl.code=p.plan_code
           WHERE ($1::text IS NULL OR p.status=$1)
           ORDER BY p.created_at DESC LIMIT $2 OFFSET $3""",
        status, limit, offset,
    )
    return [dict(r) for r in rows]


async def stats(conn) -> dict:
    r = await conn.fetchrow(
        """SELECT count(*) FILTER (WHERE status='pending') AS pending,
                  count(*) FILTER (WHERE status='approved' AND decided_at > date_trunc('month', now())) AS approved_month,
                  coalesce(sum(amount) FILTER (WHERE status='approved' AND decided_at > date_trunc('month', now())),0)::bigint AS revenue_month,
                  coalesce(sum(amount) FILTER (WHERE status='approved'),0)::bigint AS revenue_total
           FROM payment_requests"""
    )
    return dict(r)
