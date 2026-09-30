"""Superadmin bot buyruqlari (tezkor amallar). To'liq boshqaruv — mini app ichidagi admin panel."""
from __future__ import annotations

from aiogram import F, Router
from aiogram.filters import Command, CommandObject
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import CallbackQuery, Message

from app.bot import keyboards as kb
from app.bot.texts import uz as T
from app.core.timeutil import fmt_money
from app.db.database import db
from app.domain.models import User
from app.repositories import users as userrepo
from app.services import admin as admin_svc
from app.services import broadcast as bc

router = Router(name="admin")

HELP = (
    "🛡 <b>Admin buyruqlari</b>\n"
    "/admin — admin panel (mini app)\n"
    "/stats — qisqa statistika\n"
    "/aicheck — OpenAI kaliti va ovoz modelini tekshirish\n"
    "/pending — kutilayotgan to'lovlar\n"
    "/pro &lt;telegram_id&gt; &lt;tarif_kodi | kun&gt; — obuna ochish (masalan m1, m3, y1)\n"
    "/broadcast — reklama/chegirma postini barcha userlarga yuborish (rasm, video, matn)\n"
    "/block &lt;telegram_id&gt; [sabab] — bloklash\n"
    "/unblock &lt;telegram_id&gt; — blokdan chiqarish"
)


@router.message(F.text == T.BTN_ADMIN)
@router.message(Command("admin"))
async def admin_panel(message: Message, user: User):
    if not user.is_superadmin:
        return
    await message.answer(HELP, reply_markup=kb.open_dashboard("admin/", "🛡 Admin panelni ochish"))


@router.message(Command("aicheck"))
async def aicheck(message: Message, user: User):
    """OpenAI kaliti va modellarni tekshirish."""
    if not user.is_superadmin:
        return
    from app.services.ai import openai_client as ai
    msg = await message.answer("🔎 OpenAI tekshirilmoqda…")
    r = await ai.health_check()
    if not r.get("key_set"):
        return await msg.edit_text("❌ OPENAI_API_KEY .env da yo'q")
    import html
    lines = ["🤖 <b>OpenAI holati</b>"] + [f"• {k}: {html.escape(str(v))}" for k, v in r.items() if k != "key_set"]
    await msg.edit_text("\n".join(lines))


@router.message(Command("stats"))
async def stats(message: Message, user: User):
    if not user.is_superadmin:
        return
    s = await admin_svc.dashboard_stats()
    u, t, p = s["users"], s["transactions"], s["payments"]
    await message.answer(
        "📊 <b>Statistika</b>\n\n"
        f"👥 Userlar: <b>{u['users_total']}</b> (+{u['users_new_24h']} 24 soatda)\n"
        f"🔥 DAU: {u['dau']} · WAU: {u['wau']}\n"
        f"⭐️ PRO: {u['pro_active']} · 🎁 Trial: {u['trial_active']} · ⌛️ Tugagan: {u['expired']} · ⛔️ Blok: {u['blocked']}\n\n"
        f"🧾 Tranzaksiyalar 24s: {t['tx_24h']} (ovoz: {t['voice_24h']}) · jami: {t['tx_total']}\n"
        f"💳 Kutilmoqda: {p['pending']} · Bu oy: {p['approved_month']} ta / {fmt_money(p['revenue_month'])}"
    )


async def _target(message: Message, command: CommandObject) -> tuple[User | None, list[str]]:
    args = (command.args or "").split()
    if not args or not args[0].isdigit():
        await message.answer("Telegram ID kiriting. Masalan: /pro 123456789 30")
        return None, []
    async with db.system_tx() as conn:
        target = await userrepo.get_by_tg(conn, int(args[0]))
    if not target:
        await message.answer("User topilmadi (u avval botga /start bosishi kerak).")
        return None, []
    return target, args[1:]


@router.message(Command("pro"))
async def pro(message: Message, command: CommandObject, user: User):
    if not user.is_superadmin:
        return
    target, rest = await _target(message, command)
    if not target:
        return
    from app.services import billing
    arg = rest[0].lower() if rest else ""
    plan = await billing.get_plan(arg) if arg and not arg.isdigit() else None
    if plan:
        until = await admin_svc.grant_plan(user.telegram_id, target.id, plan["code"])
        label = plan["name"]
    elif arg.isdigit():
        until = await admin_svc.grant_pro(user.telegram_id, target.id, int(arg))
        label = f"{arg} kunlik"
    else:
        codes = " | ".join(f"{p['code']} ({p['name']})" for p in await billing.list_plans(active_only=False))
        return await message.answer(f"Masalan: /pro 123456789 m1\nTarif kodlari: {codes}\nYoki kun soni: /pro 123456789 45")
    await message.answer(f"✅ {target.telegram_id} ga {label} PRO ochildi ({until} gacha).")


@router.message(Command("block", "unblock"))
async def block(message: Message, command: CommandObject, user: User):
    if not user.is_superadmin:
        return
    target, rest = await _target(message, command)
    if not target:
        return
    blocked = command.command == "block"
    ok = await admin_svc.block(user.telegram_id, target.id, blocked, " ".join(rest) or None)
    await message.answer(("⛔️ Bloklandi" if blocked else "✅ Blokdan chiqarildi") if ok else "Bajarib bo'lmadi")


# ---------------- Ommaviy xabar: istalgan postni hammaga ----------------

def _bc_keyboard(msg_id: int, counts: dict[str, int]):
    from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

    def b(seg: str) -> InlineKeyboardButton:
        return InlineKeyboardButton(text=f"{bc.SEGMENT_LABELS[seg]} ({counts.get(seg, 0)})", callback_data=f"bc:{seg}:{msg_id}")

    return InlineKeyboardMarkup(inline_keyboard=[
        [b("all")],
        [b("trial"), b("expired")],
        [b("pro"), b("inactive7")],
        [InlineKeyboardButton(text="🧪 Avval o'zimga test", callback_data=f"bc:self:{msg_id}")],
        [InlineKeyboardButton(text="✖️ Bekor", callback_data="bc:cancel:0")],
    ])


class BroadcastPost(StatesGroup):
    waiting = State()


async def _ask_segment(message: Message, user: User, post_id: int):
    counts = {seg: await bc.count(seg, user.telegram_id) for seg in ("all", "trial", "expired", "pro", "inactive7")}
    await message.answer("☝️ Shu post kimlarga yuborilsin?", reply_markup=_bc_keyboard(post_id, counts))


@router.message(Command("broadcast"))
async def broadcast_cmd(message: Message, user: User, state: FSMContext):
    """Admin: /broadcast → keyingi yuborgan posti (rasm/video/matn) → segment tanlaydi → hammaga nusxalanadi.
    Yoki tayyor postga reply qilib /broadcast yozadi."""
    if not user.is_superadmin:
        return
    if message.reply_to_message:
        await state.clear()
        return await _ask_segment(message, user, message.reply_to_message.message_id)
    await state.set_state(BroadcastPost.waiting)
    await message.answer(
        "📣 <b>Ommaviy xabar</b>\n\nReklama yoki chegirma postini hozir yuboring — rasm, video yoki matn "
        "(formatlash bilan). Keyin kimlarga yuborishni tanlaysiz.\n\nBekor qilish: /cancel")


@router.message(Command("cancel"), BroadcastPost.waiting)
async def broadcast_cancel(message: Message, state: FSMContext):
    await state.clear()
    await message.answer("✖️ Bekor qilindi.")


@router.message(BroadcastPost.waiting)
async def broadcast_post(message: Message, user: User, state: FSMContext):
    await state.clear()
    if not user.is_superadmin:
        return
    await _ask_segment(message, user, message.message_id)


@router.callback_query(F.data.startswith("bc:"))
async def broadcast_cb(cb: CallbackQuery, user: User):
    if not user.is_superadmin:
        return await cb.answer("Faqat admin", show_alert=True)
    _, seg, mid = cb.data.split(":", 2)
    if seg == "cancel":
        await cb.answer("Bekor qilindi")
        return await cb.message.edit_text("✖️ Bekor qilindi.")
    if seg not in bc.SEGMENT_LABELS or not mid.isdigit():
        return await cb.answer()
    res = await bc.start_copy(user.telegram_id, seg, cb.message.chat.id, int(mid))
    await cb.answer("🚀 Yuborilmoqda")
    if seg == "self":
        return
    await cb.message.edit_text(f"🚀 <b>{bc.SEGMENT_LABELS[seg]}</b>: {res['queued']} ta userga yuborilmoqda…\n"
                               f"Tugagach hisobot keladi.")
