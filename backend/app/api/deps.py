"""FastAPI dependency'lar: Telegram initData orqali autentifikatsiya, admin tekshiruvi, rate limit."""
from __future__ import annotations

from fastapi import Depends, Header, HTTPException, Request, status

from app.core.config import get_settings
from app.core.security import InitDataError, validate_init_data
from app.domain.models import User
from app.services import ratelimit
from app.services.users import get_or_create


async def current_user(request: Request, authorization: str = Header(default="")) -> User:
    """Header: `Authorization: tma <Telegram.WebApp.initData>`.

    user_id HECH QACHON clientdan olinmaydi — faqat bot token bilan imzolangan initData dan.
    Shu sababli bir user boshqa userning ma'lumotini so'ray olmaydi.
    """
    s = get_settings()
    if not authorization.startswith("tma "):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "auth required")
    try:
        tg = validate_init_data(authorization[4:], s.bot_token, s.init_data_max_age_sec)
    except InitDataError as e:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, str(e)) from e
    if not await ratelimit.hit(f"api:{tg.id}", s.rate_limit_per_minute * 4):
        raise HTTPException(status.HTTP_429_TOO_MANY_REQUESTS, "Juda ko'p so'rov, biroz kuting")
    user, _ = await get_or_create(tg.id, tg.username, tg.first_name, tg.language_code)
    if user.is_blocked:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "blocked")
    request.state.user = user
    return user


async def admin_user(user: User = Depends(current_user)) -> User:
    if not user.is_superadmin:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "admin only")
    return user
