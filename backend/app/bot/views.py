"""Bot xabarlarini formatlash (handlerlardan ajratilgan)."""
from __future__ import annotations

import html
from datetime import datetime, timedelta

from app.bot.texts import uz as T
from app.core.timeutil import fmt_money, local_now, to_utc_range, tz
from app.db.database import db
from app.domain.models import User
from app.repositories import transactions as txrepo
from app.services.access import access_of
from app.domain.models import AccessState


def e(s: str | None) -> str:
    return html.escape(s or "", quote=False)


def tx_line(r: dict, tz_name: str) -> str:
    sign = "➕ " if r.get("type") == "income" else ""
    occ = r["occurred_at"]
    if isinstance(occ, str):
        occ = datetime.fromisoformat(occ)
    local = occ.astimezone(tz(tz_name))
    today = local_now(tz_name).date()
    when = local.strftime("%H:%M") if local.date() == today else local.strftime("%d.%m %H:%M")
    desc = r.get("description") or ""
    name = r.get("category_name") or "Boshqa"
    desc_part = f" · <i>{e(desc)}</i>" if desc and desc.lower() not in name.lower() else ""
    return f"{sign}{r.get('category_emoji') or '•'} <b>{e(name)}</b> — {fmt_money(r['amount'])}{desc_part}  <code>{when}</code>"


async def today_total(user: User) -> int:
    today = local_now(user.timezone).date()
    s, en = to_utc_range(today, today + timedelta(days=1), user.timezone)
    async with db.user_tx(user.id) as conn:
        return (await txrepo.totals(conn, user.id, s, en))["expense"]


async def saved_message(user: User, rows: list[dict]) -> str:
    lines = [T.SAVED_HEADER]
    for n, r in enumerate(rows, 1):
        prefix = f"{n}. " if len(rows) > 1 else ""
        lines.append(prefix + tx_line(r, user.timezone))
    lines.append("")
    lines.append(T.TODAY_TOTAL.format(total=fmt_money(await today_total(user))))
    return "\n".join(lines)


def pending_message(items: list[dict], question: str | None, debts: list[dict] | None = None,
                    tz_name: str = "Asia/Tashkent") -> str:
    lines = [T.CONFIRM_HEADER]
    for it in items:
        sign = "➕ Daromad: " if it["type"] == "income" else "💸 "
        desc = f" · <i>{e(it.get('description'))}</i>" if it.get("description") else ""
        lines.append(f"{sign}{it.get('category_emoji', '•')} <b>{e(it.get('category_name'))}</b> — "
                     f"{fmt_money(it['amount'])}{desc}")
    for d in debts or []:
        who = e(d.get("counterparty")) or "?"
        verb = f"<b>{who}</b>ga qarz berdingiz" if d["direction"] == "given" else f"<b>{who}</b>dan qarz oldingiz"
        due = ""
        if d.get("due_at"):
            dd = d["due_at"]
            if isinstance(dd, str):
                dd = datetime.fromisoformat(dd)
            due = f" · 📅 {dd.astimezone(tz(tz_name)).strftime('%d.%m')}gacha"
        lines.append(f"🤝 {verb} — {fmt_money(d['amount'])}{due}")
    if question:
        lines += ["", f"❔ {e(question)}"]
    return "\n".join(lines)


def debt_saved_message(rows: list[dict], tz_name: str) -> str:
    from app.services import debts as debt_svc

    if len(rows) == 1:
        return debt_svc.saved_text(rows[0], tz_name)
    lines = ["🤝 <b>Qarzlar yozildi</b>"]
    for n, r in enumerate(rows, 1):
        lines.append(f"{n}. " + debt_svc.line(r, tz_name))
    return "\n".join(lines)


def repaid_message(rows: list[dict], status: str, tz_name: str) -> str:
    from app.services import debts as debt_svc

    head = "✅ <b>Qarz yopildi</b>" if status == "paid" else "✅ <b>Qisman qaytarildi</b>"
    return head + "\n" + "\n".join(debt_svc.line(r, tz_name) for r in rows)


def plan_text(user: User) -> str:
    acc = access_of(user)
    end = acc.ends_at.astimezone(tz(user.timezone)).strftime("%d.%m.%Y") if acc.ends_at else "—"
    if acc.state == AccessState.pro:
        if user.is_superadmin:
            return "⭐️ Holat: <b>Superadmin</b> (cheklovsiz)\n\n"
        return T.PLAN_PRO.format(end=end, days=acc.days_left)
    if acc.state == AccessState.trial:
        return T.PLAN_TRIAL.format(end=end, days=acc.days_left)
    return T.PLAN_EXPIRED
