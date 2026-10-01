"""Qarzlar. HAR BIR so'rov user_id bilan cheklangan (+ RLS). Ism va izoh shifrlangan."""
from __future__ import annotations

from datetime import datetime
from uuid import UUID

from app.core.security import cipher, user_aad

_COLS = """id, user_id, direction, amount, paid_amount, counterparty_enc, note_enc, occurred_at, due_at, status,
           paid_at, last_reminded_on, source, created_at, updated_at"""


def _row(r, user_id: UUID) -> dict:
    d = dict(r)
    c = cipher()
    d["counterparty"] = c.decrypt(d.pop("counterparty_enc"), user_aad(user_id)) or ""
    d["note"] = c.decrypt(d.pop("note_enc"), user_aad(user_id)) or ""
    d["remaining"] = max(0, d["amount"] - d["paid_amount"])
    return d


async def insert(conn, user_id: UUID, *, direction: str, amount: int, counterparty: str, note: str,
                 occurred_at: datetime, due_at: datetime | None, source: str, source_key: str | None) -> dict | None:
    c = cipher()
    r = await conn.fetchrow(
        f"""INSERT INTO debts (user_id, direction, amount, counterparty_enc, note_enc, occurred_at, due_at, source, source_key)
            VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9)
            ON CONFLICT (user_id, source_key) WHERE source_key IS NOT NULL DO NOTHING
            RETURNING {_COLS}""",
        user_id, direction, amount, c.encrypt(counterparty or "", user_aad(user_id)),
        c.encrypt(note or "", user_aad(user_id)), occurred_at, due_at, source, source_key,
    )
    return _row(r, user_id) if r else None


async def get(conn, user_id: UUID, debt_id: UUID) -> dict | None:
    r = await conn.fetchrow(f"SELECT {_COLS} FROM debts WHERE id=$1 AND user_id=$2", debt_id, user_id)
    return _row(r, user_id) if r else None


async def list_(conn, user_id: UUID, status: str | None = "open", limit: int = 200) -> list[dict]:
    rows = await conn.fetch(
        f"""SELECT {_COLS} FROM debts WHERE user_id=$1 AND ($2::text IS NULL OR status=$2)
            ORDER BY (status='open') DESC, due_at NULLS LAST, created_at DESC LIMIT $3""",
        user_id, status, limit,
    )
    return [_row(r, user_id) for r in rows]


async def update(conn, user_id: UUID, debt_id: UUID, *, amount: int | None = None, counterparty: str | None = None,
                 note: str | None = None, due_at: datetime | None = None, clear_due: bool = False) -> bool:
    c = cipher()
    res = await conn.execute(
        """UPDATE debts SET amount=coalesce($3,amount),
               counterparty_enc=CASE WHEN $4::bool THEN $5 ELSE counterparty_enc END,
               note_enc=CASE WHEN $6::bool THEN $7 ELSE note_enc END,
               due_at=CASE WHEN $8::bool THEN NULL WHEN $9::timestamptz IS NOT NULL THEN $9 ELSE due_at END,
               last_reminded_on=CASE WHEN $8::bool OR $9::timestamptz IS NOT NULL THEN NULL ELSE last_reminded_on END,
               updated_at=now()
           WHERE id=$1 AND user_id=$2""",
        debt_id, user_id, amount,
        counterparty is not None, c.encrypt(counterparty or "", user_aad(user_id)) if counterparty is not None else None,
        note is not None, c.encrypt(note or "", user_aad(user_id)) if note is not None else None,
        clear_due, due_at,
    )
    return res.endswith(" 1")


async def pay(conn, user_id: UUID, debt_id: UUID, amount: int | None) -> dict | None:
    """amount=None → to'liq yopiladi. Qisman bo'lsa paid_amount oshadi; yetsa status=paid."""
    r = await conn.fetchrow(
        f"""UPDATE debts SET
               paid_amount = LEAST(amount, CASE WHEN $3::bigint IS NULL THEN amount ELSE paid_amount + $3 END),
               status = CASE WHEN $3::bigint IS NULL OR paid_amount + $3 >= amount THEN 'paid' ELSE 'open' END,
               paid_at = CASE WHEN $3::bigint IS NULL OR paid_amount + $3 >= amount THEN now() ELSE paid_at END,
               updated_at = now()
            WHERE id=$1 AND user_id=$2 AND status='open'
            RETURNING {_COLS}""",
        debt_id, user_id, amount,
    )
    return _row(r, user_id) if r else None


async def reopen(conn, user_id: UUID, debt_id: UUID) -> bool:
    res = await conn.execute(
        "UPDATE debts SET status='open', paid_amount=0, paid_at=NULL, updated_at=now() WHERE id=$1 AND user_id=$2",
        debt_id, user_id,
    )
    return res.endswith(" 1")


async def delete(conn, user_id: UUID, debt_id: UUID) -> bool:
    res = await conn.execute("DELETE FROM debts WHERE id=$1 AND user_id=$2", debt_id, user_id)
    return res.endswith(" 1")


async def summary(conn, user_id: UUID) -> dict:
    r = await conn.fetchrow(
        """SELECT coalesce(sum(amount - paid_amount) FILTER (WHERE direction='given' AND status='open'),0)::bigint AS given_open,
                  coalesce(sum(amount - paid_amount) FILTER (WHERE direction='taken' AND status='open'),0)::bigint AS taken_open,
                  count(*) FILTER (WHERE status='open') AS open_count,
                  count(*) FILTER (WHERE status='open' AND due_at IS NOT NULL AND due_at < now()) AS overdue_count,
                  count(*) FILTER (WHERE status='open' AND due_at IS NOT NULL AND due_at >= now()
                                   AND due_at < now() + interval '3 days') AS due_soon_count,
                  min(due_at) FILTER (WHERE status='open' AND due_at IS NOT NULL) AS next_due
           FROM debts WHERE user_id=$1""",
        user_id,
    )
    d = dict(r)
    d["next_due"] = d["next_due"].isoformat() if d["next_due"] else None
    return d


async def due_for_reminder(conn, limit: int = 500) -> list[dict]:
    """(system) Eslatma vaqti kelgan ochiq qarzlar: muddatgacha 3 kun qolganda va undan keyin har kuni,
    muddati o'tganda — har kuni (7 kun), so'ng har 3 kunda. User lokal vaqtida 09:00 dan keyin, kuniga 1 marta."""
    rows = await conn.fetch(
        """
        WITH d AS (
          SELECT dd.id, dd.user_id, dd.direction, dd.amount, dd.paid_amount, dd.counterparty_enc, dd.note_enc,
                 dd.occurred_at, dd.due_at, dd.status, dd.paid_at, dd.last_reminded_on, dd.source, dd.created_at, dd.updated_at,
                 u.telegram_id, u.timezone,
                 (now() AT TIME ZONE u.timezone)::date AS today_l,
                 (dd.due_at AT TIME ZONE u.timezone)::date AS due_l,
                 (now() AT TIME ZONE u.timezone)::time AS now_t
          FROM debts dd JOIN users u ON u.id = dd.user_id
          WHERE dd.status='open' AND dd.due_at IS NOT NULL AND NOT u.is_blocked
        )
        SELECT * FROM d
        WHERE now_t >= time '09:00'
          AND (last_reminded_on IS NULL OR last_reminded_on < today_l)
          AND (
                (due_l - today_l) BETWEEN 0 AND 3
             OR ((today_l - due_l) BETWEEN 1 AND 7)
             OR ((today_l - due_l) > 7 AND (today_l - due_l) % 3 = 0)
          )
        LIMIT $1
        """,
        limit,
    )
    out = []
    for r in rows:
        d = _row({k: r[k] for k in r.keys() if k not in ("today_l", "due_l", "now_t")}, r["user_id"])
        d["days_left"] = (r["due_l"] - r["today_l"]).days
        out.append(d)
    return out


async def mark_reminded(conn, debt_id: UUID, day) -> None:
    await conn.execute("UPDATE debts SET last_reminded_on=$2 WHERE id=$1", debt_id, day)


def _name_key(s: str) -> str:
    from app.services.parsing.normalize import normalize
    n = normalize(s or "")
    for suf in ("ning", "ni", "ga", "dan", "ka", "qa"):
        if n.endswith(suf) and len(n) - len(suf) >= 3:
            n = n[: -len(suf)]
            break
    return n


def name_matches(a: str, b: str) -> bool:
    """Ismlar mosligi (lotin/kirill farqsiz, qo'shimchasiz, kichik imlo farqi bilan): Alisher ≈ Алишер ≈ Alisherjon."""
    x, y = _name_key(a), _name_key(b)
    if not x or not y:
        return False
    if x == y or x.startswith(y) or y.startswith(x):
        return True
    k = min(len(x), len(y), 5)
    return k >= 4 and x[:k] == y[:k]


async def candidates(conn, user_id: UUID, direction: str, counterparty: str) -> tuple[list[dict], list[dict]]:
    """(ism bo'yicha mos ochiq qarzlar, shu yo'nalishdagi barcha ochiq qarzlar)."""
    rows = [r for r in await list_(conn, user_id, "open") if r["direction"] == direction]
    named = [r for r in rows if counterparty and name_matches(r["counterparty"], counterparty)] if counterparty else []
    return named, rows


async def find_open_match(conn, user_id: UUID, direction: str, counterparty: str, amount: int | None) -> list[dict]:
    """Qaytarish uchun mos ochiq qarzlar (eski API): ism bo'yicha, bo'lmasa yagona ochiq qarz."""
    named, rows = await candidates(conn, user_id, direction, counterparty)
    if named:
        exact = [r for r in named if amount and r["remaining"] == amount]
        return exact if len(exact) == 1 else named
    if counterparty:
        return []
    return rows
