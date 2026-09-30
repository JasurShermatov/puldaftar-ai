"""asyncpg pool + xavfsiz kontekstlar.

Har bir so'rov/handler DB bilan faqat ikkita kontekstdan biri orqali ishlaydi:

* ``db.user_tx(user_id)``  — tranzaksiya ichida ``app.user_id`` o'rnatiladi. Postgres RLS
  shu userga tegishli bo'lmagan barcha qatorlarni yashiradi va yozishni taqiqlaydi.
* ``db.system_tx()``       — scheduler, admin, user lookup uchun (``app.system=on``).

``SET LOCAL`` (set_config(..., true)) faqat joriy tranzaksiyaga ta'sir qiladi, shuning uchun
pool'dagi ulanish boshqa so'rovga o'tganda kontekst "oqib" ketmaydi.
"""
from __future__ import annotations

import json
import logging
from contextlib import asynccontextmanager
from typing import AsyncIterator
from uuid import UUID

import asyncpg

from app.core.config import get_settings

log = logging.getLogger(__name__)


async def _init_conn(conn: asyncpg.Connection) -> None:
    await conn.set_type_codec("jsonb", encoder=json.dumps, decoder=json.loads, schema="pg_catalog")
    await conn.set_type_codec("json", encoder=json.dumps, decoder=json.loads, schema="pg_catalog")


class Database:
    def __init__(self) -> None:
        self._pool: asyncpg.Pool | None = None

    async def connect(self) -> None:
        s = get_settings()
        self._pool = await asyncpg.create_pool(
            dsn=s.database_url,
            min_size=s.db_pool_min,
            max_size=s.db_pool_max,
            init=_init_conn,
            command_timeout=30,
            max_inactive_connection_lifetime=300,
        )
        log.info("DB pool ready")

    async def close(self) -> None:
        if self._pool:
            await self._pool.close()

    @property
    def pool(self) -> asyncpg.Pool:
        if not self._pool:
            raise RuntimeError("DB ulanmagan")
        return self._pool

    @asynccontextmanager
    async def user_tx(self, user_id: UUID | str) -> AsyncIterator[asyncpg.Connection]:
        async with self.pool.acquire() as conn:
            async with conn.transaction():
                await conn.execute(
                    "SELECT set_config('app.user_id', $1, true), set_config('app.system', 'off', true)",
                    str(user_id),
                )
                yield conn

    @asynccontextmanager
    async def system_tx(self) -> AsyncIterator[asyncpg.Connection]:
        async with self.pool.acquire() as conn:
            async with conn.transaction():
                await conn.execute(
                    "SELECT set_config('app.system', 'on', true), set_config('app.user_id', '', true)"
                )
                yield conn

    async def ping(self) -> bool:
        try:
            async with self.pool.acquire() as conn:
                return await conn.fetchval("SELECT 1") == 1
        except Exception:  # noqa: BLE001
            return False


db = Database()
