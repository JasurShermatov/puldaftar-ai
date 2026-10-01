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
from app.domain.models import ParsedDebt, ParsedItem, ParsedRepayment, User
from app.repositories import categories as catrepo
from app.repositories import debts as debtrepo
from app.repositories import system as sysrepo
from app.repositories import transactions as txrepo
from app.services import debts as debt_svc
from app.services.access import access_of
from app.services.parsing.local_parser import parse_local
from app.services.parsing.pipeline import parse_text

log = logging.getLogger(__name__)


@dataclass
class IngestOutcome:
    kind: str                                   # saved | pending | clarify | expired | duplicate | empty
    saved: list[dict] = field(default_factory=list)            # saqlangan tranzaksiyalar
    saved_debts: list[dict] = field(default_factory=list)      # saqlangan qarzlar
    repaid: list[dict] = field(default_factory=list)           # yopilgan/qisman qaytarilgan qarzlar
    repay_status: str | None = None                            # paid | partial | ambiguous | none
    pending_id: UUID | None = None
    pending_items: list[dict] = field(default_factory=list)    # tasdiq kutayotgan tranzaksiyalar (ko'rsatish uchun)
    pending_debts: list[dict] = field(default_factory=list)    # tasdiq kutayotgan qarzlar
    has_alt_debt: bool = False                                 # "🤝 Bu qarz" tugmasi kerakmi
    pending_kind: str | None = None                            # confirm | repay | repay_pick
    pending_repay: dict | None = None                          # repay: {who, remaining, amount, direction, debt_id}
    repay_options: list[dict] = field(default_factory=list)    # repay_pick: [{idx, debt_id, who, remaining, direction}]
    has_fallback: bool = False                                 # repay: "💸 Yo'q, oddiy yozuv" tugmasi kerakmi
    question: str | None = None
    amount_options: list[int] = field(default_factory=list)
    transcript: str | None = None

    @property
    def anything_saved(self) -> bool:
        return bool(self.saved or self.saved_debts or self.repaid)


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
                description=it.description, occurred_at=_aware(it.occurred_at, user.timezone), source=source,
                confidence=it.confidence, source_key=f"{source_key}:{idx}" if source_key else None,
            )
            if row:
                saved.append(row)
    if saved:
        async with db.system_tx() as conn:
            await sysrepo.event(conn, "transaction_saved", user.id, {"n": len(saved), "source": source})
    return saved


async def save_debts(user: User, debts: list[ParsedDebt], source: str, source_key: str | None) -> list[dict]:
    saved: list[dict] = []
    for idx, d in enumerate(debts):
        row = await debt_svc.create(user, d, source=source, source_key=f"{source_key}:d{idx}" if source_key else None)
        if row:
            saved.append(row)
    return saved


def _view_item(i: ParsedItem, cats: dict[str, dict]) -> dict:
    c = cats.get(i.category_key) or {}
    return {**i.model_dump(mode="json"), "category_name": c.get("name", "Boshqa"), "category_emoji": c.get("emoji", "•")}


async def ingest(user: User, text: str, *, source: str, source_key: str | None, force: bool = False) -> IngestOutcome:
    """Matn/ovoz → parse → (avto-saqlash | tasdiq so'rash | savol).

    Ishonchlilik: >= auto_th (odatda 0.85) — avtomatik saqlanadi; undan past bo'lsa (summa bo'lsa ham) —
    «✅ Tasdiqlash / ❌ Bekor» tugmalari bilan ko'rsatiladi; summa umuman topilmasa — savol.
    """
    if not access_of(user).can_add:
        return IngestOutcome(kind="expired")

    async with db.user_tx(user.id) as conn:
        cats = await catrepo.key_map(conn, user.id)
    allowed = {k: c["type"] for k, c in cats.items()}

    result = await parse_text(text, user.timezone, allowed, source=source)   # AI chaqiruvi DB tranzaksiyasidan tashqarida
    auto_th, _confirm_th = await _thresholds()

    # ---- Qarz qaytarildi: har doim tasdiq so'raymiz (mos qarzni topib ko'rsatamiz) ----
    if result.repayments:
        rep = result.repayments[0]
        hard = rep.confidence >= 0.7 or not result.items
        async with db.user_tx(user.id) as conn:
            named, all_dir = await debtrepo.candidates(conn, user.id, rep.direction, rep.counterparty)
        fallback = [i for i in result.items]            # "pulini berdim" kabi yumshoq holat uchun oddiy yozuv varianti
        if named or (not rep.counterparty and all_dir):
            cands = named or all_dir
            if hard or named:
                return await _pending_repay(user, cands, rep, fallback, source, source_key, cats)
        if not hard:
            # yumshoq holat, mos qarz yo'q → oddiy xarajat/daromad sifatida davom etadi
            result.repayments = []
        elif all_dir:
            # ism aytilgan, lekin mos kelmadi → shu yo'nalishdagi ochiq qarzlardan tanlatamiz
            return await _pending_repay(user, all_dir, rep, fallback, source, source_key, cats,
                                        question=f"«{rep.counterparty}» nomli ochiq qarz topilmadi. Qaysi qarz qaytarildi?")
        else:
            # yo'nalish adashgan bo'lishi mumkin: "Alisherni qarzini berdim" dedi, lekin ochiq qarz Alisher → menga
            opposite = "taken" if rep.direction == "given" else "given"
            async with db.user_tx(user.id) as conn:
                opp_named, _ = await debtrepo.candidates(conn, user.id, opposite, rep.counterparty)
            if opp_named:
                rep2 = ParsedRepayment(direction=opposite, amount=rep.amount, counterparty=rep.counterparty, confidence=0.6)
                return await _pending_repay(user, opp_named, rep2, fallback, source, source_key, cats)
            out = IngestOutcome(kind="saved", repay_status="none")
            if rep.amount:
                who = rep.counterparty
                if rep.direction == "given":
                    item = ParsedItem(type="income", amount=rep.amount, category_key="refund",
                                      description=f"{who} qarzini qaytardi".strip(), occurred_at=local_now(user.timezone),
                                      confidence=0.7)
                    q = "Bunday ochiq qarz yo'q. Qaytarilgan pul sifatida (daromad) yozaymi?"
                else:
                    item = ParsedItem(type="expense", amount=rep.amount, category_key="other",
                                      description=f"{who}ga qarz qaytardim".strip() if who else "qarz qaytardim",
                                      occurred_at=local_now(user.timezone), confidence=0.7)
                    q = "Bunday ochiq qarz yo'q. Xarajat sifatida yozaymi?"
                payload = {"kind": "confirm", "items": [item.model_dump(mode="json")], "debts": [], "alt_debt": None}
                async with db.user_tx(user.id) as conn:
                    out.pending_id = await sysrepo.save_pending(conn, user.id, payload, source,
                                                                f"{source_key}:c" if source_key else None)
                out.pending_items = [_view_item(item, cats)]
                out.pending_kind = "confirm"
                out.question = q
                out.kind = "pending"
                return out
            out.kind = "clarify"
            out.question = ("Hozircha ochiq qarzlaringiz yo'q. Yangi qarz uchun: «Jasurga 100 ming qarz berdim»")
            return out

    if result.is_empty:
        out = IngestOutcome(kind="clarify", question=result.clarification_question,
                            amount_options=result.amount_options)
        if result.amount_options:
            value = result.amount_options[0] // 1000   # parser aniqlagan "yalang'och" son (masalan 800)
            async with db.user_tx(user.id) as conn:
                out.pending_id = await sysrepo.save_pending(
                    conn, user.id, {"kind": "amount", "text": text, "value": value}, source, source_key,
                )
        return out

    # "Alisherga 100 ming berdim" + Alisherdan olingan ochiq qarz bor → bu qaytarish bo'lishi mumkin
    if result.alt_debt and result.alt_debt.counterparty and not force:
        opposite = "taken" if result.alt_debt.direction == "given" else "given"
        async with db.user_tx(user.id) as conn:
            named, _ = await debtrepo.candidates(conn, user.id, opposite, result.alt_debt.counterparty)
        if named:
            rep = ParsedRepayment(direction=opposite, amount=result.alt_debt.amount,
                                  counterparty=result.alt_debt.counterparty, confidence=0.6)
            return await _pending_repay(user, named, rep, list(result.items), source, source_key, cats,
                                        alt_debt=result.alt_debt)

    auto_items = [i for i in result.items if force or i.confidence >= auto_th]
    confirm_items = [i for i in result.items if not force and i.confidence < auto_th]
    auto_debts = [d for d in result.debts if force or d.confidence >= auto_th]
    confirm_debts = [d for d in result.debts if not force and d.confidence < auto_th]

    out = IngestOutcome(kind="saved")
    if auto_items:
        out.saved = await save_items(user, auto_items, source, source_key)
    if auto_debts:
        out.saved_debts = await save_debts(user, auto_debts, source, source_key)
    if (auto_items or auto_debts) and not out.anything_saved and source_key:
        out.kind = "duplicate"
    if confirm_items or confirm_debts:
        alt = result.alt_debt if (result.alt_debt and any(i.amount == result.alt_debt.amount for i in confirm_items)) else None
        payload = {"kind": "confirm", "items": [i.model_dump(mode="json") for i in confirm_items],
                   "debts": [d.model_dump(mode="json") for d in confirm_debts],
                   "alt_debt": alt.model_dump(mode="json") if alt else None}
        async with db.user_tx(user.id) as conn:
            out.pending_id = await sysrepo.save_pending(conn, user.id, payload, source,
                                                        f"{source_key}:c" if source_key else None)
        out.pending_items = [_view_item(i, cats) for i in confirm_items]
        out.pending_debts = [d.model_dump(mode="json") for d in confirm_debts]
        out.has_alt_debt = alt is not None
        out.question = result.clarification_question
        out.kind = "pending" if not out.anything_saved else "saved"
    return out


def _repay_view(d: dict, amount: int | None) -> dict:
    return {"debt_id": str(d["id"]), "who": d["counterparty"], "remaining": d["remaining"], "amount": amount,
            "direction": d["direction"], "due_at": d["due_at"].isoformat() if d.get("due_at") else None}


async def _pending_repay(user: User, cands: list[dict], rep: ParsedRepayment, fallback: list[ParsedItem],
                         source: str, source_key: str | None, cats: dict, *, question: str | None = None,
                         alt_debt: ParsedDebt | None = None) -> IngestOutcome:
    """Qaytarish uchun tasdiq: bitta nomzod → «✅ Qarzni yopish», bir nechta → tanlash tugmalari."""
    out = IngestOutcome(kind="pending")
    amount = rep.amount
    if len(cands) > 1 and amount:
        exact = [c for c in cands if c["remaining"] == amount]
        if len(exact) == 1:
            cands = exact
    base = {"amount": amount, "fallback_items": [i.model_dump(mode="json") for i in fallback],
            "alt_debt": alt_debt.model_dump(mode="json") if alt_debt else None}
    if len(cands) == 1:
        d = cands[0]
        payload = {"kind": "repay", "debt_id": str(d["id"]), **base}
        out.pending_kind = "repay"
        out.pending_repay = _repay_view(d, amount)
        if not question:
            who = d["counterparty"] or ("bir kishi" if d["direction"] == "given" else "kimdir")
            part = ""
            if amount and amount < d["remaining"]:
                part = f" {amount:,} so'm qisman qaytarilib, {d['remaining'] - amount:,} so'm qoladi.".replace(",", " ")
            elif amount and amount > d["remaining"]:
                part = f" (qarz qoldig'i {d['remaining']:,} so'm — to'liq yopiladi)".replace(",", " ")
            if d["direction"] == "given":
                question = f"{who} sizga {d['remaining']:,} so'm qarzdor edi. Shu qarzni yopaymi?{part}".replace(",", " ")
            else:
                question = f"Siz {who}dan {d['remaining']:,} so'm qarz olgan edingiz. Shu qarzni yopaymi?{part}".replace(",", " ")
    else:
        payload = {"kind": "repay_pick", "candidates": [str(c["id"]) for c in cands], **base}
        out.pending_kind = "repay_pick"
        out.repay_options = [{"idx": i, **_repay_view(c, amount)} for i, c in enumerate(cands)]
        question = question or "Qaysi qarz qaytarildi?"
    async with db.user_tx(user.id) as conn:
        out.pending_id = await sysrepo.save_pending(conn, user.id, payload, source, f"{source_key}:c" if source_key else None)
    out.pending_items = [_view_item(i, cats) for i in fallback]
    out.has_fallback = bool(fallback)
    out.has_alt_debt = alt_debt is not None
    out.question = question
    return out


@dataclass
class ConfirmOutcome:
    saved: list[dict] = field(default_factory=list)
    saved_debts: list[dict] = field(default_factory=list)
    repaid: list[dict] = field(default_factory=list)
    repay_status: str | None = None          # paid | partial

    @property
    def ok(self) -> bool:
        return bool(self.saved or self.saved_debts or self.repaid)


async def confirm_pending(user: User, pending_id: UUID, choice: str = "ok", pick: int | None = None) -> ConfirmOutcome:
    """choice: ok — ko'rsatilganidek saqlash (repay uchun: oddiy yozuv sifatida);
    debt — «🤝 Bu qarz» (alternativ talqin / yangi qarz); repay — qarzni yopish (pick: tanlangan nomzod)."""
    async with db.user_tx(user.id) as conn:
        popped = await sysrepo.pop_pending(conn, user.id, pending_id)
    out = ConfirmOutcome()
    if not popped:
        return out
    payload, source, source_key = popped
    kind = payload.get("kind")
    if kind not in ("confirm", "repay", "repay_pick"):
        return out
    if not access_of(user).can_add:
        return out
    if kind in ("repay", "repay_pick"):
        amount = payload.get("amount")
        if choice in ("repay", "ok") and (kind == "repay" or pick is not None):
            # repay: "ok" ham qarzni yopish degani (asosiy tugma)
            if kind == "repay":
                debt_id = payload.get("debt_id")
            else:
                cands = payload.get("candidates") or []
                debt_id = cands[pick] if pick is not None and 0 <= pick < len(cands) else None
            if debt_id:
                async with db.user_tx(user.id) as conn:
                    d = await debtrepo.get(conn, user.id, UUID(debt_id))
                if d and d["status"] == "open":
                    pay_amount = amount if amount and amount < d["remaining"] else None
                    row = await debt_svc.pay(user, UUID(debt_id), pay_amount)
                    if row:
                        out.repaid = [row]
                        out.repay_status = "paid" if row["status"] == "paid" else "partial"
            return out
        if choice == "item":
            items = [ParsedItem(**i) for i in payload.get("fallback_items", [])]
            for i in items:
                i.confidence = 1.0
            if items:
                out.saved = await save_items(user, items, source, source_key)
            return out
        if choice == "debt" and payload.get("alt_debt"):
            alt_debt = ParsedDebt(**payload["alt_debt"])
            alt_debt.confidence = 1.0
            out.saved_debts = await save_debts(user, [alt_debt], source, source_key)
            return out
        return out
    items = [ParsedItem(**i) for i in payload.get("items", [])]
    debts = [ParsedDebt(**d) for d in payload.get("debts", [])]
    alt = payload.get("alt_debt")
    if choice == "debt" and alt:
        alt_debt = ParsedDebt(**alt)
        items = [i for i in items if i.amount != alt_debt.amount]
        debts.append(alt_debt)
    for i in items:
        i.confidence = 1.0
    for d in debts:
        d.confidence = 1.0
    if items:
        out.saved = await save_items(user, items, source, source_key)
    if debts:
        out.saved_debts = await save_debts(user, debts, source, source_key)
    return out


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
