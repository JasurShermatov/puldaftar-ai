"""Bot va Dispatcher yig'ish."""
from __future__ import annotations

import logging

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.fsm.storage.base import BaseStorage
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.types import BotCommand, MenuButtonWebApp, WebAppInfo

from app.bot.handlers import admin, billing, entry, menu
from app.bot.keyboards import webapp_url
from app.bot.middlewares import IdempotencyMiddleware, ThrottleMiddleware, UserMiddleware
from app.core.config import get_settings

log = logging.getLogger(__name__)


def create_bot() -> Bot:
    return Bot(get_settings().bot_token, default=DefaultBotProperties(parse_mode=ParseMode.HTML))


def _storage() -> BaseStorage:
    url = get_settings().redis_url
    if url:
        from aiogram.fsm.storage.redis import RedisStorage
        return RedisStorage.from_url(url)
    return MemoryStorage()


def create_dispatcher() -> Dispatcher:
    dp = Dispatcher(storage=_storage())
    dp.update.outer_middleware(IdempotencyMiddleware())
    for observer in (dp.message, dp.callback_query):
        observer.outer_middleware(ThrottleMiddleware())
        observer.outer_middleware(UserMiddleware())
    # Tartib muhim: menyu/admin/billing tugmalari umumiy matn handleridan oldin
    dp.include_routers(menu.router, admin.router, billing.router, entry.router)
    return dp


COMMANDS = [
    BotCommand(command="start", description="Boshlash / menyu"),
    BotCommand(command="today", description="Bugungi hisobot"),
    BotCommand(command="week", description="Haftalik hisobot"),
    BotCommand(command="month", description="Oylik hisobot"),
    BotCommand(command="year", description="Yillik hisobot"),
    BotCommand(command="ai", description="AI tahlil"),
    BotCommand(command="export", description="Excel/CSV yuklab olish"),
    BotCommand(command="dashboard", description="Grafiklar"),
    BotCommand(command="plan", description="Obuna va to'lov"),
    BotCommand(command="settings", description="Sozlamalar"),
    BotCommand(command="help", description="Yordam"),
    BotCommand(command="delete_me", description="Ma'lumotlarimni o'chirish"),
]


async def configure_bot(bot: Bot) -> None:
    s = get_settings()
    try:
        await bot.set_my_commands(COMMANDS)
        await bot.set_chat_menu_button(menu_button=MenuButtonWebApp(text="📊 Dashboard", web_app=WebAppInfo(url=webapp_url())))
    except Exception as e:  # noqa: BLE001
        log.warning("bot configure failed: %s", type(e).__name__)
    if s.bot_mode == "webhook":
        await bot.set_webhook(
            url=f"{s.public_base_url.rstrip('/')}/webhooks/telegram",
            secret_token=s.webhook_secret or None,
            allowed_updates=["message", "callback_query"],
            drop_pending_updates=False,
            max_connections=80,
        )
        log.info("webhook set")
    else:
        await bot.delete_webhook(drop_pending_updates=False)
