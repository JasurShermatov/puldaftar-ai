"""API + bot (webhook yoki polling) jarayoni.

    uvicorn app.main:app --host 0.0.0.0 --port 8000
"""
from __future__ import annotations

import asyncio
import logging
import time
import uuid
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, ORJSONResponse

from app.api.routes import admin as admin_routes
from app.api.routes import system as system_routes
from app.api.routes import user as user_routes
from app.bot.setup import configure_bot, create_bot, create_dispatcher
from app.core.config import get_settings
from app.core.logging import correlation_id, setup_logging
from app.db.database import db
from app.services import notifier, ratelimit

log = logging.getLogger("app")


@asynccontextmanager
async def lifespan(app: FastAPI):
    s = get_settings()
    setup_logging(s.log_level)
    await db.connect()
    await ratelimit.init_redis()
    bot, dp = create_bot(), create_dispatcher()
    notifier.set_bot(bot)
    app.state.bot, app.state.dp = bot, dp
    try:
        await configure_bot(bot)
    except Exception as e:  # noqa: BLE001  (Telegram yetib bo'lmasa ham API ishga tushsin)
        log.error("configure_bot failed: %s", type(e).__name__)
    polling_task = None
    if s.bot_mode == "polling":
        polling_task = asyncio.create_task(dp.start_polling(bot, handle_signals=False))
        log.info("bot polling started")
    yield
    if polling_task:
        if not polling_task.done():
            try:
                await dp.stop_polling()
            except RuntimeError:
                pass
        polling_task.cancel()
    await bot.session.close()
    await db.close()


def create_app() -> FastAPI:
    s = get_settings()
    app = FastAPI(
        title="Hisobchi AI API",
        version="1.0.0",
        default_response_class=ORJSONResponse,
        lifespan=lifespan,
        docs_url="/api/docs" if s.is_dev else None,
        redoc_url=None,
        openapi_url="/api/openapi.json" if s.is_dev else None,
    )
    app.add_middleware(
        CORSMiddleware,
        allow_origins=[s.public_base_url.rstrip("/")] + (["http://localhost:3000"] if s.is_dev else []),
        allow_methods=["GET", "POST", "PATCH", "DELETE"],
        allow_headers=["Authorization", "Content-Type"],
    )

    @app.middleware("http")
    async def request_context(request: Request, call_next):
        correlation_id.set(request.headers.get("x-request-id") or uuid.uuid4().hex[:12])
        t0 = time.perf_counter()
        response = await call_next(request)
        ms = (time.perf_counter() - t0) * 1000
        if ms > 1000 or response.status_code >= 500:
            log.warning("%s %s %s %.0fms", request.method, request.url.path, response.status_code, ms)
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["Referrer-Policy"] = "no-referrer"
        return response

    @app.exception_handler(Exception)
    async def unhandled(_: Request, exc: Exception):
        log.exception("unhandled: %s", type(exc).__name__)
        return JSONResponse({"detail": "server error"}, status_code=500)

    app.include_router(system_routes.router)
    app.include_router(user_routes.router)
    app.include_router(admin_routes.router)
    return app


app = create_app()
