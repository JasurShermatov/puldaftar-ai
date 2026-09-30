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
}

INCOME_KEYWORDS: dict[str, list[str]] = {
    "salary": ["salary", "paycheck", "maosh", "oylik", "zarplata", "zp ", "ish haqi", "avans"],
    "sales": ["revenue", "sold", "savdo", "tushum", "sotdim", "sotuv", "vyruchka", "viruchka", "prodaja", "kassa"],
    "services": ["xizmat", "zakaz", "buyurtma", "freelance", "frilans", "loyiha puli"],
    "bonus": ["bonus", "premiya", "mukofot"],
    "refund": ["qaytardi", "qaytarildi", "qaytib keldi", "vozvrat", "keshbek", "cashback"],
    "rent_income": ["ijara daromad", "ijarachi", "ijaradan"],
    "other_income": ["income", "daromad", "doxod", "daxod", "dohod", "prixod", "foyda"],
}

# Daromad signal so'zlari (fe'llar) — kategoriya aniq bo'lmasa ham tur = income
INCOME_VERBS = ["received", "got paid", "earned", "income", "keldi", "tushdi", "oldim pul", "ishladim", "topdim", "daromad", "doxod", "daxod", "dohod",
                "prixod", "poluchil", "zarabotal", "prishlo", "prishli", "kelib tushdi", "tushib"]
# Xarajat signal so'zlari
EXPENSE_VERBS = ["spent", "paid", "bought", "ketdi", "sarfladim", "sarf", "to'ladim", "toladim", "berdim", "oldim", "xarajat", "rasxod",
                 "potratil", "zaplatil", "kupil", "ushlo", "sotib oldim", "yedim", "ichdim", "to'lov", "tolov"]

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
