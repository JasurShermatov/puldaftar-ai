from __future__ import annotations

from app.core.config import get_settings
from app.db.database import db
from app.domain.models import User
from app.repositories import system as sysrepo
from app.repositories import users as repo


async def get_or_create(tg_id: int, username: str | None, first_name: str | None,
                        language: str | None) -> tuple[User, bool]:
    """Telegram ID → user. Superadminlar faqat .env dagi SUPERADMIN_IDS dan belgilanadi (nechta ID — shuncha superadmin)."""
    s = get_settings()
    role = "superadmin" if tg_id in s.superadmin_ids else "user"
    async with db.system_tx() as conn:
        user = await repo.get_by_tg(conn, tg_id)
        if user:
            # Superadminlar FAQAT .env dagi SUPERADMIN_IDS ro'yxatidan: ro'yxatda bor — superadmin,
            # ro'yxatdan olib tashlansa — keyingi murojaatda oddiy userga aylanadi.
            await repo.touch(conn, user.id, username, first_name)
            if user.role != role:
                await repo.set_role(conn, user.id, role)
                user.role = role
            return user, False
        billing = await sysrepo.get_setting(conn, "billing")
        lang = "ru" if (language or "").startswith("ru") else "uz"
        trial_days = 0 if await repo.had_trial_before(conn, tg_id) else int(billing.get("trial_days", 7))
        user, created = await repo.create(
            conn, tg_id=tg_id, username=username, first_name=first_name, language=lang,
            trial_days=trial_days, role=role,
        )
        if created:
            await sysrepo.event(conn, "user_started", user.id)
        return user, created
