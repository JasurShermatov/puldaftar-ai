"""Telegramga xabar yuborish uchun yagona nuqta (servislar botni to'g'ridan-to'g'ri bilmaydi)."""
from __future__ import annotations

import asyncio
import logging
from typing import Any

log = logging.getLogger(__name__)
_bot = None


def set_bot(bot) -> None:
    global _bot
    _bot = bot


def bot():
    if _bot is None:
        raise RuntimeError("Bot hali ishga tushmagan")
    return _bot


async def send(chat_id: int, text: str, reply_markup: Any = None, retries: int = 3) -> bool:
    from aiogram.exceptions import TelegramBadRequest, TelegramForbiddenError, TelegramRetryAfter

    for attempt in range(retries):
        try:
            await bot().send_message(chat_id, text, reply_markup=reply_markup, disable_web_page_preview=True)
            return True
        except TelegramRetryAfter as e:
            await asyncio.sleep(e.retry_after + 0.5)
        except (TelegramForbiddenError, TelegramBadRequest):
            return False  # user botni bloklagan / chat topilmadi
        except Exception as e:  # noqa: BLE001
            log.warning("send failed (%s) attempt %d", type(e).__name__, attempt + 1)
            await asyncio.sleep(1.5 * (attempt + 1))
    return False


async def send_document(chat_id: int, filename: str, data: bytes, caption: str | None = None) -> bool:
    from aiogram.types import BufferedInputFile

    try:
        await bot().send_document(chat_id, BufferedInputFile(data, filename=filename), caption=caption)
        return True
    except Exception as e:  # noqa: BLE001
        log.warning("send_document failed: %s", type(e).__name__)
        return False


async def _with_retry(fn, retries: int = 3):
    """Telegram chaqiruvini retry bilan bajaradi. Natija yoki None (user botni bloklagan / xato)."""
    from aiogram.exceptions import TelegramBadRequest, TelegramForbiddenError, TelegramRetryAfter

    for attempt in range(retries):
        try:
            return await fn()
        except TelegramRetryAfter as e:
            await asyncio.sleep(e.retry_after + 0.5)
        except (TelegramForbiddenError, TelegramBadRequest):
            return None
        except Exception as e:  # noqa: BLE001
            log.warning("telegram call failed (%s) attempt %d", type(e).__name__, attempt + 1)
            await asyncio.sleep(1.5 * (attempt + 1))
    return None


async def send_photo(chat_id: int, photo, caption: str | None = None, reply_markup: Any = None) -> str | None:
    """photo: bytes yoki file_id. Qaytaradi: Telegram file_id (keyingi yuborishlarda qayta yuklamaslik uchun)."""
    from aiogram.types import BufferedInputFile

    media = BufferedInputFile(photo, filename="post.jpg") if isinstance(photo, (bytes, bytearray)) else photo
    msg = await _with_retry(lambda: bot().send_photo(chat_id, media, caption=caption, reply_markup=reply_markup))
    if msg is None:
        return None
    return msg.photo[-1].file_id if msg.photo else ""


async def copy(chat_id: int, from_chat_id: int, message_id: int, reply_markup: Any = None) -> bool:
    """Istalgan postni (rasm, video, matn, formatlash bilan) "forward" belgisisiz nusxalaydi."""
    res = await _with_retry(lambda: bot().copy_message(chat_id, from_chat_id, message_id, reply_markup=reply_markup))
    return res is not None
