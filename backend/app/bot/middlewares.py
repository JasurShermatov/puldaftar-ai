"""Bot middleware'lari: idempotency, user yuklash/bloklash, rate limit."""
from __future__ import annotations

import logging
import uuid
from typing import Any, Awaitable, Callable

from aiogram import BaseMiddleware
from aiogram.types import CallbackQuery, Message, TelegramObject, Update

from app.bot.texts import uz as T
from app.core.config import get_settings
from app.core.logging import correlation_id
from app.db.database import db
from app.repositories import system as sysrepo
from app.services import ratelimit
from app.services.users import get_or_create

log = logging.getLogger(__name__)
Handler = Callable[[TelegramObject, dict[str, Any]], Awaitable[Any]]


class IdempotencyMiddleware(BaseMiddleware):
    """Telegram bir update'ni qayta yuborsa (webhook retry) — ikkinchi marta ishlanmaydi."""

    async def __call__(self, handler: Handler, event: Update, data: dict[str, Any]) -> Any:
        correlation_id.set(f"u{event.update_id}-{uuid.uuid4().hex[:6]}")
        async with db.system_tx() as conn:
            fresh = await sysrepo.claim_update(conn, f"tg:{event.update_id}")
        if not fresh:
            log.info("duplicate update skipped")
            return None
        return await handler(event, data)


class UserMiddleware(BaseMiddleware):
    async def __call__(self, handler: Handler, event: TelegramObject, data: dict[str, Any]) -> Any:
        tg_user = getattr(event, "from_user", None)
        if tg_user is None or tg_user.is_bot:
            return None
        user, created = await get_or_create(tg_user.id, tg_user.username, tg_user.first_name, tg_user.language_code)
        if user.is_blocked:
            if isinstance(event, Message):
                await event.answer(T.BLOCKED)
            elif isinstance(event, CallbackQuery):
                await event.answer(T.BLOCKED, show_alert=True)
            return None
        data["user"] = user
        data["user_created"] = created
        return await handler(event, data)


class ThrottleMiddleware(BaseMiddleware):
    async def __call__(self, handler: Handler, event: TelegramObject, data: dict[str, Any]) -> Any:
        tg_user = getattr(event, "from_user", None)
        if tg_user and not await ratelimit.hit(f"bot:{tg_user.id}", get_settings().rate_limit_per_minute):
            if isinstance(event, Message):
                await event.answer(T.TOO_FAST)
            elif isinstance(event, CallbackQuery):
                await event.answer(T.TOO_FAST)
            return None
        return await handler(event, data)
