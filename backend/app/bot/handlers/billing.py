"""Obuna/to'lov: 💳 Obuna → karta → ✅ To'lov qildim → chekni adminga → admin tasdiqlaydi → PRO."""
from __future__ import annotations

import logging
from uuid import UUID

from aiogram import F, Router
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message

from app.bot import keyboards as kb
from app.bot import views
from app.bot.texts import uz as T
from app.core.config import get_settings
from app.core.timeutil import fmt_money
from app.db.database import db
from app.domain.models import User
from app.repositories import payments as payrepo
from app.services import billing, notifier

log = logging.getLogger(__name__)
router = Router(name="billing")


async def _admin_ids() -> list[int]:
    return list(dict.fromkeys(get_settings().superadmin_ids))   # faqat .env dagi superadminlar


async def _show_plans(target: Message, user: User, edit: bool = False):
    items = await billing.list_plans()
    text = views.plan_text(user) + billing.plans_text(items)
    markup = None if user.is_superadmin else kb.plans(items)
    if edit:
        try:
            return await target.edit_text(text, reply_markup=markup)
        except Exception:  # noqa: BLE001
            pass
    await target.answer(text, reply_markup=markup)


@router.message(Command("plan"))
@router.message(F.text == T.BTN_PLAN)
async def plan(message: Message, user: User, state: FSMContext):
    await state.clear()
    await _show_plans(message, user)


@router.callback_query(F.data == "pay:list")
async def plan_list(cb: CallbackQuery, user: User):
    await cb.answer()
    await _show_plans(cb.message, user, edit=True)


@router.callback_query(F.data.startswith("pay:plan:"))
async def plan_pick(cb: CallbackQuery, user: User):
    code = cb.data.split(":", 2)[2]
    p = await billing.get_plan(code)
    if not p or not p["is_active"]:
        return await cb.answer("Bu tarif hozir mavjud emas", show_alert=True)
    cfg = await billing.billing_config()
    await cb.answer()
    try:
        await cb.message.edit_text(billing.payment_instructions(cfg, p), reply_markup=kb.pay_plan(code))
    except Exception:  # noqa: BLE001
        await cb.message.answer(billing.payment_instructions(cfg, p), reply_markup=kb.pay_plan(code))


@router.callback_query(F.data.startswith("pay:done:"))
async def pay_done(cb: CallbackQuery, user: User):
    code = cb.data.split(":", 2)[2]
    res = await billing.create_request(user, code)
    if not res:
        return await cb.answer("Bu tarif hozir mavjud emas", show_alert=True)
    req, created, cfg, p = res
    await cb.answer()
    admin_username = cfg.get("admin_username")
    text = (T.PAY_CREATED if created else T.PAY_EXISTS) + f"\n\n🧾 Tarif: <b>{views.e(p['name'])}</b> — {fmt_money(p['price'])}"
    if not admin_username:
        text += "\n\n" + T.PAY_NO_ADMIN
    await cb.message.answer(text, reply_markup=kb.send_receipt(admin_username))
    who = f"@{user.username}" if user.username else views.e(user.first_name or "")
    note = (f"🧾 <b>{'Yangi' if created else 'Yangilangan'} to'lov arizasi</b>\n\n👤 {who} (ID: <code>{user.telegram_id}</code>)\n"
            f"📦 {views.e(p['name'])} · {req['days']} kun\n💰 {fmt_money(req['amount'])}\n🆔 <code>{req['id']}</code>\n\n"
            f"Chekni tekshirib, pul kelganini bank ilovasida tasdiqlang.")
    for aid in await _admin_ids():
        await notifier.send(aid, note, reply_markup=kb.admin_payment(str(req["id"])))


@router.message(F.photo | F.document)
async def receipt(message: Message, user: User):
    """User chekni botning o'ziga yuborsa — pending ariza bo'lsa adminlarga forward qilinadi."""
    async with db.system_tx() as conn:
        req = await conn.fetchrow(
            """SELECT p.id, p.amount, p.days, coalesce(pl.name, '') AS plan_name FROM payment_requests p
               LEFT JOIN plans pl ON pl.code=p.plan_code WHERE p.user_id=$1 AND p.status='pending'""", user.id)
    if not req:
        return await message.answer("Rasm/fayl qabul qilinmadi. Xarajatni matn yoki ovoz bilan yuboring 🎙")
    if message.document and (message.document.file_size or 0) > 10 * 1024 * 1024:
        return await message.answer("Fayl juda katta (maks. 10 MB).")
    who = f"@{user.username}" if user.username else views.e(user.first_name or "")
    caption = (f"🧾 <b>Chek</b> — {who} (ID: <code>{user.telegram_id}</code>)\n"
               f"📦 {views.e(req['plan_name'])} · {req['days']} kun · 💰 {fmt_money(req['amount'])}\n🆔 <code>{req['id']}</code>")
    for aid in await _admin_ids():
        try:
            await message.copy_to(aid)
            await notifier.send(aid, caption, reply_markup=kb.admin_payment(str(req["id"])))
        except Exception as e:  # noqa: BLE001
            log.warning("receipt forward failed: %s", type(e).__name__)
    await message.answer(T.PAY_RECEIPT_FORWARDED)


@router.callback_query(F.data.startswith("pay:ok:") | F.data.startswith("pay:no:"))
async def admin_decide(cb: CallbackQuery, user: User):
    if not user.is_superadmin:
        return await cb.answer("Faqat admin", show_alert=True)
    _, action, rid = cb.data.split(":", 2)
    try:
        req_id = UUID(rid)
    except ValueError:
        return await cb.answer()
    if action == "ok":
        d = await billing.approve(req_id, user.telegram_id)
        if d.ok:
            await notifier.send(d.user_tg_id, billing.approved_text(d.pro_until))
            status = f"✅ Tasdiqlandi — PRO {d.pro_until} gacha"
        else:
            status = f"ℹ️ {d.message}"
    else:
        d = await billing.reject(req_id, user.telegram_id, "Chek tasdiqlanmadi")
        if d.ok:
            await notifier.send(d.user_tg_id, billing.rejected_text("Chek tasdiqlanmadi"))
        status = "❌ Rad etildi" if d.ok else f"ℹ️ {d.message}"
    await cb.answer(status[:190], show_alert=False)
    try:
        await cb.message.edit_text((cb.message.html_text or "") + f"\n\n<b>{status}</b>")
    except Exception:  # noqa: BLE001
        pass


@router.message(Command("pending"))
async def pending_list(message: Message, user: User):
    if not user.is_superadmin:
        return
    async with db.system_tx() as conn:
        rows = await payrepo.list_requests(conn, "pending", 20, 0)
    if not rows:
        return await message.answer("Kutilayotgan to'lovlar yo'q ✅")
    for r in rows:
        who = f"@{r['username']}" if r["username"] else views.e(r["first_name"] or "")
        await message.answer(
            f"🧾 {who} (<code>{r['telegram_id']}</code>) — {views.e(r['plan_name'] or '')} · {fmt_money(r['amount'])} · {r['days']} kun\n"
            f"🕐 {r['created_at']:%d.%m.%Y %H:%M} UTC",
            reply_markup=kb.admin_payment(str(r["id"])),
        )
