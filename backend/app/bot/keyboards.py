from __future__ import annotations

from aiogram.types import (
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    KeyboardButton,
    ReplyKeyboardMarkup,
    WebAppInfo,
)

from app.bot.texts import uz as T
from app.core.config import get_settings


def webapp_url(path: str = "") -> str:
    return get_settings().public_base_url.rstrip("/") + "/" + path.lstrip("/")


def main_menu(is_admin: bool = False) -> ReplyKeyboardMarkup:
    rows = [
        [KeyboardButton(text=T.BTN_DASHBOARD)],
        [KeyboardButton(text=T.BTN_TODAY), KeyboardButton(text=T.BTN_REPORTS)],
        [KeyboardButton(text=T.BTN_AI), KeyboardButton(text=T.BTN_DEBTS)],
        [KeyboardButton(text=T.BTN_EXPORT), KeyboardButton(text=T.BTN_PLAN)],
        [KeyboardButton(text=T.BTN_SETTINGS), KeyboardButton(text=T.BTN_HELP)] + ([KeyboardButton(text=T.BTN_ADMIN)] if is_admin else []),
    ]
    return ReplyKeyboardMarkup(
        resize_keyboard=True,
        is_persistent=True,
        input_field_placeholder="Masalan: taksiga 35 ming 🎙",
        keyboard=rows,
    )


def open_dashboard(path: str = "", text: str = "📊 Dashboardni ochish") -> InlineKeyboardMarkup:
    # Inline web_app tugmasi — initData (imzolangan user) mini appga uzatiladi
    return InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text=text, web_app=WebAppInfo(url=webapp_url(path)))]])


def tx_actions(items: list[dict]) -> InlineKeyboardMarkup:
    rows = []
    many = len(items) > 1
    for n, it in enumerate(items, 1):
        tid = str(it["id"])
        suffix = f" {n}" if many else ""
        rows.append([
            InlineKeyboardButton(text=f"✏️ Summa{suffix}", callback_data=f"tx:e:{tid}"),
            InlineKeyboardButton(text=f"🏷 Kategoriya{suffix}", callback_data=f"tx:c:{tid}"),
            InlineKeyboardButton(text=f"🗑{suffix}", callback_data=f"tx:d:{tid}"),
        ])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def undo_delete(tx_id: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="↩️ Qaytarish", callback_data=f"tx:r:{tx_id}")]])


def categories(tx_id: str, cats: list[dict]) -> InlineKeyboardMarkup:
    rows, row = [], []
    for c in cats:
        row.append(InlineKeyboardButton(text=f"{c['emoji']} {c['name']}"[:30], callback_data=f"tx:s:{tx_id}:{c['id']}"))
        if len(row) == 2:
            rows.append(row)
            row = []
    if row:
        rows.append(row)
    rows.append([InlineKeyboardButton(text="✖️ Yopish", callback_data="noop:close")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def confirm_pending(pid: str, alt_debt: bool = False) -> InlineKeyboardMarkup:
    rows = [[
        InlineKeyboardButton(text="✅ Tasdiqlash", callback_data=f"pd:ok:{pid}"),
        InlineKeyboardButton(text="❌ Bekor", callback_data=f"pd:no:{pid}"),
    ]]
    if alt_debt:
        rows.insert(0, [InlineKeyboardButton(text="🤝 Bu qarz edi", callback_data=f"pd:debt:{pid}")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def debt_actions(items: list[dict]) -> InlineKeyboardMarkup:
    rows = []
    many = len(items) > 1
    for n, it in enumerate(items, 1):
        did = str(it["id"])
        suffix = f" {n}" if many else ""
        rows.append([
            InlineKeyboardButton(text=f"✅ Qaytarildi{suffix}", callback_data=f"dbt:paid:{did}"),
            InlineKeyboardButton(text=f"⏰ Muddat{suffix}", callback_data=f"dbt:due:{did}"),
            InlineKeyboardButton(text=f"🗑{suffix}", callback_data=f"dbt:del:{did}"),
        ])
    rows.append([InlineKeyboardButton(text="📋 Barcha qarzlar", web_app=WebAppInfo(url=webapp_url("?tab=debts")))])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def debt_due_options(debt_id: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="+1 kun", callback_data=f"dbt:snooze:{debt_id}:1"),
         InlineKeyboardButton(text="+3 kun", callback_data=f"dbt:snooze:{debt_id}:3"),
         InlineKeyboardButton(text="+1 hafta", callback_data=f"dbt:snooze:{debt_id}:7"),
         InlineKeyboardButton(text="+1 oy", callback_data=f"dbt:snooze:{debt_id}:30")],
        [InlineKeyboardButton(text="✖️ Yopish", callback_data="noop:close")],
    ])


def debt_reminder(debt_id: str, direction: str) -> InlineKeyboardMarkup:
    label = "✅ Qaytardi" if direction == "given" else "✅ Qaytardim"
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=label, callback_data=f"dbt:paid:{debt_id}"),
         InlineKeyboardButton(text="⏰ +3 kun", callback_data=f"dbt:snooze:{debt_id}:3")],
        [InlineKeyboardButton(text="📋 Qarzlar", web_app=WebAppInfo(url=webapp_url("?tab=debts")))],
    ])


def debts_menu() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📋 Qarzlar ro'yxati (Dashboard)", web_app=WebAppInfo(url=webapp_url("?tab=debts")))],
    ])


def ai_chat_exit() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="💬 Chatda davom etish (Dashboard)", web_app=WebAppInfo(url=webapp_url("?tab=ai")))],
        [InlineKeyboardButton(text="✖️ Suhbatni tugatish", callback_data="aichat:exit")],
    ])


def amount_options(pid: str, options: list[int]) -> InlineKeyboardMarkup:
    from app.core.timeutil import fmt_money

    btns = [InlineKeyboardButton(text=fmt_money(v), callback_data=f"pd:a:{pid}:{v}") for v in options[:3]]
    return InlineKeyboardMarkup(inline_keyboard=[btns, [InlineKeyboardButton(text="❌ Bekor", callback_data=f"pd:no:{pid}")]])


def reports() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📅 Bugun", callback_data="rep:day"),
         InlineKeyboardButton(text="🗓 Hafta", callback_data="rep:week")],
        [InlineKeyboardButton(text="📆 Oy", callback_data="rep:month"),
         InlineKeyboardButton(text="📊 Yil", callback_data="rep:year")],
        [InlineKeyboardButton(text="📈 Grafiklar (Dashboard)", web_app=WebAppInfo(url=webapp_url()))],
    ])


def export_menu() -> InlineKeyboardMarkup:
    def row(label, p):
        return [InlineKeyboardButton(text=f"{label} · Excel", callback_data=f"exp:{p}:xlsx"),
                InlineKeyboardButton(text=f"{label} · CSV", callback_data=f"exp:{p}:csv")]
    return InlineKeyboardMarkup(inline_keyboard=[row("Kunlik", "day"), row("Haftalik", "week"),
                                                 row("Oylik", "month"), row("Yillik", "year")])


def ai_menu() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📅 Bugungi", callback_data="ai:daily"),
         InlineKeyboardButton(text="🗓 Haftalik chuqur", callback_data="ai:weekly")],
        [InlineKeyboardButton(text="💬 Savol berish (AI chat)", callback_data="aichat:start")],
    ])


def settings(report_enabled: bool) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=("🔕 Hisobotni o'chirish" if report_enabled else "🔔 Hisobotni yoqish"),
                              callback_data="set:toggle")],
        [InlineKeyboardButton(text="21:00", callback_data="set:t:21:00"),
         InlineKeyboardButton(text="22:00", callback_data="set:t:22:00"),
         InlineKeyboardButton(text="23:00", callback_data="set:t:23:00"),
         InlineKeyboardButton(text="23:59", callback_data="set:t:23:59")],
        [InlineKeyboardButton(text="🌍 Toshkent/Samarqand (UTC+5)", callback_data="set:z:Asia/Tashkent")],
        [InlineKeyboardButton(text="🌍 Moskva (UTC+3)", callback_data="set:z:Europe/Moscow"),
         InlineKeyboardButton(text="🌍 Almaty (UTC+5)", callback_data="set:z:Asia/Almaty")],
        [InlineKeyboardButton(text="🗑 Ma'lumotlarimni o'chirish", callback_data="del:ask")],
    ])


def plan(show_pay: bool) -> InlineKeyboardMarkup | None:
    """Obuna tugashi/eslatmalar ostidagi tugma → tariflar ro'yxati."""
    if not show_pay:
        return None
    return InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="💳 Tarifni tanlash", callback_data="pay:list")]])


def plans(items: list[dict]) -> InlineKeyboardMarkup:
    from app.core.timeutil import fmt_money_short

    rows = []
    for p in items:
        badge = f" {p['badge']}" if p.get("badge") else ""
        rows.append([InlineKeyboardButton(text=f"{p['name']} — {fmt_money_short(p['price'])} so'm{badge}"[:60],
                                          callback_data=f"pay:plan:{p['code']}")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def pay_plan(code: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="✅ To'lov qildim", callback_data=f"pay:done:{code}")],
        [InlineKeyboardButton(text="← Boshqa tarif", callback_data="pay:list")],
    ])


def send_receipt(admin_username: str | None) -> InlineKeyboardMarkup | None:
    if not admin_username:
        return None
    return InlineKeyboardMarkup(inline_keyboard=[[
        InlineKeyboardButton(text="📨 Chekni adminga yuborish", url=f"https://t.me/{admin_username.lstrip('@')}")
    ]])


def admin_payment(req_id: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[[
        InlineKeyboardButton(text="✅ Tasdiqlash", callback_data=f"pay:ok:{req_id}"),
        InlineKeyboardButton(text="❌ Rad etish", callback_data=f"pay:no:{req_id}"),
    ]])


def delete_confirm() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[[
        InlineKeyboardButton(text="⚠️ Ha, hammasini o'chir", callback_data="del:yes"),
        InlineKeyboardButton(text="Yo'q", callback_data="noop:close"),
    ]])
