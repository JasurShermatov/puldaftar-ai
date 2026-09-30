"""AI tahlil: statistikani SQL hisoblaydi, LLM faqat odam tilida tushuntiradi (raqam o'ylab topmaydi).
OPENAI_API_KEY bo'lmasa — qoida asosidagi (rule-based) tahlil qaytariladi."""
from __future__ import annotations

import html
import json
import logging
from datetime import date, timedelta

from app.core.config import get_settings
from app.core.timeutil import fmt_money, local_now, to_utc_range
from app.db.database import db
from app.domain.models import User
from app.repositories import system as sysrepo
from app.repositories import transactions as txrepo
from app.services.ai import openai_client as ai
from app.services.parsing.prompts import INSIGHT_SYSTEM

log = logging.getLogger(__name__)
WEEKDAYS = ["dushanba", "seshanba", "chorshanba", "payshanba", "juma", "shanba", "yakshanba"]


async def compute_stats(user: User, today: date | None = None) -> dict:
    today = today or local_now(user.timezone).date()
    tzn = user.timezone
    end = today + timedelta(days=1)
    s7, e7 = to_utc_range(end - timedelta(days=7), end, tzn)
    sp7, ep7 = to_utc_range(end - timedelta(days=14), end - timedelta(days=7), tzn)
    s28, e28 = to_utc_range(end - timedelta(days=28), end, tzn)
    sd, ed = to_utc_range(today, end, tzn)
    async with db.user_tx(user.id) as conn:
        t7 = await txrepo.totals(conn, user.id, s7, e7)
        tp7 = await txrepo.totals(conn, user.id, sp7, ep7)
        t28 = await txrepo.totals(conn, user.id, s28, e28)
        tday = await txrepo.totals(conn, user.id, sd, ed)
        cats28 = await txrepo.by_category(conn, user.id, s28, e28, "expense")
        cats7 = await txrepo.by_category(conn, user.id, s7, e7, "expense")
        catsday = await txrepo.by_category(conn, user.id, sd, ed, "expense")
        daily = await txrepo.series(conn, user.id, tzn, "day", s28, e28)

    weekday_tot = [0] * 7
    for r in daily:
        weekday_tot[r["period"].weekday()] += r["expense"]
    days_with_spend = sum(1 for r in daily if r["expense"] > 0)
    biggest_day = max(daily, key=lambda r: r["expense"]) if daily else None
    weeks = 4
    return {
        "today": today.isoformat(),
        "today_expense": tday["expense"],
        "today_top": [{"name": c["name"], "total": c["total"]} for c in catsday[:3]],
        "last7_expense": t7["expense"], "prev7_expense": tp7["expense"],
        "last7_income": t7["income"],
        "change_7_pct": round(100 * (t7["expense"] - tp7["expense"]) / tp7["expense"]) if tp7["expense"] else None,
        "last28_expense": t28["expense"],
        "avg_week_28": t28["expense"] // weeks,
        "avg_day_28": t28["expense"] // 28,
        "days_with_spend_28": days_with_spend,
        "categories_28": [
            {"name": c["name"], "total": c["total"], "avg_week": c["total"] // weeks, "count": c["count"],
             "share_pct": round(100 * c["total"] / t28["expense"]) if t28["expense"] else 0}
            for c in cats28[:6]
        ],
        "categories_7": [{"name": c["name"], "total": c["total"]} for c in cats7[:5]],
        "top_weekday": WEEKDAYS[weekday_tot.index(max(weekday_tot))] if any(weekday_tot) else None,
        "biggest_day": {"date": biggest_day["period"].isoformat(), "total": biggest_day["expense"]}
        if biggest_day and biggest_day["expense"] else None,
    }


def rule_based(st: dict, kind: str) -> str:
    e = html.escape
    if not st["last28_expense"] and not st["today_expense"]:
        return "Hali tahlil uchun ma'lumot yetarli emas. Bir necha kun xarajatlaringizni yozib boring 🙂"
    lines = ["🧠 <b>Xarajatlar tahlili</b>"]
    cats = st["categories_28"]
    if cats:
        c = cats[0]
        lines.append(f"• Eng ko'p pul <b>{e(c['name'])}</b>ga ketyapti: haftasiga o'rtacha {fmt_money(c['avg_week'])} "
                     f"(jami xarajatning {c['share_pct']}%).")
    lines.append(f"• O'rtacha haftalik xarajat: {fmt_money(st['avg_week_28'])}, kunlik: {fmt_money(st['avg_day_28'])}.")
    if st["change_7_pct"] is not None:
        if st["change_7_pct"] > 10:
            lines.append(f"• Oxirgi 7 kunda xarajat oldingi haftaga nisbatan <b>{st['change_7_pct']}%</b> oshdi 🔺")
        elif st["change_7_pct"] < -10:
            lines.append(f"• Oxirgi 7 kunda xarajat {abs(st['change_7_pct'])}% kamaydi — zo'r 👏")
    if st["top_weekday"]:
        lines.append(f"• Eng ko'p xarajat qilinadigan kun: {st['top_weekday']}.")
    if cats and cats[0]["share_pct"] >= 35:
        lines.append(f"💡 Maslahat: {e(cats[0]['name'])} uchun haftalik limit qo'yib ko'ring — "
                     f"masalan {fmt_money(int(cats[0]['avg_week'] * 0.8))}.")
    return "\n".join(lines)


async def generate(user: User, kind: str = "daily", *, force: bool = False) -> str:
    """kind: daily | weekly. Natija kun/hafta bo'yicha keshlanadi (API xarajatini tejash)."""
    today = local_now(user.timezone).date()
    key_day = today if kind == "daily" else today - timedelta(days=today.weekday())
    if not force:
        async with db.user_tx(user.id) as conn:
            cached = await sysrepo.get_insight(conn, user.id, kind, key_day)
        if cached:
            return cached
    st = await compute_stats(user, today)
    text = rule_based(st, kind)
    s = get_settings()
    if s.ai_enabled and (st["last28_expense"] or st["today_expense"]):
        try:
            focus = ("Bugungi kun va oxirgi hafta tendensiyasiga e'tibor ber." if kind == "daily"
                     else "Oxirgi 4 hafta bo'yicha chuqurroq tahlil qil: qaysi kategoriya ko'p, haftalik o'rtacha.")
            text = await ai.chat_text(
                model=s.openai_insight_model, system=INSIGHT_SYSTEM,
                user=f"{focus}\nStatistika (so'mda):\n<data>{json.dumps(st, ensure_ascii=False)}</data>",
            )
            text = _sanitize_html(text)
        except Exception as e:  # noqa: BLE001
            log.warning("insight llm failed: %s", type(e).__name__)
    async with db.user_tx(user.id) as conn:
        await sysrepo.save_insight(conn, user.id, kind, key_day, text)
    return text


def _sanitize_html(text: str) -> str:
    """Telegram HTML uchun faqat <b>, <i> qoldiriladi."""
    t = html.escape(text, quote=False)
    for tag in ("b", "i"):
        t = t.replace(f"&lt;{tag}&gt;", f"<{tag}>").replace(f"&lt;/{tag}&gt;", f"</{tag}>")
    t = t.replace("**", "")
    return t[:1500]
