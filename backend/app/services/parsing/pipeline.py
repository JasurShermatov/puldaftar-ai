"""Matn → tranzaksiyalar pipeline: LLM (bo'lsa) + deterministik parser + business validator.

Qoida: LLM natijasi hech qachon to'g'ridan-to'g'ri "haqiqat" emas.
* Schema validatsiya (pydantic) — noto'g'ri JSON → local parserga fallback.
* Summalar local parser topgan summalar bilan solishtiriladi; mos kelmasa confidence tushiriladi.
* Kelajak sana, 0/manfiy summa, noma'lum kategoriya — rad etiladi/tuzatiladi.
"""
from __future__ import annotations

import logging
from datetime import datetime, timedelta

from pydantic import ValidationError

from app.core.config import get_settings
from app.core.timeutil import tz
from app.domain.models import ParsedItem, ParseResult, TxType
from app.services.ai import openai_client as ai
from app.services.parsing.local_parser import parse_local
from app.services.parsing.prompts import PARSER_SCHEMA, PARSER_SYSTEM

log = logging.getLogger(__name__)


def _validate_items(raw_items: list[dict], tz_name: str, allowed: dict[str, str], now: datetime) -> list[ParsedItem]:
    out: list[ParsedItem] = []
    z = tz(tz_name)
    for r in raw_items:
        try:
            t = TxType(r["type"])
            amount = int(r["amount"])
            if amount <= 0:
                continue
            key = r.get("category_key") or ""
            if key not in allowed or allowed[key] != t.value:
                key = "other" if t == TxType.expense else "other_income"
            try:
                occ = datetime.fromisoformat(str(r.get("occurred_at")).replace("Z", "+00:00"))
                if occ.tzinfo is None:
                    occ = occ.replace(tzinfo=z)
            except ValueError:
                occ = now
            if occ > now + timedelta(minutes=5):   # kelajak sanaga ruxsat yo'q
                occ = now
            if occ < now - timedelta(days=400):
                occ = now
            out.append(ParsedItem(
                type=t, amount=amount, category_key=key,
                description=str(r.get("description") or "")[:80],
                occurred_at=occ, account_hint=r.get("account_hint"),
                confidence=max(0.0, min(1.0, float(r.get("confidence", 0.5)))),
            ))
        except (KeyError, ValueError, TypeError, ValidationError):
            continue
    return out


async def parse_text(text: str, tz_name: str, categories: dict[str, str], now: datetime | None = None) -> ParseResult:
    """categories: {key: type} — user uchun ruxsat etilgan kategoriyalar."""
    s = get_settings()
    now = now or datetime.now(tz(tz_name))
    text = text.strip()[: s.max_text_len]
    local = parse_local(text, tz_name, now)

    if not s.ai_enabled:
        return local

    try:
        cats = ", ".join(f"{k}({v})" for k, v in categories.items())
        user_msg = (
            f"today={now.date().isoformat()} now={now.isoformat(timespec='minutes')} timezone={tz_name}\n"
            f"categories: {cats}\n<data>\n{text}\n</data>"
        )
        data = await ai.chat_json(model=s.openai_parser_model, system=PARSER_SYSTEM, user=user_msg,
                                  schema=PARSER_SCHEMA, name="transactions")
        items = _validate_items(data.get("transactions") or [], tz_name, categories, now)
    except ai.AIUnavailable:
        return local
    except Exception as e:  # noqa: BLE001  (timeout, invalid JSON, provider down) → deterministik fallback
        log.warning("llm parser failed, fallback local: %s", type(e).__name__)
        return local

    # LLM "savol" deb hisoblasa va local ham aniq topmagan bo'lsa → savol
    if not items:
        if local.items and not data.get("needs_clarification"):
            return local
        return ParseResult(
            needs_clarification=True,
            clarification_question=data.get("clarification_question") or local.clarification_question
            or "Summani aniqlay olmadim. Qaytadan aniqroq aytib bering.",
            amount_options=local.amount_options,
            engine="llm",
        )

    # --- Summalarni deterministik parser bilan solishtirish (gallyutsinatsiyaga qarshi) ---
    local_amounts = [i.amount for i in local.items]
    if local_amounts:
        pool = list(local_amounts)
        for it in items:
            if it.amount in pool:
                pool.remove(it.amount)
            else:
                it.confidence = min(it.confidence, 0.7)
    # local "Reklama 800" deb birlik so'ragan bo'lsa, LLM taxminini avto-saqlamaymiz
    if local.amount_options and not local.items:
        for it in items:
            it.confidence = min(it.confidence, 0.7)
    # local kategoriya aniq topgan bo'lsa va LLM "other" desa — local'ni olamiz
    for it in items:
        if it.category_key in ("other", "other_income"):
            for li in local.items:
                if li.amount == it.amount and li.category_key not in ("other", "other_income") and li.type == it.type:
                    it.category_key = li.category_key
                    break

    return ParseResult(
        items=items,
        needs_clarification=bool(data.get("needs_clarification")) and any(i.confidence < 0.85 for i in items),
        clarification_question=data.get("clarification_question"),
        engine="llm+local",
    )
