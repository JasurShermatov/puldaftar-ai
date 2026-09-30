"""Tranzaksiya domen servisi: matn → parse → validatsiya → saqlash / tasdiq / savol.

Bot ham, mini app ham faqat shu servis orqali yozadi (logika handler ichiga aralashmaydi).
"""
from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from datetime import datetime
from uuid import UUID

from app.core.timeutil import local_now
from app.db.database import db
from app.domain.models import ParsedItem, User
from app.repositories import categories as catrepo
from app.repositories import system as sysrepo
from app.repositories import transactions as txrepo
from app.services.access import access_of
from app.services.parsing.local_parser import parse_local
from app.services.parsing.pipeline import parse_text

log = logging.getLogger(__name__)


@dataclass
class IngestOutcome:
    kind: str                                   # saved | pending | clarify | expired | duplicate | empty
    saved: list[dict] = field(default_factory=list)
    pending_id: UUID | None = None
    pending_items: list[dict] = field(default_factory=list)
    question: str | None = None
    amount_options: list[int] = field(default_factory=list)


def _aware(dt: datetime | None, tz_name: str) -> datetime | None:
    if dt is not None and dt.tzinfo is None:
        from app.core.timeutil import tz
        return dt.replace(tzinfo=tz(tz_name))
    return dt


async def _thresholds() -> tuple[float, float]:
    async with db.system_tx() as conn:
        cfg = await sysrepo.get_setting(conn, "ai")
    return float(cfg.get("auto_save_threshold", 0.85)), float(cfg.get("confirm_threshold", 0.60))


async def _resolve_category(conn, user_id: UUID, item: ParsedItem, cats: dict[str, dict]) -> int | None:
    learned = await catrepo.learned_category(conn, user_id, item.description) if item.description else None
    if learned:
        # o'rganilgan kategoriya tur bilan mos bo'lishi kerak
        for c in cats.values():
            if c["id"] == learned and c["type"] == item.type.value:
                return learned
    c = cats.get(item.category_key)
    if c and c["type"] == item.type.value:
        return c["id"]
    fallback = cats.get("other" if item.type.value == "expense" else "other_income")
    return fallback["id"] if fallback else None


async def save_items(user: User, items: list[ParsedItem], source: str, source_key: str | None) -> list[dict]:
    saved: list[dict] = []
    async with db.user_tx(user.id) as conn:
        cats = await catrepo.key_map(conn, user.id)
        for idx, it in enumerate(items):
            cat_id = await _resolve_category(conn, user.id, it, cats)
            row = await txrepo.insert(
                conn, user.id, type_=it.type.value, amount=it.amount, category_id=cat_id,
                description=it.description, occurred_at=it.occurred_at, source=source,
                confidence=it.confidence, source_key=f"{source_key}:{idx}" if source_key else None,
            )
            if row:
                saved.append(row)
    if saved:
        async with db.system_tx() as conn:
            await sysrepo.event(conn, "transaction_saved", user.id, {"n": len(saved), "source": source})
    return saved


async def ingest(user: User, text: str, *, source: str, source_key: str | None, force: bool = False) -> IngestOutcome:
    if not access_of(user).can_add:
        return IngestOutcome(kind="expired")

    async with db.user_tx(user.id) as conn:
        cats = await catrepo.key_map(conn, user.id)
    allowed = {k: c["type"] for k, c in cats.items()}

    result = await parse_text(text, user.timezone, allowed)   # tashqi AI chaqiruvi DB tranzaksiyasidan tashqarida
    auto_th, confirm_th = await _thresholds()

    if not result.items:
        out = IngestOutcome(kind="clarify", question=result.clarification_question,
                            amount_options=result.amount_options)
        if result.amount_options:
            value = result.amount_options[0] // 1000   # parser aniqlagan "yalang'och" son (masalan 800)
            async with db.user_tx(user.id) as conn:
                out.pending_id = await sysrepo.save_pending(
                    conn, user.id, {"kind": "amount", "text": text, "value": value}, source, source_key,
                )
        return out

    auto = [i for i in result.items if force or i.confidence >= auto_th]
    confirm = [i for i in result.items if not force and confirm_th <= i.confidence < auto_th]
    too_low = [i for i in result.items if not force and i.confidence < confirm_th]

    out = IngestOutcome(kind="saved")
    if auto:
        out.saved = await save_items(user, auto, source, source_key)
        if not out.saved and source_key:
            out.kind = "duplicate"
    if confirm:
        payload = {"kind": "confirm", "items": [i.model_dump(mode="json") for i in confirm]}
        async with db.user_tx(user.id) as conn:
            out.pending_id = await sysrepo.save_pending(conn, user.id, payload, source,
                                                        f"{source_key}:c" if source_key else None)
        out.pending_items = []
        for i in confirm:
            c = cats.get(i.category_key) or {}
            out.pending_items.append({**i.model_dump(mode="json"), "category_name": c.get("name", "Boshqa"),
                                      "category_emoji": c.get("emoji", "•")})
        out.question = result.clarification_question
        out.kind = "pending" if not out.saved else "saved"
    if too_low:
        q = result.clarification_question or "Ba'zi qismini yaxshi tushunmadim. Summani va nimaga ketganini aniqroq ayting."
        if not auto and not confirm:
            out.kind = "clarify"
        out.question = out.question or q
    return out


async def confirm_pending(user: User, pending_id: UUID) -> list[dict]:
    async with db.user_tx(user.id) as conn:
        popped = await sysrepo.pop_pending(conn, user.id, pending_id)
    if not popped:
        return []
    payload, source, source_key = popped
    if payload.get("kind") != "confirm":
        return []
    items = [ParsedItem(**i) for i in payload["items"]]
    return await save_items(user, items, source, source_key)


async def cancel_pending(user: User, pending_id: UUID) -> None:
    async with db.user_tx(user.id) as conn:
        await sysrepo.pop_pending(conn, user.id, pending_id)


async def choose_amount(user: User, pending_id: UUID, amount: int) -> IngestOutcome:
    """"Reklama 800" → user tugmadan summani tanladi. Qayta so'ramaslik uchun item to'g'ridan-to'g'ri quriladi:
    noaniq son matndan olib tashlanadi, qolgan matndan tur/kategoriya/sana/izoh deterministik aniqlanadi."""
    async with db.user_tx(user.id) as conn:
        popped = await sysrepo.pop_pending(conn, user.id, pending_id)
    if not popped or amount <= 0:
        return IngestOutcome(kind="empty")
    payload, source, source_key = popped
    if not access_of(user).can_add:
        return IngestOutcome(kind="expired")
    text, value = payload.get("text", ""), payload.get("value")
    if value is not None:
        text = re.sub(rf"(?<![\d.,]){int(value)}(?![\d.,])", " ", text, count=1)
    probe = parse_local(f"{text} 1000000", user.timezone)       # vaqtinchalik summa — faqat kontekst uchun
    if probe.items:
        item = probe.items[0].model_copy(update={"amount": amount, "confidence": 1.0})
    else:
        item = ParsedItem(type="expense", amount=amount, category_key="other", description=text.strip()[:40],
                          occurred_at=local_now(user.timezone), confidence=1.0)
    saved = await save_items(user, [item], source, source_key)
    return IngestOutcome(kind="saved" if saved else "duplicate", saved=saved)


async def recategorize(user: User, tx_id: UUID, category_id: int) -> dict | None:
    async with db.user_tx(user.id) as conn:
        tx = await txrepo.get(conn, user.id, tx_id)
        if not tx:
            return None
        cats = {c["id"]: c for c in await catrepo.list_for_user(conn, user.id)}
        cat = cats.get(category_id)
        if not cat:
            return None
        await txrepo.update(conn, user.id, tx_id, category_id=category_id, type_=cat["type"])
        if tx["description"]:
            await catrepo.learn(conn, user.id, tx["description"], category_id)
        tx = await txrepo.get(conn, user.id, tx_id)
    async with db.system_tx() as conn:
        await sysrepo.event(conn, "transaction_corrected", user.id)
    return tx


async def update_tx(user: User, tx_id: UUID, *, amount: int | None = None, category_id: int | None = None,
                    description: str | None = None, occurred_at: datetime | None = None) -> dict | None:
    async with db.user_tx(user.id) as conn:
        tx = await txrepo.get(conn, user.id, tx_id)
        if not tx:
            return None
        type_ = None
        if category_id is not None:
            cats = {c["id"]: c for c in await catrepo.list_for_user(conn, user.id)}
            if category_id not in cats:
                return None
            type_ = cats[category_id]["type"]
        occurred_at = _aware(occurred_at, user.timezone)
        if occurred_at and occurred_at > local_now(user.timezone):
            occurred_at = None
        await txrepo.update(conn, user.id, tx_id, amount=amount, category_id=category_id,
                            description=description, occurred_at=occurred_at, type_=type_)
        if category_id is not None and (description or tx["description"]):
            await catrepo.learn(conn, user.id, description or tx["description"], category_id)
        return await txrepo.get(conn, user.id, tx_id)


async def delete_tx(user: User, tx_id: UUID) -> bool:
    async with db.user_tx(user.id) as conn:
        ok = await txrepo.soft_delete(conn, user.id, tx_id)
    if ok:
        async with db.system_tx() as conn:
            await sysrepo.event(conn, "transaction_deleted", user.id)
    return ok


async def add_manual(user: User, *, type_: str, amount: int, category_id: int, description: str,
                     occurred_at: datetime | None) -> dict | None:
    if not access_of(user).can_add:
        return None
    now = local_now(user.timezone)
    occurred_at = _aware(occurred_at, user.timezone)
    occ = occurred_at if occurred_at and occurred_at <= now else now
    async with db.user_tx(user.id) as conn:
        cats = {c["id"]: c for c in await catrepo.list_for_user(conn, user.id)}
        if category_id not in cats:
            return None
        return await txrepo.insert(conn, user.id, type_=cats[category_id]["type"], amount=amount,
                                   category_id=category_id, description=description, occurred_at=occ,
                                   source="manual", confidence=1.0, source_key=None)
