"""Matn → yozuvlar pipeline: LLM (bo'lsa) + deterministik parser + business validator.

Qoida: LLM natijasi hech qachon to'g'ridan-to'g'ri "haqiqat" emas.
* Schema validatsiya (pydantic) — noto'g'ri JSON → local parserga fallback.
* Summalar local parser topgan summalar bilan solishtiriladi; mos kelmasa confidence tushiriladi.
* Kelajak sana, 0/manfiy summa, noma'lum kategoriya — rad etiladi/tuzatiladi.
* Qarz so'zi aniq bo'lsa (local qarz topdi) — LLM uni xarajat deb yuborsa ham qarz sifatida qoladi.
"""
from __future__ import annotations

import logging
from datetime import date, datetime, time, timedelta

from pydantic import ValidationError

from app.core.config import get_settings
from app.core.timeutil import tz
from app.domain.models import ParsedDebt, ParsedItem, ParsedRepayment, ParseResult, TxType
from app.services.ai import openai_client as ai
from app.services.parsing.local_parser import parse_local
from app.services.parsing.prompts import PARSER_SCHEMA, PARSER_SYSTEM

log = logging.getLogger(__name__)
_DEBT_KINDS = {"debt_given": "given", "debt_taken": "taken"}
_REPAY_KINDS = {"debt_repaid_to_me": "given", "debt_repaid_by_me": "taken"}


def _parse_dt(raw, z, now: datetime) -> datetime:
    try:
        occ = datetime.fromisoformat(str(raw).replace("Z", "+00:00"))
        if occ.tzinfo is None:
            occ = occ.replace(tzinfo=z)
    except (ValueError, TypeError):
        return now
    if occ > now + timedelta(minutes=5) or occ < now - timedelta(days=400):   # kelajak/juda eski sanaga ruxsat yo'q
        return now
    return occ


def _parse_due(raw, z, now: datetime) -> datetime | None:
    if not raw:
        return None
    try:
        d = date.fromisoformat(str(raw)[:10])
    except ValueError:
        return None
    if d < now.date() or d > now.date() + timedelta(days=3650):
        return None
    return datetime.combine(d, time(12, 0), tzinfo=z)


def _conf(r: dict) -> float:
    try:
        return max(0.0, min(1.0, float(r.get("confidence", 0.5))))
    except (TypeError, ValueError):
        return 0.5


def _validate(raw_items: list[dict], tz_name: str, allowed: dict[str, str], now: datetime) -> ParseResult:
    out = ParseResult(engine="llm")
    z = tz(tz_name)
    for r in raw_items:
        try:
            kind = str(r.get("kind") or "expense")
            amount = r.get("amount")
            amount = int(amount) if amount is not None else None
            who = (str(r.get("counterparty") or "").strip())[:40]
            desc = str(r.get("description") or "")[:80]
            occ = _parse_dt(r.get("occurred_at"), z, now)
            if kind in _REPAY_KINDS:
                if amount is not None and amount <= 0:
                    amount = None
                out.repayments.append(ParsedRepayment(direction=_REPAY_KINDS[kind], amount=amount,
                                                      counterparty=who, confidence=_conf(r)))
                continue
            if amount is None or amount <= 0:
                continue
            if kind in _DEBT_KINDS:
                out.debts.append(ParsedDebt(direction=_DEBT_KINDS[kind], amount=amount, counterparty=who,
                                            note=desc[:60], occurred_at=occ, due_at=_parse_due(r.get("due_at"), z, now),
                                            confidence=_conf(r)))
                continue
            t = TxType.income if kind == "income" else TxType.expense
            key = r.get("category_key") or ""
            if key not in allowed or allowed[key] != t.value:
                key = "other" if t == TxType.expense else "other_income"
            out.items.append(ParsedItem(
                type=t, amount=amount, category_key=key, description=desc, occurred_at=occ,
                account_hint=r.get("account_hint") if r.get("account_hint") in ("card", "cash") else None,
                confidence=_conf(r),
            ))
        except (KeyError, ValueError, TypeError, ValidationError):
            continue
    return out


async def parse_text(text: str, tz_name: str, categories: dict[str, str], now: datetime | None = None,
                     *, source: str = "text") -> ParseResult:
    """categories: {key: type} — user uchun ruxsat etilgan kategoriyalar. source: text | voice."""
    s = get_settings()
    now = now or datetime.now(tz(tz_name))
    text = text.strip()[: s.max_text_len]
    local = parse_local(text, tz_name, now)

    if not s.ai_enabled:
        return local

    try:
        cats = ", ".join(f"{k}({v})" for k, v in categories.items())
        src = "source=voice (matn ovozdan tanilgan — xatolarni kontekstdan tuzat)" if source == "voice" else "source=text"
        user_msg = (
            f"today={now.date().isoformat()} now={now.isoformat(timespec='minutes')} timezone={tz_name} "
            f"weekday={now.strftime('%A')} {src}\n"
            f"categories: {cats}\n<data>\n{text}\n</data>"
        )
        data = await ai.chat_json(model=s.openai_parser_model, system=PARSER_SYSTEM, user=user_msg,
                                  schema=PARSER_SCHEMA, name="transactions")
        llm = _validate(data.get("transactions") or [], tz_name, categories, now)
    except ai.AIUnavailable:
        return local
    except Exception as e:  # noqa: BLE001  (timeout, invalid JSON, provider down) → deterministik fallback
        log.warning("llm parser failed, fallback local: %s", type(e).__name__)
        return local

    # --- Qarz qaytarish: local aniq topgan bo'lsa — local (deterministik) ustun ---
    if local.repayments:
        if llm.repayments:
            for lr, rr in zip(local.repayments, llm.repayments):
                if not lr.counterparty and rr.counterparty:
                    lr.counterparty = rr.counterparty
                if lr.amount is None and rr.amount:
                    lr.amount = rr.amount
        return local
    if llm.repayments and not llm.items and not llm.debts:
        llm.engine = "llm+local"
        return llm

    # LLM "savol" deb hisoblasa va local ham aniq topmagan bo'lsa → savol
    if llm.is_empty:
        if not local.is_empty and not data.get("needs_clarification"):
            return local
        return ParseResult(
            needs_clarification=True,
            clarification_question=data.get("clarification_question") or local.clarification_question
            or "Summani aniqlay olmadim. Qaytadan aniqroq aytib bering.",
            amount_options=local.amount_options,
            engine="llm",
        )

    # --- Summalarni deterministik parser bilan solishtirish (gallyutsinatsiyaga qarshi) ---
    local_amounts = [i.amount for i in local.items] + [d.amount for d in local.debts]
    if local_amounts:
        pool = list(local_amounts)
        for it in [*llm.items, *llm.debts]:
            if it.amount in pool:
                pool.remove(it.amount)
            else:
                it.confidence = min(it.confidence, 0.7)
    # local "Reklama 800" deb birlik so'ragan bo'lsa, LLM taxminini avto-saqlamaymiz
    if local.amount_options and local.is_empty:
        for it in [*llm.items, *llm.debts]:
            it.confidence = min(it.confidence, 0.7)

    # --- Qarz: "qarz" so'zi bor (local qarz topdi), LLM esa xarajat/daromad dedi → local qarzini olamiz ---
    if local.debts and not llm.debts:
        llm_by_amount = {i.amount: i for i in llm.items}
        for d in local.debts:
            llm_by_amount.pop(d.amount, None)
        llm.items = list(llm_by_amount.values())
        llm.debts = list(local.debts)
    elif local.debts and llm.debts:
        # LLM ism/muddatni yaxshiroq topadi; bo'sh qoldirsa local'dan to'ldiramiz
        for ld in local.debts:
            for d in llm.debts:
                if d.amount == ld.amount:
                    if not d.counterparty and ld.counterparty:
                        d.counterparty = ld.counterparty
                    if d.due_at is None and ld.due_at is not None:
                        d.due_at = ld.due_at
                    if d.direction != ld.direction and ld.confidence >= 0.9:
                        d.direction = ld.direction      # "berdim"/"oldim" — deterministik aniqroq
                    break

    # local kategoriya aniq topgan bo'lsa va LLM "other" desa — local'ni olamiz
    for it in llm.items:
        if it.category_key in ("other", "other_income"):
            for li in local.items:
                if li.amount == it.amount and li.category_key not in ("other", "other_income") and li.type == it.type:
                    it.category_key = li.category_key
                    break
    # "Akmalga 2 mln berdim" — local topgan alternativ (qarz) tugmasini saqlab qolamiz
    if local.alt_debt and any(i.amount == local.alt_debt.amount for i in llm.items):
        llm.alt_debt = local.alt_debt
        for i in llm.items:
            if i.amount == local.alt_debt.amount:
                i.confidence = min(i.confidence, 0.65)

    llm.engine = "llm+local"
    low = any(i.confidence < 0.85 for i in [*llm.items, *llm.debts])
    llm.needs_clarification = bool(data.get("needs_clarification")) and low or (local.needs_clarification and low)
    llm.clarification_question = data.get("clarification_question") or local.clarification_question
    return llm
