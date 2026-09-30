"""Integratsion test: ikki user ma'lumotlari hech qachon aralashmasligi (RLS + repository).

Talab: ishlayotgan Postgres (docker compose up -d db && docker compose run --rm migrate)
Ishga tushirish:
    docker compose run --rm api pytest -q tests/test_isolation.py
TEST_DB_OK=1 bo'lmasa (yoki asyncpg yo'q bo'lsa) — skip qilinadi.
"""
import asyncio
import os
from datetime import datetime, timezone

import pytest

pytestmark = pytest.mark.skipif(os.getenv("TEST_DB_OK") != "1", reason="TEST_DB_OK=1 bilan ishga tushiring")


def test_users_cannot_see_each_other():
    asyncio.run(_scenario())


async def _scenario():
    from app.db.database import db
    from app.repositories import transactions as txrepo
    from app.repositories import users as userrepo

    await db.connect()
    try:
        async with db.system_tx() as conn:
            a, _ = await userrepo.create(conn, tg_id=900000001, username="a", first_name="A", language="uz",
                                         trial_days=7, role="user")
            b, _ = await userrepo.create(conn, tg_id=900000002, username="b", first_name="B", language="uz",
                                         trial_days=7, role="user")
        now = datetime.now(timezone.utc)
        async with db.user_tx(a.id) as conn:
            ta = await txrepo.insert(conn, a.id, type_="expense", amount=111, category_id=None, description="A-secret",
                                     occurred_at=now, source="text", confidence=1.0, source_key="t:a:1")
        async with db.user_tx(b.id) as conn:
            await txrepo.insert(conn, b.id, type_="expense", amount=222, category_id=None, description="B-secret",
                                occurred_at=now, source="text", confidence=1.0, source_key="t:b:1")

        # 1) B, A ning tranzaksiyasini ID bilan ham ololmaydi
        async with db.user_tx(b.id) as conn:
            assert await txrepo.get(conn, b.id, ta["id"]) is None
            assert await txrepo.get(conn, a.id, ta["id"]) is None            # user_id ni almashtirsa ham — RLS
            raw = await conn.fetch("SELECT amount FROM transactions")         # WHERE siz ham faqat o'ziniki
            assert [r["amount"] for r in raw] == [222]
            # 2) B, A nomidan yozolmaydi
            with pytest.raises(Exception):
                await conn.execute(
                    "INSERT INTO transactions (user_id,type,amount,occurred_at) VALUES ($1,'expense',1,now())", a.id)

        # 3) Idempotency: bir xil source_key ikkinchi marta yozilmaydi
        async with db.user_tx(a.id) as conn:
            dup = await txrepo.insert(conn, a.id, type_="expense", amount=111, category_id=None, description="x",
                                      occurred_at=now, source="text", confidence=1.0, source_key="t:a:1")
            assert dup is None

        # 4) Kontekstsiz ulanish hech narsa ko'rmaydi
        async with db.pool.acquire() as conn:
            assert await conn.fetchval("SELECT count(*) FROM transactions") == 0
    finally:
        async with db.system_tx() as conn:
            await conn.execute("DELETE FROM users WHERE telegram_id IN (900000001, 900000002)")
        await db.close()
