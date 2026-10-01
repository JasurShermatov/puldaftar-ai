"""Kategoriya kalit so'zlari (o'zbek lotin/kirill-translit, rus, sleng).

Qoida: bitta so'zli kalitlar token *boshlanishi* bo'yicha solishtiriladi ("taksiga", "obedga"),
ko'p so'zlilar esa normalizatsiya qilingan matn ichidan qidiriladi.
"""
from __future__ import annotations

EXPENSE_KEYWORDS: dict[str, list[str]] = {
    "food": ["lunch", "dinner", "breakfast", "cafe", "restaurant", "meal", "food", "snack", "ovqat", "obed", "abed", "tushlik", "nonushta", "zavtrak", "uzhin", "ujin", "kechki ovqat",
             "kafe", "kafe", "restoran", "choyxona", "osh", "palov", "lavash", "shaurma", "burger", "pitsa",
             "pizza", "evos", "kfc", "oqtepa", "somsa", "kofe", "coffee", "fastfud", "fast food", "yegulik",
             "yedik", "tamaddi", "shashlik", "manti", "chuchvara", "hot-dog", "hotdog", "donar", "doner",
             "stolovoy", "stolovaya", "eda", "perekus", "bellissimo", "maxway", "feed up", "yaponamama"],
    "groceries": ["groceries", "grocery", "bozor", "market", "supermarket", "korzinka", "makro", "havas", "oziq", "go'sht", "gosht",
                  "sabzavot", "meva", "sut", "produkt", "magazin", "do'kon", "dokon", "un ", "yog'", "shakar",
                  "tuxum", "kartoshka", "piyoz", "guruch", "non ", "nonga", "non,", "bazar"],
    "taxi": ["uber", "cab", "taksi", "taxi", "yandex go", "yandeks", "mytaxi", "uklon", "indrive"],
    "transport": ["bus", "ticket", "train", "flight", "avtobus", "metro", "marshrut", "yo'l kira", "yol kira", "proezd", "poyezd", "poezd",
                  "avia", "bilet", "samolyot", "samolet", "transport", "parkovka", "stoyanka", "damas"],
    "fuel": ["petrol", "fuel", "gasoline", "benzin", "zapravka", "yoqilg'i", "yoqilgi", "metan", "propan", "dizel", "solyarka", "ai-92", "toplivo"],
    "utilities": ["electricity", "utilities", "water bill", "kommunal", "svet", "elektr", "gaz", "suv puli", "suvga", "issiq suv", "kvartplata",
                  "musor", "chiqindi", "otoplenie", "isitish"],
    "rent": ["rent", "ijara", "arenda", "kvartira puli", "kvartiraga", "ijaraga"],
    "home": ["remont", "ta'mir", "tamir", "mebel", "uy jihoz", "santexnik", "elektrik", "posuda", "idish"],
    "internet": ["phone", "mobile", "internet", "aloqa", "telefon", "balans", "paynet", "uzmobile", "beeline", "ucell", "mobiuz",
                 "humans", "wifi", "tarif", "svyaz"],
    "health": ["pharmacy", "medicine", "doctor", "hospital", "dori", "apteka", "dorixona", "shifokor", "vrach", "klinika", "analiz", "stomatolog", "tish ",
               "shifoxona", "bolnitsa", "lekarstv", "massaj", "ukol", "uzi"],
    "education": ["course", "book", "tuition", "school", "kurs", "o'qish", "oqish", "kontrakt", "kitob", "repetitor", "maktab", "universitet",
                  "ta'lim", "talim", "trening", "seminar", "bog'cha", "bogcha", "detsad", "ucheba"],
    "entertainment": ["cinema", "movie", "games", "kino", "o'yin", "oyin", "kinoteatr", "park", "dam olish", "netflix", "spotify",
                      "playstation", "boulin", "bouling", "karaoke", "konsert", "sayohat", "otdix", "otdyx", "futbol"],
    "clothes": ["clothes", "shoes", "jacket", "kiyim", "oyoq kiyim", "krossovka", "ko'ylak", "koylak", "shim", "kurtka", "odejda", "obuv",
                "tufli", "futbolka", "palto", "etik", "sumka"],
    "gifts": ["gift", "present", "birthday", "sovg'a", "sovga", "to'y", "toy", "tug'ilgan kun", "tugilgan kun", "gul", "podarok", "tabrik",
              "den rojdeniya", "svadba"],
    "charity": ["sadaqa", "xayriya", "ehson", "zakot", "fitr", "masjid", "blagotvor"],
    "advertising": ["ads", "advertising", "reklama", "target", "smm", "reklam", "piar", "promo"],
    "delivery": ["delivery", "courier", "dostavka", "yetkazib", "kuryer", "kurer", "express24", "uzum tezkor", "wolt", "pochta"],
    "business": ["biznes", "ofis", "tovar", "zakup", "xom ashyo", "ishchi", "oylik berdim", "maosh berdim",
                 "zarplata berdim", "hodim", "xodim", "sklad", "ombor"],
    "construction": ["qurilish", "sement", "g'isht", "gisht", "armatura", "beton", "qum", "shebyon",
                     "kafel", "kraska", "bo'yoq", "stroy", "usta"],
    "taxes": ["soliq", "jarima", "shtraf", "nalog", "bojxona", "poshlina", "yo'l politsiya", "gai"],
    "loss": ["yo'qotib", "yoqotib", "yo'qotdim", "yoqotdim", "yo'qoldi", "yoqoldi", "tushirib qoldirdim", "tushurib qoldirdim",
             "o'g'irlatdim", "ogirlatdim", "o'g'irlab", "ogirlab", "o'g'irlashdi", "ogirlashdi", "aldanib", "aldab ketishdi",
             "poteryal", "poteryala", "ukrali", "sperli", "lost", "stolen", "zarar", "ubitok", "kuyib qoldim", "kuydim",
             "yutqazdim", "yutqizdim", "proigral"],
}

INCOME_KEYWORDS: dict[str, list[str]] = {
    "salary": ["salary", "paycheck", "maosh", "oylik", "zarplata", "zp ", "ish haqi", "avans"],
    "sales": ["revenue", "sold", "savdo", "tushum", "sotdim", "sotuv", "vyruchka", "viruchka", "prodaja", "kassa"],
    "services": ["xizmat", "zakaz", "buyurtma", "freelance", "frilans", "loyiha puli"],
    "bonus": ["bonus", "premiya", "mukofot"],
    "refund": ["qaytardi", "qaytarildi", "qaytib keldi", "vozvrat", "keshbek", "cashback"],
    "rent_income": ["ijara daromad", "ijarachi", "ijaradan"],
    "found": ["topib oldim", "topdim", "topib", "topvoldim", "nashel", "nashla", "found", "yutib oldim", "yutdim",
              "yutuq", "viigral", "vyigral", "sovg'a qilishdi", "sovga qilishdi", "hadya qilishdi", "podarili"],
    "other_income": ["income", "daromad", "doxod", "daxod", "dohod", "prixod", "foyda"],
}

# Daromad signal so'zlari (fe'llar) — kategoriya aniq bo'lmasa ham tur = income
INCOME_VERBS = ["received", "got paid", "earned", "income", "found", "won", "keldi", "tushdi", "oldim pul", "ishladim", "topdim",
                "topib oldim", "topvoldim", "yutib oldim", "yutdim", "berishdi", "sovg'a qilishdi", "daromad", "doxod", "daxod",
                "dohod", "prixod", "poluchil", "zarabotal", "nashel", "nashla", "vyigral", "viigral", "podarili", "prishlo",
                "prishli", "kelib tushdi", "tushib"]
# Xarajat signal so'zlari
EXPENSE_VERBS = ["spent", "paid", "bought", "lost", "ketdi", "sarfladim", "sarf", "to'ladim", "toladim", "berdim", "oldim", "xarajat",
                 "rasxod", "yo'qotdim", "yoqotdim", "yo'qotib", "yoqotib", "potratil", "zaplatil", "kupil", "poteryal", "ushlo",
                 "sotib oldim", "yedim", "ichdim", "to'lov", "tolov"]

# Tavsifdan olib tashlanadigan so'zlar
STOPWORDS = {
    "bugun", "kecha", "ertalab", "tushda", "kechqurun", "kechasi", "segodnya", "vchera", "utrom", "vecherom",
    "uchun", "ga", "ni", "da", "dan", "va", "ham", "keyin", "yana", "so'm", "som", "sum", "sumga", "uzs",
    "ketdi", "sarfladim", "to'ladim", "toladim", "berdim", "oldim", "bo'ldi", "boldi", "qildim", "rasxod",
    "xarajat", "na", "za", "i", "potratil", "zaplatil", "ushlo", "pul", "puli", "pulga", "summa",
    "ming", "million", "mln", "yarim", "k", "ta", "soat", "edi", "qilindi", "sarf", "kartadan", "naqd",
    "karta", "kartaga", "nalichka", "keldi", "tushdi", "o'tgan", "otgan", "kuni", "men", "biz", "u",
    "for", "on", "the", "a", "spent", "paid", "today", "yesterday", "and", "thousand", "i", "my",
}

CARD_WORDS = ["card", "kartadan", "karta", "plastik", "humo", "uzcard", "click", "payme", "kartoy", "kartochk", "perevod"]
CASH_WORDS = ["cash", "naqd", "nalichka", "nalichn", "naqdga", "kesh", "cash"]

YESTERDAY = {"kecha", "vchera", "kechagi", "yesterday"}
DAY_BEFORE = {"o'tgan kuni", "otgan kuni", "pozavchera", "avvalgi kuni", "oldingi kuni"}
TODAY = {"bugun", "segodnya", "hozir", "today"}
TOMORROW = {"ertaga", "zavtra"}

# ---------------- Qarz ----------------
# "qarz berdim" → men berdim (given), "qarz oldim" → men oldim (taken)
DEBT_WORDS = ["qarz", "qarzga", "qarzini", "qarzimni", "qarzni", "nasiya", "nasiyaga", "dolg", "v dolg", "zaym", "zayom",
              "zanyal", "odolzhil", "odoljil", "zanyala", "odolzhila", "loan", "lent", "borrowed", "lend", "borrow", "owe"]
DEBT_GIVEN_VERBS = ["berdim", "berib turdim", "berdik", "berib yubordim", "dal", "dala", "odolzhil", "odoljil", "odolzhila",
                    "lent", "lend", "gave"]
DEBT_TAKEN_VERBS = ["oldim", "olib turdim", "oldik", "olib keldim", "vzyal", "vzyala", "zanyal", "zanyala", "borrowed",
                    "borrow", "took", "nasiyaga oldim"]
# qaytarish: "qarzini qaytardi" (menga), "qarzimni qaytardim" (men)
REPAY_TO_ME = ["qarzini qaytardi", "qarzni qaytardi", "qaytarib berdi", "qarzini berdi", "qarzini to'ladi", "qarzini toladi",
               "qarzini yopdi", "qarzini uzdi", "vernul mne", "vernula mne", "otdal mne", "otdala mne", "vernul dolg",
               "vernula dolg", "paid me back", "returned my money", "returned the debt"]
REPAY_BY_ME = ["qarzimni qaytardim", "qarzni qaytardim", "qaytarib berdim", "qarzimni berdim", "qarzimni to'ladim",
               "qarzimni toladim", "qarzni to'ladim", "qarzni toladim", "qarzni yopdim", "qarzimni yopdim", "qarzimni uzdim",
               "ya vernul", "ya otdal", "vernul emu", "vernul ey", "otdal emu", "otdal ey", "vernul dolg emu",
               "paid back my debt", "repaid", "i paid back"]

# Muddat: "2 kunga", "1 haftaga", "oy oxirigacha", "ertagacha", "15-oktabrgacha"
DURATION_UNITS = {
    "kun": 1, "kunga": 1, "kunlik": 1, "kunda": 1, "den": 1, "dnya": 1, "dney": 1, "day": 1, "days": 1,
    "hafta": 7, "haftaga": 7, "haftalik": 7, "haftada": 7, "nedelya": 7, "nedelyu": 7, "nedeli": 7, "nedel": 7,
    "week": 7, "weeks": 7,
    "oy": 30, "oyga": 30, "oylik": 30, "oyda": 30, "mesyats": 30, "mesyatsa": 30, "mesyatsev": 30, "month": 30, "months": 30,
}
UNTIL_WORDS = {"ertagacha": 1, "zavtra": 1, "do zavtra": 1, "tomorrow": 1, "indinga": 2, "indingacha": 2, "poslezavtra": 2}
WEEKDAY_WORDS = {
    "dushanba": 0, "seshanba": 1, "chorshanba": 2, "payshanba": 3, "juma": 4, "shanba": 5, "yakshanba": 6,
    "ponedelnik": 0, "vtornik": 1, "sreda": 2, "sredu": 2, "chetverg": 3, "pyatnitsa": 4, "pyatnitsu": 4, "subbota": 5,
    "subbotu": 5, "voskresenye": 6, "ponedelnika": 0, "vtornika": 1, "sredi": 2, "sredy": 2, "chetverga": 3,
    "pyatnitsi": 4, "pyatnitsy": 4, "subboti": 5, "subboty": 5, "voskresenya": 6, "monday": 0, "tuesday": 1, "wednesday": 2, "thursday": 3, "friday": 4,
    "saturday": 5, "sunday": 6,
}
# Ism bo'lishi mumkin bo'lmagan so'zlar (-ga/-dan qo'shimchali bo'lsa ham)
NOT_A_NAME = {
    "bugun", "kecha", "ertaga", "indin", "men", "sen", "u", "biz", "siz", "ular", "unga", "menga", "senga", "bizga",
    "sizga", "ularga", "undan", "mendan", "sendan", "bizdan", "sizdan", "ulardan", "kun", "hafta", "oy", "yil", "soat",
    "qarz", "qarzga", "nasiya", "nasiyaga", "pul", "pulga", "puldan", "karta", "kartaga", "kartadan", "naqd", "naqdga",
    "bank", "bankdan", "bankka", "ishga", "ishdan", "uyga", "uydan", "bozor", "bozorga", "bozordan", "do'kon", "dokon",
    "do'konga", "dokonga", "do'kondan", "dokondan", "muddat", "muddatga", "oldin", "keyin", "yana", "ham",
    "dolg", "dengi", "mne", "emu", "ey", "nam", "im", "tebe", "vam", "ot", "do", "na", "za", "to", "from", "for",
    "the", "a", "my", "me", "him", "her", "them", "friend", "bittasiga", "bittasidan", "birovga", "birovdan", "kimgadir",
    "kimdandir", "odamga", "odamdan", "hamma", "hammaga", "nimaga", "nimadan", "shunga", "shundan", "bunga", "bundan",
    "ishxonaga", "ishxonadan", "ofisga", "ofisdan", "kassaga", "kassadan", "hisobga", "hisobdan", "qaytarishga",
}
