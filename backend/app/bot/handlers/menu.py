"""/start, menyu tugmalari, hisobotlar, AI tahlil, eksport, sozlamalar, o'chirish."""
from __future__ import annotations

import logging

from aiogram import F, Router
from aiogram.filters import Command, CommandObject, CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message

from app.bot import keyboards as kb
from app.bot import views
from app.bot.texts import uz as T
from app.core.timeutil import local_now, tz
from app.db.database import db
from app.domain.models import User
from app.repositories import system as sysrepo
from app.repositories import users as userrepo
from app.bot.states import AiChat
from app.services import debts as debt_svc
from app.services import export as export_svc
from app.services import insights as insight_svc
from app.services import ratelimit
from app.services import reports as report_svc
from app.services.access import access_of
from app.services.billing import billing_config

log = logging.getLogger(__name__)
router = Router(name="menu")


@router.message(CommandStart())
async def start(message: Message, user: User, user_created: bool, state: FSMContext):
    await state.clear()
    name = views.e(message.from_user.first_name or "do'st")
    if user_created:
        cfg = await billing_config()
        end = user.trial_ends_at.astimezone(tz(user.timezone)).strftime("%d.%m.%Y")
        await message.answer(T.WELCOME.format(name=name, trial_days=cfg.get("trial_days", 7), trial_end=end),
                             reply_markup=kb.main_menu(user.is_superadmin))
        async with db.system_tx() as conn:
            await sysrepo.event(conn, "trial_started", user.id)
    else:
        await message.answer(T.WELCOME_BACK.format(name=name), reply_markup=kb.main_menu(user.is_superadmin))
    if user.is_superadmin:
        await message.answer("🛡 Siz <b>superadmin</b>siz. Boshqaruv: «🛡 Admin panel» tugmasi yoki /admin")
    await message.answer("👇 Grafiklar va to'liq statistika:", reply_markup=kb.open_dashboard())


@router.message(Command("help"))
@router.message(F.text == T.BTN_HELP)
async def help_(message: Message, user: User, state: FSMContext):
    await state.clear()
    await message.answer(T.HELP, reply_markup=kb.main_menu(user.is_superadmin))


@router.message(Command("dashboard"))
@router.message(F.text == T.BTN_DASHBOARD)
async def dashboard(message: Message, state: FSMContext):
    await state.clear()
    await message.answer("📊 Dashboard — kunlik, haftalik, oylik va yillik grafiklar:", reply_markup=kb.open_dashboard())


@router.message(Command("today"))
@router.message(F.text == T.BTN_TODAY)
async def today(message: Message, user: User, state: FSMContext):
    await state.clear()
    text = await report_svc.daily_report_text(user, local_now(user.timezone).date(), final=False)
    await message.answer(text, reply_markup=kb.open_dashboard(text="📊 Batafsil"))


@router.message(F.text == T.BTN_REPORTS)
@router.message(Command("report"))
async def reports_menu(message: Message, state: FSMContext):
    await state.clear()
    await message.answer(T.REPORTS_PICK, reply_markup=kb.reports())


@router.message(Command("week", "month", "year"))
async def period_cmd(message: Message, user: User):
    period = message.text.split()[0].lstrip("/").split("@")[0]
    await message.answer(await report_svc.period_report_text(user, period))


@router.callback_query(F.data.startswith("rep:"))
async def report_cb(cb: CallbackQuery, user: User):
    period = cb.data.split(":")[1]
    if period not in ("day", "week", "month", "year"):
        return await cb.answer()
    await cb.answer()
    await cb.message.answer(await report_svc.period_report_text(user, period))


@router.message(Command("ai"))
@router.message(F.text == T.BTN_AI)
async def ai_menu(message: Message, user: User, state: FSMContext, command: CommandObject | None = None):
    if not access_of(user).can_ai:
        return await message.answer(T.EXPIRED, reply_markup=kb.plan(True))
    # "/ai savol" — to'g'ridan-to'g'ri AI chat javobi
    if command is not None and command.args:
        from app.bot.handlers.entry import answer_ai_question
        await state.set_state(AiChat.waiting)
        return await answer_ai_question(message, user, command.args.strip())
    await state.clear()
    msg = await message.answer(T.AI_THINKING)
    text = await insight_svc.generate(user, "weekly")
    await msg.edit_text(text, reply_markup=kb.ai_menu())


@router.callback_query(F.data == "aichat:start")
async def ai_chat_start(cb: CallbackQuery, user: User, state: FSMContext):
    if not access_of(user).can_ai:
        return await cb.answer(T.AI_CHAT_PRO, show_alert=True)
    await state.set_state(AiChat.waiting)
    await cb.answer()
    await cb.message.answer(T.AI_CHAT_START, reply_markup=kb.ai_chat_exit())


@router.callback_query(F.data == "aichat:exit")
async def ai_chat_exit(cb: CallbackQuery, state: FSMContext):
    await state.clear()
    await cb.answer()
    try:
        await cb.message.edit_reply_markup(reply_markup=None)
    except Exception:  # noqa: BLE001
        pass
    await cb.message.answer(T.AI_CHAT_EXIT)


# ---------------- Qarzlar ----------------

@router.message(Command("debts"))
@router.message(F.text == T.BTN_DEBTS)
async def debts_menu(message: Message, user: User, state: FSMContext):
    await state.clear()
    data = await debt_svc.list_debts(user, "open")
    await message.answer(debt_svc.list_text(data, user.timezone), reply_markup=kb.debts_menu())


@router.callback_query(F.data.startswith("ai:"))
async def ai_cb(cb: CallbackQuery, user: User):
    kind = cb.data.split(":")[1]
    if kind not in ("daily", "weekly") or not access_of(user).can_ai:
        return await cb.answer("PRO kerak", show_alert=True)
    await cb.answer("🧠 …")
    force = await ratelimit.hit(f"insight:{user.telegram_id}", 5, 3600)
    text = await insight_svc.generate(user, kind, force=force)
    try:
        await cb.message.edit_text(text, reply_markup=kb.ai_menu())
    except Exception:  # noqa: BLE001  (matn o'zgarmagan bo'lsa Telegram xato beradi)
        pass


@router.message(Command("export"))
@router.message(F.text == T.BTN_EXPORT)
async def export_menu(message: Message, user: User, state: FSMContext):
    await state.clear()
    if not access_of(user).can_export:
        return await message.answer(T.EXPORT_PRO, reply_markup=kb.plan(True))
    await message.answer(T.EXPORT_PICK, reply_markup=kb.export_menu())


@router.callback_query(F.data.startswith("exp:"))
async def export_cb(cb: CallbackQuery, user: User):
    _, period, fmt = cb.data.split(":")
    if period not in ("day", "week", "month", "year") or fmt not in ("xlsx", "csv"):
        return await cb.answer()
    if not access_of(user).can_export:
        return await cb.answer(T.EXPORT_PRO, show_alert=True)
    if not await ratelimit.hit(f"export:{user.telegram_id}", 10, 600):
        return await cb.answer(T.TOO_FAST, show_alert=True)
    await cb.answer(T.EXPORT_SENDING)
    fn = export_svc.export_xlsx if fmt == "xlsx" else export_svc.export_csv
    name, data = await fn(user, period)
    from aiogram.types import BufferedInputFile
    await cb.message.answer_document(BufferedInputFile(data, filename=name),
                                     caption=f"📥 {export_svc.PERIOD_LABEL[period].capitalize()} hisobot")


# ---------------- Sozlamalar ----------------

def _settings_text(user: User) -> str:
    return T.SETTINGS.format(report="yoqilgan ✅" if user.report_enabled else "o'chirilgan 🔕",
                             time=user.report_time, tz=user.timezone)


@router.message(Command("settings"))
@router.message(F.text == T.BTN_SETTINGS)
async def settings(message: Message, user: User, state: FSMContext):
    await state.clear()
    await message.answer(_settings_text(user), reply_markup=kb.settings(user.report_enabled))


@router.callback_query(F.data.startswith("set:"))
async def settings_cb(cb: CallbackQuery, user: User):
    parts = cb.data.split(":", 2)
    async with db.user_tx(user.id) as conn:
        if parts[1] == "toggle":
            await userrepo.update_settings(conn, user.id, report_enabled=not user.report_enabled)
        elif parts[1] == "t" and parts[2] in ("21:00", "22:00", "23:00", "23:59"):
            await userrepo.update_settings(conn, user.id, report_time=parts[2])
        elif parts[1] == "z" and parts[2] in ("Asia/Tashkent", "Europe/Moscow", "Asia/Almaty"):
            await userrepo.update_settings(conn, user.id, timezone=parts[2])
        fresh = await userrepo.get(conn, user.id)
    await cb.answer("✅ Saqlandi")
    try:
        await cb.message.edit_text(_settings_text(fresh), reply_markup=kb.settings(fresh.report_enabled))
    except Exception:  # noqa: BLE001
        pass


# ---------------- Ma'lumotlarni o'chirish ----------------

@router.message(Command("delete_me"))
async def delete_me(message: Message):
    await message.answer(T.DELETE_CONFIRM, reply_markup=kb.delete_confirm())


@router.callback_query(F.data == "del:ask")
async def delete_ask(cb: CallbackQuery):
    await cb.answer()
    await cb.message.answer(T.DELETE_CONFIRM, reply_markup=kb.delete_confirm())


@router.callback_query(F.data == "del:yes")
async def delete_yes(cb: CallbackQuery, user: User):
    if user.is_superadmin:
        return await cb.answer("Superadmin o'chira olmaydi", show_alert=True)
    async with db.system_tx() as conn:
        await userrepo.delete(conn, user.id)
        await sysrepo.event(conn, "account_deleted", None)
    await cb.answer()
    await cb.message.edit_text(T.DELETE_DONE)


@router.callback_query(F.data.startswith("noop:"))
async def noop(cb: CallbackQuery):
    await cb.answer()
    try:
        await cb.message.delete()
    except Exception:  # noqa: BLE001
        pass
