"""Ommaviy xabar (reklama, chegirma e'lonlari): matn, rasm+matn, tugma, yoki botdagi istalgan postni nusxalash.

Fonda yuboriladi (Telegram limiti ~30 xabar/sek — biz ~22/sek), natija broadcasts jadvalida,
tugagach adminga hisobot keladi. Bloklangan userlarga yuborilmaydi.
"""
from __future__ import annotations

import asyncio
import html
import logging
from typing import Any, Awaitable, Callable

from app.db.database import db
from app.repositories import system as sysrepo
from app.services import notifier

log = logging.getLogger(__name__)
_tasks: set[asyncio.Task] = set()

SEGMENTS = {
    "all": "TRUE",
    "pro": "pro_until > now()",
    "trial": "trial_ends_at > now() AND (pro_until IS NULL OR pro_until <= now())",
    "expired": "trial_ends_at <= now() AND (pro_until IS NULL OR pro_until <= now())",
    "active7": "last_active_at > now() - interval '7 days'",
    "inactive7": "last_active_at <= now() - interval '7 days'",
}
SEGMENT_LABELS = {"all": "Hammaga", "pro": "PRO", "trial": "Sinovdagilar", "expired": "Muddati tugaganlar",
                  "active7": "Faol (7 kun)", "inactive7": "Nofaol (7+ kun)", "self": "Faqat o'zimga (test)"}


_ALLOWED_TAGS = {"b", "strong", "i", "em", "u", "ins", "s", "strike", "del", "a", "code", "pre", "tg-spoiler",
                 "blockquote", "span"}


_TAG_NAMES = "|".join(sorted(_ALLOWED_TAGS, key=len, reverse=True))


def normalize_html(text: str) -> str:
    """Teg bo'lmagan "<" va "&" belgilarini xavfsiz ko'rinishga o'tkazadi ("5 < 10" kabi matnlar uchun)."""
    import re
    text = re.sub(r"&(?!#?\w+;)", "&amp;", text)
    return re.sub(rf"<(?!/?(?:{_TAG_NAMES})[\s>])", "&lt;", text)


def validate_html(text: str) -> str | None:
    """Telegram HTML xatosi bo'lsa — butun tarqatma yiqiladi. Oldindan tekshiramiz. Xato matnini qaytaradi."""
    from html.parser import HTMLParser

    stack: list[str] = []
    err: list[str] = []

    class P(HTMLParser):
        def handle_starttag(self, tag, attrs):
            if tag not in _ALLOWED_TAGS:
                err.append(f"<{tag}> tegi ruxsat etilmagan (faqat b, i, u, s, a, code)")
            stack.append(tag)

        def handle_endtag(self, tag):
            if not stack or stack[-1] != tag:
                err.append(f"</{tag}> yopilishi noto'g'ri")
            else:
                stack.pop()

    try:
        P(convert_charrefs=True).feed(text)
    except Exception:  # noqa: BLE001
        return "HTML noto'g'ri"
    if stack:
        err.append(f"<{stack[-1]}> yopilmagan")
    return err[0] if err else None


async def recipients(segment: str, admin_tg: int) -> list[int]:
    if segment == "self":
        return [admin_tg]
    cond = SEGMENTS.get(segment)
    if cond is None:
        raise ValueError("segment")
    async with db.system_tx() as conn:
        rows = await conn.fetch(f"SELECT telegram_id FROM users WHERE NOT is_blocked AND {cond}")
    return [r["telegram_id"] for r in rows]


async def count(segment: str, admin_tg: int) -> int:
    return len(await recipients(segment, admin_tg))


def button_markup(text: str | None, url: str | None):
    if not text or not url:
        return None
    from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup
    return InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text=text[:40], url=url)]])


async def _run(bc_id: int, admin_tg: int, ids: list[int], send_one: Callable[[int], Awaitable[bool]], label: str):
    sent = failed = 0
    for n, chat_id in enumerate(ids, 1):
        ok = await send_one(chat_id)
        sent += ok
        failed += not ok
        if n % 200 == 0:
            async with db.system_tx() as conn:
                await conn.execute("UPDATE broadcasts SET sent=$2, failed=$3 WHERE id=$1", bc_id, sent, failed)
        await asyncio.sleep(0.045)
    async with db.system_tx() as conn:
        await conn.execute("UPDATE broadcasts SET sent=$2, failed=$3, status='done', finished_at=now() WHERE id=$1",
                           bc_id, sent, failed)
    log.info("broadcast %s done %d/%d", bc_id, sent, len(ids))
    await notifier.send(admin_tg, f"📣 <b>Ommaviy xabar yakunlandi</b> ({html.escape(label)})\n"
                                  f"✅ Yetkazildi: <b>{sent}</b>\n❌ Yetmadi (botni bloklagan va h.k.): {failed}")


async def start(admin_tg: int, segment: str, kind: str, preview: str,
                send_one: Callable[[int], Awaitable[bool]], first_id: list[int] | None = None) -> dict[str, Any]:
    ids = await recipients(segment, admin_tg)
    async with db.system_tx() as conn:
        bc_id = await conn.fetchval(
            "INSERT INTO broadcasts (admin_tg_id, segment, kind, preview, total) VALUES ($1,$2,$3,$4,$5) RETURNING id",
            admin_tg, segment, kind, preview[:200], len(ids),
        )
        await sysrepo.audit(conn, admin_tg, "broadcast", None,
                            {"id": bc_id, "segment": segment, "kind": kind, "count": len(ids), "preview": preview[:80]})
    task = asyncio.create_task(_run(bc_id, admin_tg, ids, send_one, SEGMENT_LABELS.get(segment, segment)))
    _tasks.add(task)
    task.add_done_callback(_tasks.discard)
    return {"id": bc_id, "queued": len(ids)}


# ---------- Tayyor yuboruvchilar ----------

async def start_text(admin_tg: int, segment: str, text: str, button_text: str | None = None,
                     button_url: str | None = None) -> dict:
    markup = button_markup(button_text, button_url)

    async def one(chat_id: int) -> bool:
        return await notifier.send(chat_id, text, reply_markup=markup, retries=2)

    return await start(admin_tg, segment, "text", text, one)


async def start_photo(admin_tg: int, segment: str, photo: bytes, caption: str | None,
                      button_text: str | None = None, button_url: str | None = None) -> dict:
    """Rasm bir marta yuklanadi, keyin Telegram file_id qayta ishlatiladi (tez va trafik tejaladi)."""
    markup = button_markup(button_text, button_url)
    file_id: dict[str, str | None] = {"id": None}
    lock = asyncio.Lock()

    async def one(chat_id: int) -> bool:
        async with lock:
            if file_id["id"] is None:
                fid = await notifier.send_photo(chat_id, photo, caption=caption, reply_markup=markup)
                if fid:
                    file_id["id"] = fid
                return fid is not None
        return await notifier.send_photo(chat_id, file_id["id"], caption=caption, reply_markup=markup) is not None

    return await start(admin_tg, segment, "photo", caption or "[rasm]", one)


async def start_copy(admin_tg: int, segment: str, from_chat_id: int, message_id: int) -> dict:
    async def one(chat_id: int) -> bool:
        return await notifier.copy(chat_id, from_chat_id, message_id)

    return await start(admin_tg, segment, "copy", f"[bot posti #{message_id}]", one)


async def history(limit: int = 30) -> list[dict]:
    async with db.system_tx() as conn:
        rows = await conn.fetch("SELECT * FROM broadcasts ORDER BY id DESC LIMIT $1", limit)
    return [dict(r) for r in rows]
