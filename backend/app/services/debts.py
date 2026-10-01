"""Qarzlar domen servisi: yaratish, qaytarish, eslatma matnlari. Bot va mini app faqat shu orqali ishlaydi."""
from __future__ import annotations

import html
import logging
from datetime import date, datetime
from uuid import UUID

from app.core.timeutil import fmt_money, local_now, tz
from app.db.database import db
from app.domain.models import ParsedDebt, ParsedRepayment, User
from app.repositories import debts as repo
from app.repositories import system as sysrepo

log = logging.getLogger(__name__)


def _e(s: str | None) -> str:
    return html.escape(s or "", quote=False)


def _aware(dt: datetime | None, tz_name: str) -> datetime | None:
    if dt is not None and dt.tzinfo is None:
        return dt.replace(tzinfo=tz(tz_name))
    return dt


def serialize(d: dict, tz_name: str, today: date | None = None) -> dict:
    z = tz(tz_name)
    today = today or local_now(tz_name).date()
    due = d["due_at"].astimezone(z) if d.get("due_at") else None
    days_left = (due.date() - today).days if due else None
    return {
        "id": str(d["id"]), "direction": d["direction"], "amount": d["amount"], "paid_amount": d["paid_amount"],
        "remaining": d["remaining"], "counterparty": d["counterparty"], "note": d["note"], "status": d["status"],
        "occurred_at": d["occurred_at"].astimezone(z).isoformat(),
        "due_at": due.isoformat() if due else None,
        "days_left": days_left,
        "overdue": bool(due and days_left is not None and days_left < 0 and d["status"] == "open"),
        "paid_at": d["paid_at"].astimezone(z).isoformat() if d.get("paid_at") else None,
        "source": d["source"],
    }


async def create(user: User, parsed: ParsedDebt, *, source: str, source_key: str | None) -> dict | None:
    async with db.user_tx(user.id) as conn:
        row = await repo.insert(
            conn, user.id, direction=parsed.direction, amount=parsed.amount, counterparty=parsed.counterparty[:40],
            note=parsed.note[:60], occurred_at=_aware(parsed.occurred_at, user.timezone),
            due_at=_aware(parsed.due_at, user.timezone), source=source, source_key=source_key,
        )
    if row:
        async with db.system_tx() as conn:
            await sysrepo.event(conn, "debt_created", user.id, {"direction": parsed.direction, "source": source})
    return row


async def create_manual(user: User, *, direction: str, amount: int, counterparty: str, note: str,
                        due_at: datetime | None, occurred_at: datetime | None) -> dict | None:
    now = local_now(user.timezone)
    occ = _aware(occurred_at, user.timezone) or now
    if occ > now:
        occ = now
    parsed = ParsedDebt(direction=direction, amount=amount, counterparty=counterparty, note=note, occurred_at=occ,
                        due_at=_aware(due_at, user.timezone), confidence=1.0)
    return await create(user, parsed, source="manual", source_key=None)


async def list_debts(user: User, status: str | None) -> dict:
    async with db.user_tx(user.id) as conn:
        rows = await repo.list_(conn, user.id, status)
        summ = await repo.summary(conn, user.id)
    today = local_now(user.timezone).date()
    return {"items": [serialize(r, user.timezone, today) for r in rows], "summary": summ}


async def summary(user: User) -> dict:
    async with db.user_tx(user.id) as conn:
        return await repo.summary(conn, user.id)


async def pay(user: User, debt_id: UUID, amount: int | None = None) -> dict | None:
    async with db.user_tx(user.id) as conn:
        row = await repo.pay(conn, user.id, debt_id, amount)
    if row:
        async with db.system_tx() as conn:
            await sysrepo.event(conn, "debt_paid" if row["status"] == "paid" else "debt_partial", user.id)
    return row


async def reopen(user: User, debt_id: UUID) -> bool:
    async with db.user_tx(user.id) as conn:
        return await repo.reopen(conn, user.id, debt_id)


async def update(user: User, debt_id: UUID, *, amount: int | None = None, counterparty: str | None = None,
                 note: str | None = None, due_at: datetime | None = None, clear_due: bool = False) -> dict | None:
    async with db.user_tx(user.id) as conn:
        ok = await repo.update(conn, user.id, debt_id, amount=amount, counterparty=counterparty, note=note,
                               due_at=_aware(due_at, user.timezone), clear_due=clear_due)
        return await repo.get(conn, user.id, debt_id) if ok else None


async def snooze(user: User, debt_id: UUID, days: int) -> dict | None:
    """Muddatni N kunga surish (eslatmadan)."""
    async with db.user_tx(user.id) as conn:
        d = await repo.get(conn, user.id, debt_id)
        if not d or d["status"] != "open":
            return None
        base = d["due_at"] or local_now(user.timezone)
        now = local_now(user.timezone)
        if base < now:
            base = now
        from datetime import timedelta
        await repo.update(conn, user.id, debt_id, due_at=base + timedelta(days=days))
        return await repo.get(conn, user.id, debt_id)


async def delete(user: User, debt_id: UUID) -> bool:
    async with db.user_tx(user.id) as conn:
        return await repo.delete(conn, user.id, debt_id)


async def apply_repayment(user: User, rep: ParsedRepayment) -> tuple[str, list[dict]]:
    """«Jasur qarzini qaytardi» → mos ochiq qarz topilsa yopiladi.
    Qaytaradi: ("paid"|"partial"|"ambiguous"|"none", qarzlar)."""
    async with db.user_tx(user.id) as conn:
        matches = await repo.find_open_match(conn, user.id, rep.direction, rep.counterparty, rep.amount)
        if not matches:
            return "none", []
        if len(matches) > 1 and not rep.amount:
            return "ambiguous", matches
        if len(matches) > 1:
            exact = [m for m in matches if m["remaining"] == rep.amount]
            if len(exact) != 1:
                return "ambiguous", matches
            matches = exact
        target = matches[0]
        amount = rep.amount if rep.amount and rep.amount < target["remaining"] else None
        row = await repo.pay(conn, user.id, target["id"], amount)
    if not row:
        return "none", []
    async with db.system_tx() as conn:
        await sysrepo.event(conn, "debt_paid" if row["status"] == "paid" else "debt_partial", user.id)
    return ("paid" if row["status"] == "paid" else "partial"), [row]


# ---------------- Matnlar ----------------

def due_label(d: dict, tz_name: str, today: date | None = None) -> str:
    if not d.get("due_at"):
        return "muddatsiz"
    today = today or local_now(tz_name).date()
    due = d["due_at"].astimezone(tz(tz_name)).date()
    left = (due - today).days
    ds = due.strftime("%d.%m")
    if left < 0:
        return f"{ds} · ⚠️ {abs(left)} kun o'tdi"
    if left == 0:
        return f"{ds} · bugun!"
    if left == 1:
        return f"{ds} · ertaga"
    return f"{ds} · {left} kun qoldi"


def line(d: dict, tz_name: str, today: date | None = None) -> str:
    who = _e(d["counterparty"]) or ("kimgadir" if d["direction"] == "given" else "kimdandir")
    arrow = "🤝➡️" if d["direction"] == "given" else "🤝⬅️"
    verb = f"<b>{who}</b>ga berdingiz" if d["direction"] == "given" else f"<b>{who}</b>dan oldingiz"
    amt = fmt_money(d["remaining"] if d["status"] == "open" else d["amount"])
    part = f" (jami {fmt_money(d['amount'])}, {fmt_money(d['paid_amount'])} qaytdi)" if d["paid_amount"] and d["status"] == "open" else ""
    note = f" · <i>{_e(d['note'])}</i>" if d.get("note") else ""
    status = "✅ yopilgan" if d["status"] == "paid" else due_label(d, tz_name, today)
    return f"{arrow} {verb} — {amt}{part}{note}\n     📅 {status}"


def saved_text(d: dict, tz_name: str) -> str:
    head = "🤝 <b>Qarz yozildi</b>"
    tail = ("\n\nMuddati yaqinlashganda eslatib turaman 🔔" if d.get("due_at")
            else "\n\n<i>Muddat aytilmadi — xohlasangiz «⏰ Muddat» tugmasi bilan qo'ying.</i>")
    return f"{head}\n{line(d, tz_name)}{tail}"


def reminder_text(d: dict, tz_name: str) -> str:
    who = _e(d["counterparty"]) or ("bir kishi" if d["direction"] == "given" else "kimdir")
    amt = fmt_money(d["remaining"])
    left = d.get("days_left")
    due = d["due_at"].astimezone(tz(tz_name)).strftime("%d.%m.%Y") if d.get("due_at") else ""
    if d["direction"] == "given":
        if left is not None and left < 0:
            when = f"Muddati <b>{abs(left)} kun oldin</b> ({due}) o'tgan."
        elif left == 0:
            when = f"Muddati <b>bugun</b> ({due})."
        else:
            when = f"Muddatiga <b>{left} kun</b> qoldi ({due})."
        return (f"🔔 <b>Eslatma: sizga qarzdorlar</b>\n\n"
                f"Siz <b>{who}</b>ga <b>{amt}</b> qarz bergan edingiz. {when}\n"
                f"So'rab ko'ring 🙂")
    if left is not None and left < 0:
        when = f"Muddati <b>{abs(left)} kun oldin</b> ({due}) o'tgan — tezroq qaytaring."
    elif left == 0:
        when = f"Muddati <b>bugun</b> ({due}) — unutmang!"
    else:
        when = f"<b>{left} kun</b> qoldi ({due}) — unutmang!"
    return (f"🔔 <b>Eslatma: qarzingiz bor</b>\n\n"
            f"Siz <b>{who}</b>dan <b>{amt}</b> qarz olgan edingiz. {when}")


def list_text(data: dict, tz_name: str) -> str:
    items, s = data["items"], data["summary"]
    today = local_now(tz_name).date()
    lines = ["🤝 <b>Qarzlar</b>", ""]
    if not items:
        lines.append("Ochiq qarzlar yo'q 🎉")
        lines.append("\n<i>Yozing: «Jasurga 100 ming qarz berdim 2 kunga» yoki «Akmaldan 500 ming qarz oldim»</i>")
        return "\n".join(lines)
    given = [i for i in items if i["direction"] == "given"]
    taken = [i for i in items if i["direction"] == "taken"]
    if given:
        lines.append(f"➡️ <b>Sizga qaytarishlari kerak: {fmt_money(s['given_open'])}</b>")
        for d in given[:15]:
            lines.append(_short_line(d, today))
        lines.append("")
    if taken:
        lines.append(f"⬅️ <b>Siz qaytarishingiz kerak: {fmt_money(s['taken_open'])}</b>")
        for d in taken[:15]:
            lines.append(_short_line(d, today))
        lines.append("")
    if s["overdue_count"]:
        lines.append(f"⚠️ Muddati o'tgan: {s['overdue_count']} ta")
    return "\n".join(lines).rstrip()


def _short_line(d: dict, today: date) -> str:
    who = _e(d["counterparty"]) or "—"
    due = ""
    if d["due_at"]:
        left = d["days_left"]
        due = " · ⚠️ muddati o'tgan" if left < 0 else (" · bugun" if left == 0 else f" · {left} kun")
    return f"• {who} — {fmt_money(d['remaining'])}{due}"
