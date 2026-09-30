"""Tranzaksiyalar. HAR BIR so'rov user_id bilan cheklangan (+ RLS ikkinchi himoya qatlami)."""
from __future__ import annotations

from datetime import datetime
from uuid import UUID

from app.core.security import cipher, user_aad

_SELECT = """SELECT t.id, t.type, t.amount, t.currency, t.category_id, t.description_enc, t.occurred_at,
                    t.source, t.confidence, t.created_at, t.updated_at,
                    c.key AS category_key, c.name AS category_name, c.emoji AS category_emoji
             FROM transactions t LEFT JOIN categories c ON c.id = t.category_id"""


def _row(r, user_id: UUID) -> dict:
    d = dict(r)
    d["description"] = cipher().decrypt(d.pop("description_enc"), user_aad(user_id))
    return d


async def insert(conn, user_id: UUID, *, type_: str, amount: int, category_id: int | None, description: str,
                 occurred_at: datetime, source: str, confidence: float | None, source_key: str | None) -> dict | None:
    """source_key bo'yicha idempotent: bir xil xabar qayta kelsa None qaytadi."""
    r = await conn.fetchrow(
        f"""WITH ins AS (
              INSERT INTO transactions (user_id, type, amount, category_id, description_enc, occurred_at, source,
                                        confidence, source_key)
              VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9)
              ON CONFLICT (user_id, source_key) WHERE source_key IS NOT NULL DO NOTHING
              RETURNING *)
            SELECT t.id, t.type, t.amount, t.currency, t.category_id, t.description_enc, t.occurred_at, t.source,
                   t.confidence, t.created_at, t.updated_at, c.key AS category_key, c.name AS category_name,
                   c.emoji AS category_emoji
            FROM ins t LEFT JOIN categories c ON c.id = t.category_id""",
        user_id, type_, amount, category_id, cipher().encrypt(description, user_aad(user_id)),
        occurred_at, source, confidence, source_key,
    )
    return _row(r, user_id) if r else None


async def get(conn, user_id: UUID, tx_id: UUID) -> dict | None:
    r = await conn.fetchrow(f"{_SELECT} WHERE t.id=$1 AND t.user_id=$2 AND t.deleted_at IS NULL", tx_id, user_id)
    return _row(r, user_id) if r else None


async def update(conn, user_id: UUID, tx_id: UUID, *, amount: int | None = None, category_id: int | None = None,
                 description: str | None = None, occurred_at: datetime | None = None,
                 type_: str | None = None) -> bool:
    desc_enc = cipher().encrypt(description, user_aad(user_id)) if description is not None else None
    res = await conn.execute(
        """UPDATE transactions SET amount=coalesce($3,amount), category_id=coalesce($4,category_id),
               description_enc=CASE WHEN $5::bool THEN $6 ELSE description_enc END,
               occurred_at=coalesce($7,occurred_at), type=coalesce($8,type), updated_at=now()
           WHERE id=$1 AND user_id=$2 AND deleted_at IS NULL""",
        tx_id, user_id, amount, category_id, description is not None, desc_enc, occurred_at, type_,
    )
    return res.endswith(" 1")


async def soft_delete(conn, user_id: UUID, tx_id: UUID) -> bool:
    res = await conn.execute(
        "UPDATE transactions SET deleted_at=now() WHERE id=$1 AND user_id=$2 AND deleted_at IS NULL", tx_id, user_id
    )
    return res.endswith(" 1")


async def restore(conn, user_id: UUID, tx_id: UUID) -> bool:
    res = await conn.execute(
        "UPDATE transactions SET deleted_at=NULL WHERE id=$1 AND user_id=$2 AND deleted_at IS NOT NULL", tx_id, user_id
    )
    return res.endswith(" 1")


async def list_range(conn, user_id: UUID, start: datetime, end: datetime, *, limit: int = 1000, offset: int = 0,
                     type_: str | None = None, category_id: int | None = None, asc: bool = False) -> list[dict]:
    order = "ASC" if asc else "DESC"
    rows = await conn.fetch(
        f"""{_SELECT} WHERE t.user_id=$1 AND t.deleted_at IS NULL AND t.occurred_at >= $2 AND t.occurred_at < $3
             AND ($4::text IS NULL OR t.type=$4) AND ($5::int IS NULL OR t.category_id=$5)
            ORDER BY t.occurred_at {order} LIMIT $6 OFFSET $7""",
        user_id, start, end, type_, category_id, limit, offset,
    )
    return [_row(r, user_id) for r in rows]


async def totals(conn, user_id: UUID, start: datetime, end: datetime) -> dict:
    r = await conn.fetchrow(
        """SELECT coalesce(sum(amount) FILTER (WHERE type='expense'),0)::bigint AS expense,
                  coalesce(sum(amount) FILTER (WHERE type='income'),0)::bigint AS income,
                  count(*) AS count
           FROM transactions WHERE user_id=$1 AND deleted_at IS NULL AND occurred_at >= $2 AND occurred_at < $3""",
        user_id, start, end,
    )
    d = dict(r)
    d["net"] = d["income"] - d["expense"]
    return d


async def by_category(conn, user_id: UUID, start: datetime, end: datetime, type_: str = "expense") -> list[dict]:
    rows = await conn.fetch(
        """SELECT c.id, c.key, c.name, c.emoji, sum(t.amount)::bigint AS total, count(*) AS count
           FROM transactions t LEFT JOIN categories c ON c.id=t.category_id
           WHERE t.user_id=$1 AND t.deleted_at IS NULL AND t.type=$4 AND t.occurred_at >= $2 AND t.occurred_at < $3
           GROUP BY c.id, c.key, c.name, c.emoji ORDER BY total DESC""",
        user_id, start, end, type_,
    )
    return [dict(r) for r in rows]


async def series(conn, user_id: UUID, tz_name: str, bucket: str, start: datetime, end: datetime) -> list[dict]:
    """Grafik uchun: har bir davr (kun/hafta/oy/yil) bo'yicha xarajat va daromad; bo'sh davrlar 0 bilan."""
    if bucket not in ("day", "week", "month", "year"):
        raise ValueError(bucket)
    step = {"day": "1 day", "week": "1 week", "month": "1 month", "year": "1 year"}[bucket]
    rows = await conn.fetch(
        f"""
        WITH b AS (
          SELECT generate_series(date_trunc('{bucket}', $3::timestamptz AT TIME ZONE $2::text),
                                 date_trunc('{bucket}', ($4::timestamptz - interval '1 second') AT TIME ZONE $2::text),
                                 interval '{step}') AS period
        ), agg AS (
          SELECT date_trunc('{bucket}', occurred_at AT TIME ZONE $2::text) AS period,
                 sum(amount) FILTER (WHERE type='expense')::bigint AS expense,
                 sum(amount) FILTER (WHERE type='income')::bigint AS income,
                 count(*) AS count
          FROM transactions
          WHERE user_id=$1 AND deleted_at IS NULL AND occurred_at >= $3 AND occurred_at < $4
          GROUP BY 1
        )
        SELECT b.period::date AS period, coalesce(a.expense,0) AS expense, coalesce(a.income,0) AS income,
               coalesce(a.count,0) AS count
        FROM b LEFT JOIN agg a USING (period) ORDER BY b.period
        """,
        user_id, tz_name, start, end,
    )
    return [dict(r) for r in rows]


async def first_date(conn, user_id: UUID) -> datetime | None:
    return await conn.fetchval(
        "SELECT min(occurred_at) FROM transactions WHERE user_id=$1 AND deleted_at IS NULL", user_id
    )


async def global_stats(conn) -> dict:
    """Admin uchun faqat agregatlar (maxfiylik: xom tavsiflar ko'rsatilmaydi)."""
    r = await conn.fetchrow(
        """SELECT count(*) FILTER (WHERE created_at > now() - interval '1 day') AS tx_24h,
                  count(*) AS tx_total,
                  count(*) FILTER (WHERE source='voice' AND created_at > now() - interval '1 day') AS voice_24h
           FROM transactions WHERE deleted_at IS NULL"""
    )
    return dict(r)


async def daily_counts(conn, days: int = 30) -> list[dict]:
    rows = await conn.fetch(
        """SELECT d::date AS day,
                  (SELECT count(*) FROM transactions t WHERE t.created_at >= d AND t.created_at < d + interval '1 day') AS tx,
                  (SELECT count(*) FROM users u WHERE u.created_at >= d AND u.created_at < d + interval '1 day') AS new_users
           FROM generate_series(date_trunc('day', now()) - make_interval(days => $1 - 1), date_trunc('day', now()), interval '1 day') d""",
        days,
    )
    return [dict(r) for r in rows]
