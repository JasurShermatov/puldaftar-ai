"""Xarajat/daromad kiritish: matn va ovoz. Tahrirlash, kategoriya, o'chirish tugmalari."""
from __future__ import annotations

import io
import logging
from uuid import UUID

from aiogram import F, Router
from aiogram.enums import ChatAction
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import CallbackQuery, Message

from app.bot import keyboards as kb
from app.bot import views
from app.bot.texts import uz as T
from app.core.config import get_settings
from app.core.timeutil import fmt_money
from app.db.database import db
from app.domain.models import User
from app.repositories import categories as catrepo
from app.repositories import system as sysrepo
from app.repositories import transactions as txrepo
from app.services import ai_chat, ratelimit
from app.services import debts as debt_svc
from app.services import transactions as tx_svc
from app.services.access import access_of
from app.services.ai import openai_client as ai
from app.bot.states import AiChat
from app.services.parsing.normalize import normalize, tokenize
from app.services.parsing.numbers import find_amounts

log = logging.getLogger(__name__)
router = Router(name="entry")


class EditAmount(StatesGroup):
    waiting = State()


# ---------------- Natijani ko'rsatish ----------------

async def _render_outcome(user: User, out: tx_svc.IngestOutcome, reply_to: Message, edit: Message | None = None):
    async def say(text: str, markup=None):
        if edit:
            try:
                return await edit.edit_text(text, reply_markup=markup)
            except Exception:  # noqa: BLE001
                pass
        return await reply_to.answer(text, reply_markup=markup)

    if out.kind == "expired":
        return await say(T.EXPIRED, kb.plan(True))
    if out.kind == "duplicate":
        return await say(T.DUPLICATE)
    shown = False
    if out.repaid:
        await say(views.repaid_message(out.repaid, out.repay_status or "paid", user.timezone),
                  kb.debt_actions(out.repaid) if out.repay_status == "partial" else None)
        shown = True
    if out.saved:
        text = await views.saved_message(user, out.saved)
        if shown:
            await reply_to.answer(text, reply_markup=kb.tx_actions(out.saved))
        else:
            await say(text, kb.tx_actions(out.saved))
        shown = True
    if out.saved_debts:
        text = views.debt_saved_message(out.saved_debts, user.timezone)
        if shown:
            await reply_to.answer(text, reply_markup=kb.debt_actions(out.saved_debts))
        else:
            await say(text, kb.debt_actions(out.saved_debts))
        shown = True
    if out.pending_id and out.pending_kind in ("repay", "repay_pick"):
        text = views.repay_pending_message(out)
        if out.pending_kind == "repay":
            inc = any(i.get("type") == "income" for i in out.pending_items)
            markup = kb.confirm_repay(str(out.pending_id), out.has_fallback, out.has_alt_debt, inc)
        else:
            markup = kb.repay_pick(str(out.pending_id), out.repay_options, out.has_fallback)
        if shown:
            await reply_to.answer(text, reply_markup=markup)
        else:
            await say(text, markup)
        return
    if out.pending_id and (out.pending_items or out.pending_debts):
        text = views.pending_message(out.pending_items, out.question, out.pending_debts, user.timezone)
        markup = kb.confirm_pending(str(out.pending_id), alt_debt=out.has_alt_debt)
        if shown:
            await reply_to.answer(text, reply_markup=markup)
        else:
            await say(text, markup)
        return
    if shown:
        return
    if out.kind == "clarify":
        q = views.e(out.question or "Tushunmadim, qaytadan aniqroq yozing.")
        if out.pending_id and out.amount_options:
            return await say(f"❔ {q}", kb.amount_options(str(out.pending_id), out.amount_options))
        return await say(f"❔ {q}\n\n<i>Masalan: «Taksiga 35 ming»</i>")
    return await say(T.ERROR)


# ---------------- Summani tahrirlash (FSM) ----------------

@router.message(EditAmount.waiting, F.text)
async def edit_amount_value(message: Message, state: FSMContext, user: User):
    data = await state.get_data()
    spans = find_amounts(tokenize(normalize(message.text)))
    if not spans or spans[0].is_bare_small:
        # yalang'och kichik son "45" — 45 so'mmi yoki 45 mingmi? taxmin qilmaymiz
        return await message.answer(T.AMOUNT_BAD)
    amount = spans[0].value
    row = await tx_svc.update_tx(user, UUID(data["tx_id"]), amount=amount)
    await state.clear()
    if not row:
        return await message.answer(T.NOT_FOUND)
    await message.answer(T.AMOUNT_UPDATED.format(amount=fmt_money(amount)) + "\n" + views.tx_line(row, user.timezone),
                         reply_markup=kb.tx_actions([row]))


# ---------------- Matn ----------------

@router.message(AiChat.waiting, F.text & ~F.text.startswith("/"))
async def on_ai_chat_text(message: Message, user: User):
    await answer_ai_question(message, user, message.text.strip())


async def answer_ai_question(message: Message, user: User, question: str):
    if not access_of(user).can_ai:
        return await message.answer(T.AI_CHAT_PRO, reply_markup=kb.plan(True))
    if not await ratelimit.hit(f"aichat:{user.telegram_id}", 20, 3600):
        return await message.answer(T.TOO_FAST)
    await message.bot.send_chat_action(message.chat.id, ChatAction.TYPING)
    try:
        res = await ai_chat.ask(user, question)
    except Exception:  # noqa: BLE001
        log.exception("ai chat failed")
        return await message.answer(T.ERROR)
    await message.answer(res["answer"], reply_markup=kb.ai_chat_exit())


@router.message(F.text & ~F.text.startswith("/"))
async def on_text(message: Message, user: User, state: FSMContext):
    await state.clear()
    text = message.text.strip()
    if len(text) > get_settings().max_text_len:
        return await message.answer("Matn juda uzun. Qisqaroq yozing 🙂")
    await message.bot.send_chat_action(message.chat.id, ChatAction.TYPING)
    async with db.system_tx() as conn:
        await sysrepo.event(conn, "text_received", user.id)
    try:
        out = await tx_svc.ingest(user, text, source="text", source_key=f"{message.chat.id}:{message.message_id}")
    except Exception:  # noqa: BLE001
        log.exception("ingest failed")
        return await message.answer(T.ERROR)
    await _render_outcome(user, out, message)


# ---------------- Ovoz ----------------

@router.message(F.voice | F.audio | F.video_note)
async def on_voice(message: Message, user: User, state: FSMContext):
    if await state.get_state() != AiChat.waiting.state:
        await state.clear()
    s = get_settings()
    media = message.voice or message.audio or message.video_note
    if not s.ai_enabled:
        return await message.answer(T.VOICE_OFF)
    if (media.duration or 0) > s.max_voice_seconds:
        return await message.answer(T.VOICE_TOO_LONG.format(sec=s.max_voice_seconds))
    if (media.file_size or 0) > s.max_voice_bytes:
        return await message.answer(T.VOICE_TOO_LONG.format(sec=s.max_voice_seconds))
    status = await message.answer(T.PROCESSING_VOICE)
    async with db.system_tx() as conn:
        await sysrepo.event(conn, "voice_received", user.id, {"sec": media.duration})
    try:
        buf = io.BytesIO()
        await message.bot.download(media.file_id, destination=buf)   # xotirada, diskka yozilmaydi
        if message.video_note:
            ext = "mp4"
        elif message.voice:
            ext = "ogg"
        else:
            name = (message.audio.file_name or "a.mp3") if message.audio else "a.mp3"
            ext = name.rsplit(".", 1)[-1].lower() if "." in name else "mp3"
        transcript = await ai.transcribe(buf.getvalue(), f"voice.{ext}")
        buf.close()
    except Exception as e:  # noqa: BLE001  (STT timeout/provider down) — tranzaksiya yaratilmaydi
        log.warning("stt failed: %s", ai.describe_error(e))
        async with db.system_tx() as conn:
            await sysrepo.event(conn, "stt_failed", user.id)
        return await status.edit_text(T.VOICE_FAIL)
    if not transcript:
        return await status.edit_text(T.VOICE_FAIL)
    async with db.system_tx() as conn:
        await sysrepo.event(conn, "stt_success", user.id)
    if await state.get_state() == AiChat.waiting.state:
        await status.edit_text(f"🗣 <i>«{views.e(transcript[:300])}»</i>")
        return await answer_ai_question(message, user, transcript)
    try:
        out = await tx_svc.ingest(user, transcript, source="voice",
                                  source_key=f"{message.chat.id}:{message.message_id}")
    except Exception:  # noqa: BLE001
        log.exception("ingest failed")
        return await status.edit_text(T.ERROR)
    heard = f"🗣 <i>«{views.e(transcript[:300])}»</i>"
    # eshitilgan matnni ko'rsatamiz — user xatoni darhol ko'radi
    try:
        await status.edit_text(heard)
    except Exception:  # noqa: BLE001
        pass
    await _render_outcome(user, out, message)


# ---------------- Callback: tasdiq / summa tanlash ----------------

@router.callback_query(F.data.startswith("pd:"))
async def pending_cb(cb: CallbackQuery, user: User):
    parts = cb.data.split(":")
    try:
        pid = UUID(parts[2])
    except (IndexError, ValueError):
        return await cb.answer()
    if parts[1] in ("ok", "debt", "rp", "item", "pick"):
        choice = {"ok": "ok", "debt": "debt", "rp": "repay", "item": "item", "pick": "repay"}[parts[1]]
        pick = int(parts[3]) if parts[1] == "pick" and len(parts) == 4 and parts[3].isdigit() else None
        res = await tx_svc.confirm_pending(user, pid, choice=choice, pick=pick)
        await cb.answer()
        if not res.ok:
            return await cb.message.edit_text("Bu so'rov eskirgan yoki allaqachon saqlangan.")
        if res.repaid:
            await cb.message.edit_text(views.repaid_message(res.repaid, res.repay_status or "paid", user.timezone),
                                       reply_markup=kb.debt_actions(res.repaid) if res.repay_status == "partial" else None)
        if res.saved:
            if res.repaid:
                await cb.message.answer(await views.saved_message(user, res.saved), reply_markup=kb.tx_actions(res.saved))
            else:
                await cb.message.edit_text(await views.saved_message(user, res.saved), reply_markup=kb.tx_actions(res.saved))
        if res.saved_debts:
            text = views.debt_saved_message(res.saved_debts, user.timezone)
            if res.saved or res.repaid:
                await cb.message.answer(text, reply_markup=kb.debt_actions(res.saved_debts))
            else:
                await cb.message.edit_text(text, reply_markup=kb.debt_actions(res.saved_debts))
    elif parts[1] == "no":
        await tx_svc.cancel_pending(user, pid)
        await cb.answer()
        await cb.message.edit_text(T.CANCELLED)
    elif parts[1] == "a" and len(parts) == 4 and parts[3].isdigit():
        await cb.answer()
        out = await tx_svc.choose_amount(user, pid, int(parts[3]))
        await _render_outcome(user, out, cb.message, edit=cb.message)


# ---------------- Callback: tahrirlash ----------------

@router.callback_query(F.data.startswith("tx:"))
async def tx_cb(cb: CallbackQuery, user: User, state: FSMContext):
    parts = cb.data.split(":")
    action = parts[1]
    try:
        tx_id = UUID(parts[2])
    except (IndexError, ValueError):
        return await cb.answer()

    if action == "e":
        await state.set_state(EditAmount.waiting)
        await state.update_data(tx_id=str(tx_id))
        await cb.answer()
        return await cb.message.answer(T.ASK_AMOUNT)

    if action == "c":
        async with db.user_tx(user.id) as conn:
            tx = await txrepo.get(conn, user.id, tx_id)
            cats = await catrepo.list_for_user(conn, user.id)
        if not tx:
            return await cb.answer(T.NOT_FOUND, show_alert=True)
        cats = [c for c in cats if c["type"] == tx["type"]]
        await cb.answer()
        return await cb.message.answer(T.PICK_CATEGORY, reply_markup=kb.categories(str(tx_id), cats))

    if action == "s" and len(parts) == 4 and parts[3].isdigit():
        row = await tx_svc.recategorize(user, tx_id, int(parts[3]))
        if not row:
            return await cb.answer(T.NOT_FOUND, show_alert=True)
        await cb.answer("✅")
        return await cb.message.edit_text(
            T.CATEGORY_UPDATED.format(emoji=row["category_emoji"], name=views.e(row["category_name"]))
            + "\n" + views.tx_line(row, user.timezone)
        )

    if action == "d":
        ok = await tx_svc.delete_tx(user, tx_id)
        await cb.answer(T.DELETED if ok else T.NOT_FOUND)
        if ok:
            await cb.message.answer(T.DELETED, reply_markup=kb.undo_delete(str(tx_id)))
        return

    if action == "r":
        async with db.user_tx(user.id) as conn:
            ok = await txrepo.restore(conn, user.id, tx_id)
        await cb.answer(T.RESTORED if ok else T.NOT_FOUND)
        if ok:
            await cb.message.edit_text(T.RESTORED)


# ---------------- Callback: qarzlar ----------------

@router.callback_query(F.data.startswith("dbt:"))
async def debt_cb(cb: CallbackQuery, user: User):
    parts = cb.data.split(":")
    action = parts[1]
    try:
        debt_id = UUID(parts[2])
    except (IndexError, ValueError):
        return await cb.answer()

    if action == "paid":
        row = await debt_svc.pay(user, debt_id, None)
        if not row:
            return await cb.answer(T.NOT_FOUND, show_alert=True)
        await cb.answer(T.DEBT_PAID)
        return await cb.message.edit_text(views.repaid_message([row], "paid", user.timezone))

    if action == "due":
        await cb.answer()
        return await cb.message.answer(T.DEBT_DUE_PICK, reply_markup=kb.debt_due_options(str(debt_id)))

    if action == "snooze" and len(parts) == 4 and parts[3].isdigit():
        row = await debt_svc.snooze(user, debt_id, int(parts[3]))
        if not row:
            return await cb.answer(T.NOT_FOUND, show_alert=True)
        from app.core.timeutil import tz as _tz
        date_s = row["due_at"].astimezone(_tz(user.timezone)).strftime("%d.%m.%Y")
        await cb.answer(T.DEBT_SNOOZED.format(date=date_s))
        try:
            await cb.message.edit_text(views.debt_saved_message([row], user.timezone).replace("Qarz yozildi", "Muddat yangilandi"),
                                       reply_markup=kb.debt_actions([row]))
        except Exception:  # noqa: BLE001
            await cb.message.answer(views.debt_saved_message([row], user.timezone).replace("Qarz yozildi", "Muddat yangilandi"),
                                    reply_markup=kb.debt_actions([row]))
        return

    if action == "del":
        ok = await debt_svc.delete(user, debt_id)
        await cb.answer(T.DEBT_DELETED if ok else T.NOT_FOUND)
        if ok:
            try:
                await cb.message.edit_text(T.DEBT_DELETED)
            except Exception:  # noqa: BLE001
                pass
