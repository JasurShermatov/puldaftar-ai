"""AI suhbat: foydalanuvchining O'Z ma'lumotlari asosida savol-javob.

Kontekst (SQL bilan aniq hisoblangan): bugun/7 kun/30 kun/oy va o'tgan oy jami, kategoriyalar (xarajat va daromad),
oxirgi yozuvlar, ochiq qarzlar, oldingi suhbat. LLM faqat tushuntiradi — raqamlarni o'zi hisoblamaydi.
Ma'lumot ko'paygan sari kontekst boyiydi → javoblar aniqlashadi. Suhbat tarixi shifrlangan holda saqlanadi.
"""
from __future__ import annotations

import html
import json
import logging
from datetime import date, timedelta

from app.core.config import get_settings
from app.core.timeutil import fmt_money, local_now, period_bounds, to_utc_range, tz
from app.db.database import db
from app.domain.models import User
from app.repositories import chat as chatrepo
from app.repositories import debts as debtrepo
from app.repositories import system as sysrepo
from app.repositories import transactions as txrepo
from app.services.ai import openai_client as ai
from app.services.parsing.prompts import CHAT_SYSTEM

log = logging.getLogger(__name__)
MAX_QUESTION = 600
HISTORY_TURNS = 8

SUGGESTIONS = [
    "Nimaga eng ko'p pul sarflayapman?",
    "Bu oy o'tgan oyga nisbatan qanday?",
    "Daromadim xarajatimni qoplayaptimi?",
    "Qaysi kunlari ko'p xarajat qilaman?",
    "Qarzlarim qancha va kimga?",
    "Qanday tejashim mumkin?",
]


async def build_context(user: User) -> dict:
    tzn = user.timezone
    now = local_now(tzn)
    today = now.date()
    end = today + timedelta(days=1)

    def rng(a: date, b: date):
        return to_utc_range(a, b, tzn)

    ms, me = period_bounds("month", today, tzn)
    pms, pme = period_bounds("month", ms - timedelta(days=1), tzn)
    ws, we = period_bounds("week", today, tzn)
    async with db.user_tx(user.id) as conn:
        t_day = await txrepo.totals(conn, user.id, *rng(today, end))
        t_7 = await txrepo.totals(conn, user.id, *rng(end - timedelta(days=7), end))
        t_p7 = await txrepo.totals(conn, user.id, *rng(end - timedelta(days=14), end - timedelta(days=7)))
        t_30 = await txrepo.totals(conn, user.id, *rng(end - timedelta(days=30), end))
        t_week = await txrepo.totals(conn, user.id, *rng(ws, we))
        t_month = await txrepo.totals(conn, user.id, *rng(ms, me))
        t_pmonth = await txrepo.totals(conn, user.id, *rng(pms, pme))
        ys, ye = period_bounds("year", today, tzn)
        t_year = await txrepo.totals(conn, user.id, *rng(ys, ye))
        cats_m = await txrepo.by_category(conn, user.id, *rng(ms, me), "expense")
        cats_pm = await txrepo.by_category(conn, user.id, *rng(pms, pme), "expense")
        inc_m = await txrepo.by_category(conn, user.id, *rng(ms, me), "income")
        cats_30 = await txrepo.by_category(conn, user.id, *rng(end - timedelta(days=30), end), "expense")
        inc_30 = await txrepo.by_category(conn, user.id, *rng(end - timedelta(days=30), end), "income")
        daily = await txrepo.series(conn, user.id, tzn, "day", *rng(end - timedelta(days=30), end))
        recent = await txrepo.list_range(conn, user.id, *rng(end - timedelta(days=45), end), limit=40)
        debts = await debtrepo.list_(conn, user.id, "open", limit=30)
        dsum = await debtrepo.summary(conn, user.id)
        first = await txrepo.first_date(conn, user.id)

    z = tz(tzn)
    weekday_tot = [0] * 7
    for r in daily:
        weekday_tot[r["period"].weekday()] += r["expense"]
    wd_names = ["dushanba", "seshanba", "chorshanba", "payshanba", "juma", "shanba", "yakshanba"]
    biggest = max(daily, key=lambda r: r["expense"]) if daily else None

    def cat_list(rows, total):
        return [{"name": c["name"] or "Boshqa", "total": c["total"], "count": c["count"],
                 "share_pct": round(100 * c["total"] / total) if total else 0} for c in rows[:10]]

    def tot(t):
        return {"expense": t["expense"], "income": t["income"], "net": t["net"], "count": t["count"]}

    # Tez-tez takrorlanadigan izohlar (30 kun) — "nimaga" savoliga aniq javob uchun
    freq: dict[str, dict] = {}
    for r in recent:
        key = (r["description"] or r["category_name"] or "").strip().lower()
        if not key:
            continue
        f = freq.setdefault(key, {"name": key, "count": 0, "total": 0, "type": r["type"]})
        f["count"] += 1
        f["total"] += r["amount"]
    top_desc = sorted(freq.values(), key=lambda x: x["total"], reverse=True)[:8]

    return {
        "today": today.isoformat(), "weekday": wd_names[today.weekday()],
        "tracking_since": first.astimezone(z).date().isoformat() if first else None,
        "totals": {"today": tot(t_day), "last7": tot(t_7), "prev7": tot(t_p7), "last30": tot(t_30),
                   "this_week": tot(t_week), "this_month": tot(t_month), "prev_month": tot(t_pmonth), "this_year": tot(t_year)},
        "month_label": f"{ms.strftime('%Y-%m')}", "prev_month_label": f"{pms.strftime('%Y-%m')}",
        "avg_day_30": t_30["expense"] // 30, "avg_week_30": t_30["expense"] * 7 // 30,
        "expense_categories_month": cat_list(cats_m, t_month["expense"]),
        "expense_categories_prev_month": cat_list(cats_pm, t_pmonth["expense"]),
        "expense_categories_30": cat_list(cats_30, t_30["expense"]),
        "income_categories_month": cat_list(inc_m, t_month["income"]),
        "income_categories_30": cat_list(inc_30, t_30["income"]),
        "top_descriptions_45d": top_desc,
        "top_weekday_30": wd_names[weekday_tot.index(max(weekday_tot))] if any(weekday_tot) else None,
        "biggest_day_30": {"date": biggest["period"].isoformat(), "expense": biggest["expense"]} if biggest and biggest["expense"] else None,
        "recent_transactions": [
            {"date": r["occurred_at"].astimezone(z).strftime("%Y-%m-%d %H:%M"), "type": r["type"],
             "category": r["category_name"], "amount": r["amount"], "desc": (r["description"] or "")[:40]}
            for r in recent[:30]
        ],
        "debts": {
            "given_open_total": dsum["given_open"], "taken_open_total": dsum["taken_open"],
            "overdue_count": dsum["overdue_count"],
            "open": [{"direction": d["direction"], "who": d["counterparty"] or "?", "remaining": d["remaining"],
                      "due": d["due_at"].astimezone(z).date().isoformat() if d["due_at"] else None} for d in debts[:15]],
        },
    }


def _fallback_answer(ctx: dict, question: str) -> str:
    """AI o'chiq bo'lsa — eng ko'p so'raladigan savollarga qoida asosida javob."""
    q = question.lower()
    t = ctx["totals"]
    e = html.escape
    if "qarz" in q or "долг" in q or "debt" in q:
        d = ctx["debts"]
        if not d["open"]:
            return "Ochiq qarzlaringiz yo'q 🎉"
        lines = [f"🤝 Sizga qaytarishlari kerak: <b>{fmt_money(d['given_open_total'])}</b>, "
                 f"siz qaytarishingiz kerak: <b>{fmt_money(d['taken_open_total'])}</b>."]
        for x in d["open"][:6]:
            arrow = "➡️" if x["direction"] == "given" else "⬅️"
            lines.append(f"• {arrow} {e(x['who'])} — {fmt_money(x['remaining'])}" + (f" ({x['due']}gacha)" if x["due"] else ""))
        return "\n".join(lines)
    if "daromad" in q or "qopla" in q or "доход" in q or "income" in q:
        m = t["this_month"]
        sign = "+" if m["net"] >= 0 else "−"
        return (f"Bu oy daromad <b>{fmt_money(m['income'])}</b>, xarajat <b>{fmt_money(m['expense'])}</b>, "
                f"qoldiq <b>{sign}{fmt_money(abs(m['net']))}</b>.")
    if "o'tgan oy" in q or "otgan oy" in q or "прошл" in q or "last month" in q or "nisbatan" in q:
        m, p = t["this_month"], t["prev_month"]
        diff = m["expense"] - p["expense"]
        pct = f" ({'+' if diff > 0 else ''}{round(100 * diff / p['expense'])}%)" if p["expense"] else ""
        return (f"Bu oy xarajat <b>{fmt_money(m['expense'])}</b>, o'tgan oy <b>{fmt_money(p['expense'])}</b>"
                f"{pct}. Daromad: {fmt_money(m['income'])} / {fmt_money(p['income'])}.")
    cats = ctx["expense_categories_30"]
    if not cats:
        return "Hali tahlil uchun ma'lumot kam. Bir necha kun xarajatlaringizni yozib boring 🙂"
    lines = [f"Oxirgi 30 kunda jami xarajat <b>{fmt_money(t['last30']['expense'])}</b> "
             f"(kuniga o'rtacha {fmt_money(ctx['avg_day_30'])})."]
    for c in cats[:4]:
        lines.append(f"• {e(c['name'])} — {fmt_money(c['total'])} ({c['share_pct']}%)")
    if ctx["top_weekday_30"]:
        lines.append(f"Eng ko'p xarajat kuni: {ctx['top_weekday_30']}.")
    return "\n".join(lines)


def _sanitize(text: str) -> str:
    t = html.escape(text, quote=False)
    for tag in ("b", "i"):
        t = t.replace(f"&lt;{tag}&gt;", f"<{tag}>").replace(f"&lt;/{tag}&gt;", f"</{tag}>")
    return t.replace("**", "").strip()[:2000]


async def history(user: User, limit: int = 30) -> list[dict]:
    async with db.user_tx(user.id) as conn:
        return await chatrepo.recent(conn, user.id, limit)


async def clear(user: User) -> None:
    async with db.user_tx(user.id) as conn:
        await chatrepo.clear(conn, user.id)


async def ask(user: User, question: str) -> dict:
    """Savol → javob (saqlanadi). Qaytaradi: {"answer": html, "ai": bool}."""
    question = question.strip()[:MAX_QUESTION]
    ctx = await build_context(user)
    async with db.user_tx(user.id) as conn:
        hist = await chatrepo.recent(conn, user.id, HISTORY_TURNS * 2)
    s = get_settings()
    used_ai = False
    answer = ""
    if s.ai_enabled:
        try:
            messages = [{"role": "system", "content": CHAT_SYSTEM}]
            messages.append({"role": "system", "content": "<data>\n" + json.dumps(ctx, ensure_ascii=False, default=str) + "\n</data>"})
            for h in hist:
                messages.append({"role": h["role"], "content": h["content"][:1200]})
            messages.append({"role": "user", "content": question})
            raw = await ai.chat_messages(model=s.openai_insight_model, messages=messages, temperature=0.3, max_tokens=700)
            answer = _sanitize(raw)
            used_ai = bool(answer)
        except Exception as e:  # noqa: BLE001
            log.warning("ai chat failed: %s", ai.describe_error(e))
    if not answer:
        answer = _fallback_answer(ctx, question)
    async with db.user_tx(user.id) as conn:
        await chatrepo.add(conn, user.id, "user", question)
        await chatrepo.add(conn, user.id, "assistant", answer)
        await chatrepo.trim(conn, user.id)
    async with db.system_tx() as conn:
        await sysrepo.event(conn, "ai_chat", user.id, {"ai": used_ai})
    return {"answer": answer, "ai": used_ai}
