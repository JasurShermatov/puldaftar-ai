"""Bot matnlari (o'zbek). Boshqa til qo'shish uchun shu faylni nusxalang (ru.py) — kod o'zgarmaydi."""

BTN_DASHBOARD = "📊 Dashboard"
BTN_TODAY = "📅 Bugun"
BTN_REPORTS = "📈 Hisobotlar"
BTN_AI = "🧠 AI tahlil"
BTN_EXPORT = "📥 Yuklab olish"
BTN_PLAN = "💳 Obuna"
BTN_SETTINGS = "⚙️ Sozlamalar"
BTN_HELP = "❓ Yordam"
BTN_ADMIN = "🛡 Admin panel"

WELCOME = (
    "Assalomu alaykum, <b>{name}</b>! 👋\n\n"
    "Men — <b>Hisobchi AI</b>. Xarajatlaringizni siz uchun hisoblab boraman.\n\n"
    "🗣 <b>Gapiring yoki yozing — hisobni men yuritaman:</b>\n"
    "• «Bugun taksiga 35 ming, obedga 80 ming ketdi»\n"
    "• «Kecha benzin 300 ming»\n"
    "• «Oylik 6 million tushdi»\n\n"
    "🕛 Har kuni soat <b>23:59</b> da kunlik hisobot yuboraman.\n"
    "📊 Grafiklar va to'liq statistika — <b>Dashboard</b>da.\n\n"
    "🎁 Sizga <b>{trial_days} kun bepul</b> PRO berildi (tugash sanasi: {trial_end})."
)
WELCOME_BACK = "Qaytganingizdan xursandman, <b>{name}</b>! Xarajatni yozing yoki ovozli xabar yuboring 🎙"

HELP = (
    "❓ <b>Qanday foydalaniladi</b>\n\n"
    "Shunchaki oddiy gapiring yoki yozing — bot summani, nimaga ketganini va vaqtini o'zi ajratadi.\n\n"
    "<b>Misollar:</b>\n"
    "• Taksiga 35 ming\n"
    "• Bugun obedga 80 ming, kofega 25 ming ketdi\n"
    "• Kecha bozorga 1 yarim million\n"
    "• Kartadan 250 ming kommunal to'ladim\n"
    "• Segodnya reklama 800 ming rasxod\n"
    "• Oylik 6 mln tushdi  (daromad)\n\n"
    "<b>Summa formatlari:</b> 35 ming, 1.2 mln, 800k, ikki yarim million, 4 million 300 ming\n\n"
    "<b>Tugmalar:</b>\n"
    "📅 Bugun — bugungi ro'yxat\n📈 Hisobotlar — hafta/oy/yil\n🧠 AI tahlil — nimaga ko'p pul ketyapti\n"
    "📥 Yuklab olish — Excel/CSV\n📊 Dashboard — grafiklar\n\n"
    "Har bir saqlangan yozuv ostida ✏️ tahrirlash, 🏷 kategoriya va 🗑 o'chirish tugmalari bor.\n\n"
    "Buyruqlar: /today /week /month /year /export /settings /plan /delete_me"
)

PROCESSING_VOICE = "🎧 Qabul qildim, hisoblayapman…"
PROCESSING_TEXT = "⏳ Hisoblayapman…"
SAVED_HEADER = "✅ <b>Saqlandi</b>"
TODAY_TOTAL = "📊 Bugun jami xarajat: <b>{total}</b>"
DUPLICATE = "Bu xabar allaqachon hisobga olingan ✅"
CONFIRM_HEADER = "🤔 <b>Shu to'g'rimi?</b>"
CONFIRM_SAVED = "✅ Tasdiqlandi va saqlandi."
CANCELLED = "❌ Bekor qilindi."
DELETED = "🗑 O'chirildi."
RESTORED = "↩️ Qaytarildi."
ASK_AMOUNT = "✏️ Yangi summani yozing (masalan: <i>45 ming</i> yoki <i>45000</i>):"
AMOUNT_UPDATED = "✅ Summa yangilandi: <b>{amount}</b>"
AMOUNT_BAD = "Summani tushunmadim. Masalan: 45 ming"
PICK_CATEGORY = "🏷 Kategoriyani tanlang:"
CATEGORY_UPDATED = "✅ Kategoriya: <b>{emoji} {name}</b>\nKeyingi safar shunga o'xshash yozuvlarni shu kategoriyaga yozaman."
NOT_FOUND = "Yozuv topilmadi."
VOICE_OFF = "🎙 Ovozli rejim hozircha sozlanmagan. Iltimos, matn bilan yozing."
VOICE_TOO_LONG = "🎙 Ovozli xabar juda uzun (maks. {sec} soniya). Qisqaroq qilib yuboring."
VOICE_FAIL = "😕 Ovozni tanib bo'lmadi. Qaytadan, sekinroq ayting yoki matn bilan yozing."
TOO_FAST = "⏱ Juda tez! Bir necha soniyadan keyin qayta urinib ko'ring."
BLOCKED = "⛔️ Hisobingiz bloklangan. Savollar bo'lsa admin bilan bog'laning."
EXPIRED = (
    "⌛️ <b>Bepul davr tugadi.</b>\n\nYangi xarajat yozish uchun PRO obunani faollashtiring. "
    "Eski ma'lumotlaringiz saqlanib qoladi va ko'rish mumkin."
)
ERROR = "😕 Nimadir xato ketdi. Iltimos, qaytadan urinib ko'ring."

REPORTS_PICK = "📈 Qaysi davr bo'yicha hisobot?"
EXPORT_PICK = "📥 Qaysi davr va qaysi formatda yuklab olasiz?"
EXPORT_SENDING = "⏳ Fayl tayyorlanmoqda…"
EXPORT_PRO = "📥 Yuklab olish PRO foydalanuvchilar uchun."
AI_THINKING = "🧠 Tahlil qilyapman…"

SETTINGS = (
    "⚙️ <b>Sozlamalar</b>\n\n"
    "🕛 Kunlik hisobot: <b>{report}</b>\n"
    "⏰ Hisobot vaqti: <b>{time}</b>\n"
    "🌍 Vaqt zonasi: <b>{tz}</b>"
)

PLAN_TRIAL = "🎁 Holat: <b>Bepul sinov (PRO)</b>\n⏳ Qoldi: <b>{days} kun</b> ({end} gacha)\n\n"
PLAN_PRO = "⭐️ Holat: <b>PRO</b>\n⏳ Muddati: <b>{end}</b> gacha ({days} kun qoldi)\n\n"
PLAN_EXPIRED = "⌛️ Holat: <b>Muddati tugagan</b>\n\n"
PAY_CREATED = (
    "🧾 <b>Ariza qabul qilindi!</b>\n\n"
    "Endi to'lov chekini (skrinshot) adminga yuboring 👇\n"
    "Admin tekshirib tasdiqlashi bilan PRO avtomatik yoqiladi va sizga xabar keladi.\n\n"
    "💡 Chekni shu botning o'ziga ham yuborishingiz mumkin — adminga yetkaziladi."
)
PAY_EXISTS = "🧾 Sizda tekshiruvdagi ariza bor. Chekni adminga yuboring 👇"
PAY_RECEIPT_FORWARDED = "📨 Chek adminga yuborildi. Tasdiqlanishini kuting ✅"
PAY_NO_ADMIN = "Admin kontakti hali sozlanmagan. Chekni shu botga rasm qilib yuboring."

DELETE_CONFIRM = (
    "⚠️ <b>Diqqat!</b> Barcha ma'lumotlaringiz (xarajatlar, hisobotlar, sozlamalar) <b>butunlay o'chiriladi</b> "
    "va qayta tiklab bo'lmaydi.\n\nDavom etasizmi?"
)
DELETE_DONE = "✅ Barcha ma'lumotlaringiz o'chirildi. Qayta boshlash uchun /start bosing."

TRIAL_D2 = "⏳ Bepul davr tugashiga <b>2 kun</b> qoldi. Uzluksiz foydalanish uchun «💳 Obuna» bo'limiga o'ting."
TRIAL_END = ("⌛️ <b>Bepul davr tugadi.</b> Ma'lumotlaringiz saqlanadi.\n"
             "Davom etish uchun «💳 Obuna» tugmasini bosing.")
PRO_D3 = "⏳ PRO obuna tugashiga <b>3 kun</b> qoldi. Uzaytirish uchun «💳 Obuna» tugmasini bosing."
PRO_END = "⌛️ PRO obuna muddati tugadi. Ma'lumotlaringiz saqlanadi. Uzaytirish: «💳 Obuna»."
