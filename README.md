# Hisobchi AI — Telegram bot + Mini App

Kunlik xarajat/daromadni **ovoz yoki matn** orqali yozib boradigan Telegram bot, grafikli **Mini App dashboard**,
AI tahlil, Excel/CSV eksport, 7 kunlik bepul sinov + qo'lda tasdiqlanadigan to'lov va superadmin panel.

---

## 1. Imkoniyatlar

**Bot**
- Matn yoki ovoz: «Bugun taksiga 35 ming, obedga 80 ming ketdi» → 2 ta yozuv, kategoriya, vaqt.
- O'zbek (lotin/kirill), rus va aralash nutq: `35 ming`, `1 yarim million`, `ikki yarim mln`, `4 million 300 ming`, `1.2 mln`, `800k`.
- Noaniq bo'lsa taxmin qilmaydi: «Reklama 800» → *800 ming so'mmi?* tugmalari; «Akmalga 2 mln berdim» → tasdiq so'raydi.
- Har yozuv ostida ✏️ Summa / 🏷 Kategoriya / 🗑 O'chirish (+ ↩️ Qaytarish). Kategoriya tuzatilsa — bot o'rganadi.
- **Har kuni 23:59** (sozlanadi) chiroyli hisobot: har bir yozuv nomi, vaqti, summasi va oxirida
  `📅 30.09.2026 soat 23:59 · 💸 Umumiy xarajat: 5 000 000 so'm`.
- Har kuni qisqa AI tahlil, yakshanba — haftalik chuqur tahlil («ovqatga haftasiga o'rtacha 612 ming ketyapti…»).
- **Ma'noni tushunadi:** «100 ming topib oldim / yutib oldim» → daromad (🍀 Topilgan pul); «50 ming yo'qotib qo'ydim / o'g'irlatdim» → xarajat (🕳 Yo'qotish).
- **Qarzlar:** «Jasurga 100 ming qarz berdim 2 kunga», «Akmaldan 500 ming qarz oldim bir haftaga», «Дал в долг Азизу 200 тысяч на неделю»,
  «Jasur qarzini qaytardi» — kim, qancha, qachongacha avtomatik ajratiladi. Muddatgacha 3 kun qolganda va muddati o'tganda
  har kuni ertalab (09:00) eslatma: *«Jasurga 100 ming qarz bergan edingiz, 2 kun qoldi — so'rab ko'ring»* / *«Akmaldan 500 ming qarz olgansiz, unutmang»*.
  Eslatma ostida ✅ Qaytardi · ⏰ +3 kun tugmalari. `/debts` yoki 🤝 Qarzlar tugmasi — ro'yxat.
- **Ishonchlilik:** ≥ 85% — avtomatik saqlanadi; pastroq bo'lsa (summa bo'lsa ham) — «✅ Tasdiqlash / ❌ Bekor» (va kerak bo'lsa «🤝 Bu qarz edi»)
  tugmalari bilan ko'rsatiladi; summa topilmasa — savol. Ovoz uchun: STT (gpt-4o-transcribe, whisper-1 zaxira) + tipik xatolarni tuzatish
  + LLM parser ovoz kontekstini biladi.
- **AI suhbat:** `/ai nimaga ko'p xarajat qilyapman?` yoki 🧠 AI tahlil → «💬 Savol berish» — faqat shu userning o'z ma'lumotlari
  (xarajat/daromad/kategoriya/qarzlar, SQL bilan hisoblangan) asosida javob; suhbat tarixi shifrlangan holda saqlanadi, ma'lumot ko'paygan sari aniqroq.
- Tugmalar: 📊 Dashboard · 📅 Bugun · 📈 Hisobotlar · 🧠 AI tahlil · 🤝 Qarzlar · 📥 Yuklab olish · 💳 Obuna · ⚙️ Sozlamalar · ❓ Yordam.

**Mini App (Dashboard)**
- Bugungi xarajat **va daromad**, hafta/oy/yil KPI (xarajat + daromad), oylik sof natija (+/−) chizig'i.
- Ketma-ket 4 ta line grafik: **kunlik (30 kun) → haftalik (12 hafta) → oylik (12 oy) → yillik** — xarajat (qizil) va daromad (yashil)
  alohida chiziqlar, «Ikkalasi / Xarajat / Daromad» tanlovi, barmoq bilan surib ikkala qiymatni ko'rish.
- «Nimaga ketyapti» / «Nimadan kelyapti» — kategoriyalar ulushi (kun/hafta/oy/yil), tarix (sana bo'yicha varaqlash, filtr, tahrirlash).
- 🤝 **Qarzlar** sahifasi: sizga qaytarishadi / siz qaytarasiz, muddat belgilari (yashil/sariq/qizil), qisman qaytarish, muddatni o'zgartirish, yopilganlar.
- 💬 **AI** sahifasi: suhbat (tayyor savollar bilan) + statistik tahlil. Excel (.xlsx — grafiklar va qarzlar varag'i bilan) / CSV.
- Sozlamalar: hisobot vaqti, vaqt zonasi, ma'lumotlarni butunlay o'chirish.

**Superadmin panel** (`/admin` — faqat `SUPERADMIN_IDS`)
- Statistika (userlar, DAU/WAU, PRO/sinov/tugagan, tushum, hisobotlar, tizim holati).
- Userlar: qidirish, **bloklash / blokdan chiqarish**, PRO berish/bekor qilish, sinovni uzaytirish, o'chirish.
- To'lovlar: kutilayotgan arizalarni **Tasdiqlash / Rad etish** (PRO avtomatik yoqiladi, userga xabar boradi).
- Sozlamalar: 3 ta tarif (narx, chegirma, muddat), sinov kunlari, karta raqami, karta egasi, chek qabul qiluvchi admin, AI chegaralari.
- Ommaviy xabar (segment bo'yicha), audit jurnali (kim, qachon, nima qildi).

**Tariflar:** 1 oylik · 3 oylik · 1 yillik. Narx, muddat, «eski narx» (chegirma — ustidan chizilib ko'rinadi),
belgi («🔥 -20%»), yoqish/o'chirish, **yangi tarif qo'shish va o'chirish** (to'lov tarixida bor tarif arxivlanadi) —
admin panel → Sozlamalar → Tariflar. Karta raqami, karta egasi va chek qabul qiluvchi admin — shu sahifada, o'zgarish botda darhol ko'rinadi.

**To'lov jarayoni (botda)**
1. User 💳 **Obuna** → 3 ta tarif tugmasi → tarifni tanlaydi → karta raqami va aniq summa chiqadi.
2. Kartaga pul o'tkazadi → **✅ To'lov qildim** → ariza yaratiladi (boshqa tarifni tanlasa ariza yangilanadi).
3. **📨 Chekni adminga yuborish** tugmasi adminning Telegram akkauntini ochadi (chekni botga ham yuborsa — adminga forward bo'ladi).
4. Adminga botda ariza keladi `[✅ Tasdiqlash] [❌ Rad etish]` (yoki admin paneldan).
5. Tasdiqlansa — tanlangan tarif muddatiga PRO (aktiv PRO bo'lsa ustiga qo'shiladi), userga xabar. Ikki marta bosilsa ham bitta PRO.
7. Admin to'lovsiz ham ochib bera oladi: admin panel → Userlar → user → **1 oylik / 3 oylik / 1 yillik** tugmasi
   (yoki botda `/pro <telegram_id> m1|m3|y1`).

**Ommaviy xabar (reklama, chegirma e'lonlari)**
- Admin panel → **📣 Xabar**: segment (hammaga / sinovda / tugagan / PRO / faol / nofaol), tayyor shablonlar
  («1 oylik chegirma», «1 yillik chegirma» — joriy narxlar avtomatik qo'yiladi), rasm, havola-tugma, «O'zimga test».
- Botda: `/broadcast` → istalgan postni yuboring (rasm, video, matn — formatlash bilan) → segment tanlang → aynan shu post hammaga nusxalanadi.
- Fonda ~20 ta/sek yuboriladi, bloklanganlarga yuborilmaydi, tugagach adminga hisobot keladi, tarix saqlanadi.
6. Sinov tugashiga 2 kun / PRO tugashiga 3 kun qolganda eslatma.

---

## 2. Arxitektura

```
Telegram ──webhook──► nginx+certbot (HTTPS) ──► nginx (web) ──► FastAPI (api) ──► PostgreSQL (RLS)
                                          │  statik Mini App        │  aiogram bot    ▲
                                          └─────────────────────────┘  OpenAI         │
                                                         worker (23:59 hisobot, eslatmalar)─┘
                                                         Redis (rate limit, FSM)
```

| Qatlam | Texnologiya | Nega |
|---|---|---|
| Backend API + bot | **FastAPI + aiogram 3** (async, uvloop) | Bitta async jarayon, webhook tezda 200 qaytaradi, og'ir ish fonda |
| DB | **PostgreSQL 16** + asyncpg (ORM'siz, toza SQL) | Eng tez Python drayveri, SQL agregatlar |
| Mini App | **Next.js 15** statik eksport + nginx | Server render yo'q → bir zumda yuklanadi; grafiklar kutubxonasiz SVG |
| Fon | `worker` konteyneri | Hisobot/eslatma API'ni sekinlashtirmaydi |
| AI | OpenAI (parser: `gpt-4o-mini`, ovoz: `gpt-4o-transcribe`) | `.env` da model almashtiriladi |

```
backend/app/
  core/          config (.env), security (shifrlash, initData), logging, vaqt
  db/            asyncpg pool + user/system kontekst, migrate.py, migrations/*.sql
  domain/        pydantic modellari
  repositories/  faqat SQL (users, transactions, categories, payments, system)
  services/      biznes-logika: parsing/, ai/, transactions, reports, insights, export, billing, admin
  api/           FastAPI routes (user, admin, webhook/health), deps (auth)
  bot/           aiogram: handlers/, keyboards, middlewares, texts/uz.py
  worker/        scheduler (23:59 hisobot, AI tahlil, eslatmalar, tozalash)
frontend/        Next.js mini app (components/, lib/, app/)
```

Qoidalar: handler → service → repository. Handler ichida SQL yo'q; service Telegram'ni bilmaydi (`notifier` orqali).

---

## 3. Ma'lumotlar xavfsizligi va userlar izolyatsiyasi

Bir userning ma'lumoti boshqasiga **hech qanday yo'l bilan** o'tmasligi uchun 5 qavatli himoya:

1. **Identifikatsiya faqat Telegram imzosi orqali.** Mini App har so'rovda `initData` yuboradi, server uni
   bot token bilan **HMAC-SHA256** orqali tekshiradi (24 soatdan eski — rad). `user_id` hech qachon clientdan
   parametr sifatida olinmaydi, shuning uchun URL/ID almashtirib boshqa userni ko'rib bo'lmaydi. Botda esa ID Telegram serveridan keladi.
2. **Har bir SQL so'rov `user_id` bilan cheklangan** (repository qatlamida).
3. **PostgreSQL Row-Level Security (RLS)** — ikkinchi, mustaqil qatlam. Har so'rov tranzaksiyasida
   `SET LOCAL app.user_id = …` o'rnatiladi va barcha user jadvallarida `FORCE ROW LEVEL SECURITY` siyosati bor.
   Kodda xato bo'lib `WHERE user_id` unutilsa ham baza boshqa userning qatorini **qaytarmaydi va yozdirmaydi**.
   Ilova `hisobchi_app` roli bilan ulanadi — u jadval egasi ham, superuser ham emas (`NOBYPASSRLS`).
   `SET LOCAL` faqat joriy tranzaksiyaga ta'sir qiladi — pool'dagi ulanishda kontekst "oqib" qolmaydi.
4. **Shifrlash.** Tranzaksiya izohlari, AI tahlillar, tasdiq kutayotgan ma'lumotlar **AES-256-GCM** bilan
   shifrlanadi; shifr aynan shu userga bog'langan (AAD = user_id) — boshqa user qatoriga ko'chirilsa ochilmaydi.
   Kategoriya o'rganish so'zlari faqat HMAC hash ko'rinishida. Ovozli xabar diskka yozilmaydi (faqat xotirada), saqlanmaydi.
5. **Admin ham maxfiylikka bo'ysunadi:** admin panelda userning alohida yozuvlari/izohlari ko'rinmaydi — faqat umumiy summalar.
   Admin amallari o'zgartirib bo'lmaydigan `audit_logs` jadvaliga yoziladi (app rolida UPDATE/DELETE huquqi yo'q).

Qo'shimcha: webhook secret token, rate limit (user + IP), Telegram update idempotency (bir xil xabar ikki marta
yozilmaydi), CSV/Excel formula-injection himoyasi, loglarda token/karta raqami maskalanadi, LLM'ga user matni
`<data>` sifatida beriladi (prompt injection himoyasi) va LLM javobi schema + deterministik summa tekshiruvidan o'tadi,
DB port tashqariga ochilmagan, `/delete_me` — barcha ma'lumotlar butunlay o'chiriladi.

Tekshirish: `tests/test_isolation.py` ikki user yaratib, bir-birini ko'rolmasligini, begona nomidan yozolmasligini tasdiqlaydi.

---

## 4. O'rnatish — bitta buyruq, domen shart emas

Telegram Mini App faqat **HTTPS** manzilda ochiladi. Domen sotib olmasdan ikki yo'l bor:

### A) VPS (doimiy ishlash uchun) — server IP si bilan
Talab: Ubuntu/Debian server, ochiq IP, 80 va 443 portlar ochiq.
```bash
# loyiha papkasini serverga ko'chiring (scp/rsync/git), keyin:
cd hisobchi-ai
sudo ./scripts/setup.sh
```
Skript o'zi: Docker o'rnatadi → barcha maxfiy kalitlarni generatsiya qiladi → server IP sini aniqlab
`https://<IP-chiziqcha>.sslip.io` manzilini beradi (bepul xizmat, IP ni HTTPS manzilga aylantiradi; sertifikatni
certbot oladi, `scripts/ssl.sh`) → `BOT_TOKEN`/`OPENAI_API_KEY` bo'lmasa so'raydi → hammasini ishga tushiradi.
Bot `polling` rejimida ishlaydi — webhook/domen kerak emas.

### B) O'z kompyuteringizda sinash (Mac/PC, ochiq IP kerak emas)
Docker Desktop o'rnatilgan bo'lsin:
```bash
./scripts/setup.sh --tunnel
```
Bepul Cloudflare tunnel `https://<random>.trycloudflare.com` manzil beradi. Kompyuter o'chsa bot ham to'xtaydi,
qayta ishga tushirganda manzil o'zgaradi (skriptni qayta ishga tushirsangiz bot menyusi avtomatik yangilanadi).

### Superadminlar
Faqat `.env` dagi `SUPERADMIN_IDS` (Telegram ID lar, vergul bilan) — nechta ID yozilsa, shuncha superadmin.
ID ni olib tashlasangiz, u keyingi kirishda oddiy userga aylanadi. O'zgartirgach: `docker compose up -d`.
Keyin `/admin` → Sozlamalar: **karta raqami, karta egasi, chek qabul qiluvchi @username, tariflar**.

Keyinroq domen olsangiz: `.env` da `DOMAIN=sizning.domen` va `PUBLIC_BASE_URL=https://sizning.domen`, so'ng
`./scripts/ssl.sh` (certbot sertifikat oladi) va `docker compose up -d --force-recreate api worker`.
Sertifikat har 12 soatda avtomatik tekshiriladi va yangilanadi (certbot konteyneri).

Foydali buyruqlar: `docker compose logs -f api worker` · `docker compose down` · `./scripts/update.sh` (GitHub'dan yangilash).

**Barqarorlik va xavfsizlik (bir marta):** `sudo ./scripts/harden.sh` — UFW firewall (22/80/443), fail2ban, avtomatik
xavfsizlik yangilanishlari, Docker log rotatsiyasi, **watchdog** (har 2 daqiqada saytni tekshiradi, yiqilsa o'zi tiklaydi
va superadminga Telegram orqali xabar beradi) va kunlik DB zaxira croni. `update.sh` ham yangilashdan keyin saytni tekshirib,
kerak bo'lsa proxy'ni qayta yo'naltiradi.

---

## 5. Testlar

```bash
docker compose run --rm api pytest -q                                   # unit testlar
docker compose run --rm -e TEST_DB_OK=1 api pytest -q tests/test_isolation.py   # RLS izolyatsiya (DB bilan)
```
- `test_parser.py` — TZ acceptance holatlari AC-01…AC-06 va barcha summa formatlari.
- `test_security.py` — initData imzo (soxta/eskirgan/boshqa bot), shifrlash, user bog'lanishi.
- `test_export.py` — Excel/CSV, formula-injection himoyasi.
- `test_isolation.py` — userlar ma'lumoti aralashmasligi (RLS).

---

## 6. Zaxira (backup)

```bash
crontab -e
0 3 * * * /opt/hisobchi/scripts/backup.sh >> /var/log/hisobchi-backup.log 2>&1
./scripts/restore.sh backups/hisobchi_20260930_0300.sql.gz
```
⚠️ `DATA_ENCRYPTION_KEY` ni alohida xavfsiz joyda saqlang — usiz shifrlangan izohlarni tiklab bo'lmaydi.

---

## 7. Konfiguratsiya

Barcha kalitlar `.env.example` da izohlari bilan. Narx, sinov kunlari, karta, AI chegaralari —
**admin paneldan** (kodni o'zgartirmasdan). AI yo'q bo'lsa (kalit bo'sh): matn lokal parser bilan ishlaydi,
ovoz o'chadi, tahlil statistik (rule-based) bo'ladi.

## 8. Ma'lum cheklovlar / keyingi bosqich
- Faqat UZS. Bot matnlari o'zbekcha (ruscha — `bot/texts/` ga fayl qo'shish).
- To'lov qo'lda tasdiqlanadi (Click/Payme API — Phase 2, `services/billing.py` ga adapter).
- Phase 2: chek OCR, budjet limitlari, takroriy xarajatlar.
