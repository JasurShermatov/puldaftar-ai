"""Telegram webhook va health endpointlari."""
from __future__ import annotations

import asyncio
import hmac
import logging

from fastapi import APIRouter, Header, HTTPException, Request
from fastapi.responses import JSONResponse

from app.core.config import get_settings
from app.db.database import db

log = logging.getLogger(__name__)
router = APIRouter()
_tasks: set[asyncio.Task] = set()


@router.post("/webhooks/telegram", include_in_schema=False)
async def telegram_webhook(request: Request, x_telegram_bot_api_secret_token: str = Header(default="")):
    s = get_settings()
    if s.webhook_secret and not hmac.compare_digest(x_telegram_bot_api_secret_token, s.webhook_secret):
        raise HTTPException(403)
    from aiogram.types import Update

    bot, dp = request.app.state.bot, request.app.state.dp
    update = Update.model_validate(await request.json(), context={"bot": bot})
    # Telegram'ga darhol 200 qaytaramiz; ovoz/AI ishlovi fonda (webhook timeoutga tushmaydi)
    task = asyncio.create_task(dp.feed_update(bot, update))
    _tasks.add(task)
    task.add_done_callback(_tasks.discard)
    return JSONResponse({"ok": True})


@router.get("/health/live", include_in_schema=False)
async def live():
    return {"ok": True}


@router.get("/health/ready", include_in_schema=False)
async def ready():
    ok = await db.ping()
    return JSONResponse({"db": ok}, status_code=200 if ok else 503)
