"""Hisobotlar. Barcha summalar SQL bilan deterministik hisoblanadi (LLM raqam hisoblamaydi)."""
from __future__ import annotations

import html
from datetime import date, datetime, timedelta

from app.core.timeutil import fmt_money, local_now, period_bounds, to_utc_range, tz
from app.db.database import db
from app.domain.models import User
from app.repositories import transactions as txrepo

PERIOD_TITLES = {"day": "Kunlik", "week": "Haftalik", "month": "Oylik", "year": "Yillik"}
MONTHS_UZ = ["", "yanvar", "fevral", "mart", "aprel", "may", "iyun", "iyul", "avgust", "sentabr", "oktabr",
             "noyabr", "dekabr"]
MAX_LINES = 60


def _e(s: str | None) -> str:
    return html.escape(s or "", quote=False)


def _bar(part: int, total: int, width: int = 10) -> str:
    if total <= 0:
        return "▱" * width
    n = max(1, round(width * part / total)) if part else 0
    return "▰" * n + "▱" * (width - n)


async def daily_report_text(user: User, day: date, *, final: bool = True) -> str:
    """Kun oxiridagi (23:59) hisobot: har bir yozuv nomi, vaqti va summasi bilan + umumiy."""
    start, end = to_utc_range(day, day + timedelta(days=1), user.timezone)
    async with db.user_tx(user.id) as conn:
        rows = await txrepo.list_range(conn, user.id, start, end, asc=True, limit=500)
        totals = await txrepo.totals(conn, user.id, start, end)
        cats = await txrepo.by_category(conn, user.id, start, end, "expense")
    z = tz(user.timezone)
    d = day.strftime("%d.%m.%Y")
    lines = [f"📊 <b>Kunlik hisobot</b> — {d}", ""]
    expenses = [r for r in rows if r["type"] == "expense"]
    incomes = [r for r in rows if r["type"] == "income"]

    if not rows:
        lines.append("Bugun hech qanday yozuv bo'lmadi 🙂")
        lines.append("Xarajat qilsangiz — shunchaki yozing yoki ovozli xabar yuboring.")
    else:
        if expenses:
            lines.append("💸 <b>Xarajatlar:</b>")
            for n, r in enumerate(expenses[:MAX_LINES], 1):
                t = r["occurred_at"].astimezone(z).strftime("%H:%M")
                name = _e(r["category_name"] or "Boshqa")
                desc = _e(r["description"])
                desc_part = f" · <i>{desc}</i>" if desc and desc.lower() != name.lower() else ""
                lines.append(f"{n}. {r['category_emoji'] or '•'} <b>{name}</b> — {fmt_money(r['amount'])}")
                lines.append(f"     🕐 {t}{desc_part}")
            if len(expenses) > MAX_LINES:
                lines.append(f"… yana {len(expenses) - MAX_LINES} ta (to'liq ro'yxat Dashboard'da)")
            lines.append("")
        if incomes:
            lines.append("💰 <b>Daromadlar:</b>")
            for r in incomes[:20]:
                t = r["occurred_at"].astimezone(z).strftime("%H:%M")
                lines.append(f"• {r['category_emoji'] or '•'} {_e(r['category_name'])} — {fmt_money(r['amount'])}  🕐 {t}")
            lines.append("")
        if cats:
            top = cats[0]
            share = round(100 * top["total"] / totals["expense"]) if totals["expense"] else 0
            lines.append(f"🏆 Eng ko'p: {top['emoji'] or ''} {_e(top['name'])} — {fmt_money(top['total'])} ({share}%)")

    lines.append("━━━━━━━━━━━━━━━")
    stamp = f"{d} soat {user.report_time}" if final else f"{d} soat {local_now(user.timezone).strftime('%H:%M')}"
    lines.append(f"📅 {stamp}")
    lines.append(f"💸 <b>Umumiy xarajat: {fmt_money(totals['expense'])}</b>")
    if totals["income"]:
        lines.append(f"💰 Daromad: {fmt_money(totals['income'])}")
        sign = "+" if totals["net"] >= 0 else "−"
        lines.append(f"⚖️ Qoldiq: {sign}{fmt_money(abs(totals['net']))}")
    lines.append(f"🧾 Yozuvlar soni: {totals['count']}")
    return "\n".join(lines)


async def period_report_text(user: User, period: str, day: date | None = None) -> str:
    day = day or local_now(user.timezone).date()
    if period == "day":
        return await daily_report_text(user, day, final=False)
    ps, pe = period_bounds(period, day, user.timezone)
    start, end = to_utc_range(ps, pe, user.timezone)
    # oldingi davr (taqqoslash uchun)
    prev_ps, _ = period_bounds(period, ps - timedelta(days=1), user.timezone)
    pstart, pend = to_utc_range(prev_ps, ps, user.timezone)
    async with db.user_tx(user.id) as conn:
        totals = await txrepo.totals(conn, user.id, start, end)
        prev = await txrepo.totals(conn, user.id, pstart, pend)
        cats = await txrepo.by_category(conn, user.id, start, end, "expense")
        top_tx = await txrepo.list_range(conn, user.id, start, end, type_="expense", limit=2000)
    top_tx = sorted(top_tx, key=lambda r: r["amount"], reverse=True)[:5]

    title = PERIOD_TITLES[period]
    if period == "week":
        label = f"{ps.strftime('%d.%m')} – {(pe - timedelta(days=1)).strftime('%d.%m.%Y')}"
    elif period == "month":
        label = f"{MONTHS_UZ[ps.month].capitalize()} {ps.year}"
    else:
        label = str(ps.year)
    today = local_now(user.timezone).date()
    elapsed = max(1, (min(today + timedelta(days=1), pe) - ps).days)
    lines = [f"📈 <b>{title} hisobot</b> — {label}", ""]
    lines.append(f"💸 Xarajat: <b>{fmt_money(totals['expense'])}</b>")
    if totals["income"]:
        lines.append(f"💰 Daromad: <b>{fmt_money(totals['income'])}</b>")
        sign = "+" if totals["net"] >= 0 else "−"
        lines.append(f"⚖️ Qoldiq: {sign}{fmt_money(abs(totals['net']))}")
    lines.append(f"📆 Kunlik o'rtacha: {fmt_money(totals['expense'] // elapsed)}")
    if prev["expense"]:
        diff = totals["expense"] - prev["expense"]
        pct = round(100 * diff / prev["expense"])
        arrow = "🔺" if diff > 0 else "🔻"
        lines.append(f"{arrow} Oldingi davrga nisbatan: {'+' if diff > 0 else ''}{pct}%")
    if cats:
        lines += ["", "<b>Kategoriyalar:</b>"]
        for c in cats[:8]:
            share = round(100 * c["total"] / totals["expense"]) if totals["expense"] else 0
            lines.append(f"{c['emoji'] or '•'} {_e(c['name'])}\n{_bar(c['total'], totals['expense'])} {share}% · {fmt_money(c['total'])}")
    if top_tx:
        lines += ["", "<b>Eng katta xarajatlar:</b>"]
        z = tz(user.timezone)
        for r in top_tx:
            dt = r["occurred_at"].astimezone(z).strftime("%d.%m %H:%M")
            desc = f" · <i>{_e(r['description'])}</i>" if r["description"] else ""
            lines.append(f"• {fmt_money(r['amount'])} — {_e(r['category_name'])}{desc} ({dt})")
    if not totals["count"]:
        lines.append("\nBu davrda yozuvlar yo'q.")
    return "\n".join(lines)


# ---------------- Mini app dashboard ----------------

def _shift_months(d: date, months: int) -> date:
    m = d.month - 1 + months
    return date(d.year + m // 12, m % 12 + 1, 1)


async def dashboard(user: User) -> dict:
    now = local_now(user.timezone)
    today = now.date()
    tzn = user.timezone
    out: dict = {"today": today.isoformat(), "generated_at": now.isoformat()}

    async with db.user_tx(user.id) as conn:
        # KPI kartalar
        for p in ("day", "week", "month", "year"):
            ps, pe = period_bounds(p, today, tzn)
            s, e = to_utc_range(ps, pe, tzn)
            out[f"totals_{p}"] = await txrepo.totals(conn, user.id, s, e)

        # 4 ta line grafik
        d_start = today - timedelta(days=29)
        s, e = to_utc_range(d_start, today + timedelta(days=1), tzn)
        daily = await txrepo.series(conn, user.id, tzn, "day", s, e)

        w_start = today - timedelta(days=today.weekday()) - timedelta(weeks=11)
        s, e = to_utc_range(w_start, today + timedelta(days=1), tzn)
        weekly = await txrepo.series(conn, user.id, tzn, "week", s, e)

        m_start = _shift_months(today.replace(day=1), -11)
        s, e = to_utc_range(m_start, today + timedelta(days=1), tzn)
        monthly = await txrepo.series(conn, user.id, tzn, "month", s, e)

        first = await txrepo.first_date(conn, user.id)
        first_year = first.astimezone(tz(tzn)).year if first else today.year
        y_start = date(min(first_year, today.year - 4), 1, 1)
        s, e = to_utc_range(y_start, today + timedelta(days=1), tzn)
        yearly = await txrepo.series(conn, user.id, tzn, "year", s, e)

        ms, me = period_bounds("month", today, tzn)
        s, e = to_utc_range(ms, me, tzn)
        out["categories_month"] = await txrepo.by_category(conn, user.id, s, e, "expense")
        ws, we = period_bounds("week", today, tzn)
        s, e = to_utc_range(ws, we, tzn)
        out["categories_week"] = await txrepo.by_category(conn, user.id, s, e, "expense")
        ds, de = to_utc_range(today, today + timedelta(days=1), tzn)
        out["categories_day"] = await txrepo.by_category(conn, user.id, ds, de, "expense")
        ys, ye = period_bounds("year", today, tzn)
        s, e = to_utc_range(ys, ye, tzn)
        out["categories_year"] = await txrepo.by_category(conn, user.id, s, e, "expense")

        recent = await txrepo.list_range(conn, user.id, datetime(2000, 1, 1, tzinfo=tz("UTC")),
                                         datetime(2100, 1, 1, tzinfo=tz("UTC")), limit=15)

    def ser(rows):
        return [{"period": r["period"].isoformat(), "expense": r["expense"], "income": r["income"],
                 "count": r["count"]} for r in rows]

    out["charts"] = {"daily": ser(daily), "weekly": ser(weekly), "monthly": ser(monthly), "yearly": ser(yearly)}
    out["recent"] = [serialize_tx(r, tzn) for r in recent]
    # o'rtachalar (AI emas — deterministik)
    exp30 = sum(r["expense"] for r in daily)
    out["avg_daily_30"] = exp30 // 30
    out["avg_weekly_12"] = sum(r["expense"] for r in weekly) // max(1, len(weekly))
    return out


def serialize_tx(r: dict, tz_name: str) -> dict:
    return {
        "id": str(r["id"]), "type": r["type"], "amount": r["amount"], "currency": r["currency"],
        "category_id": r["category_id"], "category_key": r["category_key"], "category_name": r["category_name"],
        "category_emoji": r["category_emoji"], "description": r["description"],
        "occurred_at": r["occurred_at"].astimezone(tz(tz_name)).isoformat(), "source": r["source"],
    }
