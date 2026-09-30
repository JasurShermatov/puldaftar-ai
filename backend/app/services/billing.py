"""To'lov (qo'lda tasdiqlash): user kartaga o'tkazadi → "To'lov qildim" → admin chekni ko'radi → Tasdiqlash.

Approve atomik: payment_request FOR UPDATE → status tekshiruv → approved → PRO uzaytirish → audit.
Ikki marta bosilsa ham faqat bitta PRO qo'shiladi (idempotent).
"""
from __future__ import annotations

import html
import logging
from dataclasses import dataclass
from uuid import UUID

from app.core.timeutil import fmt_money, tz
from app.db.database import db
from app.domain.models import User
from app.repositories import payments as payrepo
from app.repositories import plans as planrepo
from app.repositories import system as sysrepo
from app.repositories import users as userrepo

log = logging.getLogger(__name__)


@dataclass
class Decision:
    ok: bool
    message: str
    user_tg_id: int | None = None
    pro_until: str | None = None


async def billing_config() -> dict:
    async with db.system_tx() as conn:
        return await sysrepo.get_setting(conn, "billing")


async def list_plans(active_only: bool = True) -> list[dict]:
    async with db.system_tx() as conn:
        return await planrepo.list_plans(conn, active_only)


async def get_plan(code: str) -> dict | None:
    async with db.system_tx() as conn:
        return await planrepo.get(conn, code)


async def create_request(user: User, plan_code: str) -> tuple[dict, bool, dict, dict] | None:
    """(ariza, yangi_yaratildimi, billing_config, tarif) yoki tarif topilmasa None."""
    cfg = await billing_config()
    async with db.system_tx() as conn:
        plan = await planrepo.get(conn, plan_code)
        if not plan or not plan["is_active"]:
            return None
        req, created = await payrepo.create_pending(conn, user.id, plan)
        if created:
            await sysrepo.event(conn, "payment_started", user.id, {"plan": plan_code})
    return req, created, cfg, plan


async def approve(req_id: UUID, admin_tg_id: int) -> Decision:
    async with db.system_tx() as conn:
        req = await payrepo.get_for_update(conn, req_id)
        if not req:
            return Decision(False, "Ariza topilmadi")
        if req["status"] != "pending":
            return Decision(False, f"Ariza allaqachon: {req['status']}")
        await payrepo.decide(conn, req_id, "approved", admin_tg_id)
        pro_until = await userrepo.extend_pro(conn, req["user_id"], req["days"])
        await sysrepo.audit(conn, admin_tg_id, "payment.approve", req["user_id"],
                            {"request_id": str(req_id), "plan": req.get("plan_code"), "amount": req["amount"],
                             "days": req["days"]})
        await sysrepo.event(conn, "payment_success", req["user_id"])
        u = await userrepo.get(conn, req["user_id"])
    return Decision(True, "Tasdiqlandi", u.telegram_id, pro_until.astimezone(tz(u.timezone)).strftime("%d.%m.%Y"))


async def reject(req_id: UUID, admin_tg_id: int, reason: str | None = None) -> Decision:
    async with db.system_tx() as conn:
        req = await payrepo.get_for_update(conn, req_id)
        if not req:
            return Decision(False, "Ariza topilmadi")
        if req["status"] != "pending":
            return Decision(False, f"Ariza allaqachon: {req['status']}")
        await payrepo.decide(conn, req_id, "rejected", admin_tg_id, reason)
        await sysrepo.audit(conn, admin_tg_id, "payment.reject", req["user_id"], {"request_id": str(req_id), "reason": reason})
        u = await userrepo.get(conn, req["user_id"])
    return Decision(True, "Rad etildi", u.telegram_id)


def approved_text(pro_until: str) -> str:
    return (f"🎉 <b>PRO faollashtirildi!</b>\n\nTo'lovingiz tasdiqlandi. PRO muddati: <b>{pro_until}</b> gacha.\n"
            f"Rahmat! Endi barcha funksiyalar ochiq ✅")


def rejected_text(reason: str | None) -> str:
    r = f"\nSabab: {reason}" if reason else ""
    return (f"❌ To'lov tasdiqlanmadi.{r}\n\nAgar xato bo'lsa, «💳 Obuna» bo'limidan qayta urinib ko'ring yoki "
            f"admin bilan bog'laning.")


def price_line(plan: dict) -> str:
    name = html.escape(plan["name"])
    old = f" <s>{fmt_money(plan['old_price'])}</s>" if plan.get("old_price") and plan["old_price"] > plan["price"] else ""
    badge = f"  {html.escape(plan['badge'])}" if plan.get("badge") else ""
    per_month = plan["price"] * 30 // plan["days"]
    pm = f"  <i>(oyiga ~{fmt_money(per_month)})</i>" if plan["days"] > 31 else ""
    return f"<b>{name}</b> — <b>{fmt_money(plan['price'])}</b>{old}{badge}{pm}"


def plans_text(plans: list[dict]) -> str:
    lines = ["💳 <b>PRO obuna tariflari</b>", ""]
    for p in plans:
        lines.append("• " + price_line(p))
    lines += ["", "PRO: cheksiz ovozli/matnli yozuv, kunlik hisobot, AI tahlil, Excel/CSV yuklab olish.",
              "👇 Tarifni tanlang:"]
    return "\n".join(lines)


def payment_instructions(cfg: dict, plan: dict) -> str:
    card = html.escape(cfg.get("card_number") or "— (admin hali kiritmagan)")
    holder = html.escape(cfg.get("card_holder") or "")
    return (
        f"💳 <b>{html.escape(plan['name'])} PRO</b> — {plan['days']} kun\n\n"
        f"To'lov summasi: <b>{fmt_money(plan['price'])}</b>\n\n"
        f"Karta raqami:\n<code>{card}</code>\n"
        + (f"Qabul qiluvchi: <b>{holder}</b>\n" if holder else "")
        + "\n1️⃣ Yuqoridagi kartaga aniq summani o'tkazing (raqam ustiga bossangiz nusxalanadi)\n"
          "2️⃣ «✅ To'lov qildim» tugmasini bosing\n"
          "3️⃣ Chek (skrinshot)ni adminga yuboring\n"
          "4️⃣ Admin tasdiqlagach PRO avtomatik yoqiladi"
    )
