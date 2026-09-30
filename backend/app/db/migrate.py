"""Oddiy, versiyalangan SQL migratsiya runner.

Ishga tushirish:  python -m app.db.migrate
* migrations/NNN_*.sql fayllarini tartib bilan bir marta qo'llaydi (schema_migrations jadvali).
* Ilova roli (DB_APP_ROLE) uchun minimal huquqlar beradi: u jadval egasi emas,
  shuning uchun RLS doim ishlaydi. audit_logs faqat INSERT/SELECT (o'zgartirib bo'lmaydi).
"""
from __future__ import annotations

import asyncio
import logging
import re
from pathlib import Path

import asyncpg

from app.core.config import get_settings

log = logging.getLogger("migrate")
MIGRATIONS_DIR = Path(__file__).parent / "migrations"
_ROLE_RE = re.compile(r"^[a-z_][a-z0-9_]{0,62}$")


async def run() -> None:
    s = get_settings()
    role = s.db_app_role
    if not _ROLE_RE.match(role):
        raise SystemExit("DB_APP_ROLE noto'g'ri")
    conn = await asyncpg.connect(s.migration_database_url)
    try:
        await conn.execute(
            "CREATE TABLE IF NOT EXISTS schema_migrations (version text PRIMARY KEY, applied_at timestamptz DEFAULT now())"
        )
        done = {r["version"] for r in await conn.fetch("SELECT version FROM schema_migrations")}
        for f in sorted(MIGRATIONS_DIR.glob("*.sql")):
            if f.name in done:
                continue
            log.warning("applying %s", f.name)
            async with conn.transaction():
                await conn.execute(f.read_text(encoding="utf-8"))
                await conn.execute("INSERT INTO schema_migrations(version) VALUES($1)", f.name)

        # --- ilova roli: bo'lmasa yaratiladi, bo'lsa paroli .env bilan moslanadi (idempotent) ---
        pwd = s.db_app_password.replace("'", "''")
        if not pwd:
            raise SystemExit("DB_APP_PASSWORD .env da bo'sh")
        await conn.execute(f"""
            DO $do$ BEGIN
              IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = '{role}') THEN
                CREATE ROLE {role} LOGIN PASSWORD '{pwd}' NOSUPERUSER NOBYPASSRLS NOCREATEDB NOCREATEROLE;
              ELSE
                ALTER ROLE {role} WITH LOGIN PASSWORD '{pwd}' NOSUPERUSER NOBYPASSRLS;
              END IF;
            END $do$;
        """)
        dbname = await conn.fetchval("SELECT current_database()")
        await conn.execute(f'GRANT CONNECT ON DATABASE "{dbname}" TO {role}')

        # --- huquqlar (idempotent) ---
        await conn.execute(f"""
            GRANT USAGE ON SCHEMA public TO {role};
            GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA public TO {role};
            REVOKE UPDATE, DELETE ON audit_logs FROM {role};
            REVOKE ALL ON schema_migrations FROM {role};
            GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA public TO {role};
            GRANT EXECUTE ON FUNCTION app_current_user(), app_is_system() TO {role};
        """)
        log.warning("migrations OK")
    finally:
        await conn.close()


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    asyncio.run(run())
