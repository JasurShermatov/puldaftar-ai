"""O'zbekcha/ruscha/aralash summalarni deterministik ajratish.

"35 ming" → 35 000, "1 yarim million" → 1 500 000, "ikki yarim mln" → 2 500 000,
"4 million 300 ming" → 4 300 000, "1.2 mln" → 1 200 000, "800k" → 800 000,
"bir million" → 1 000 000, "yuz ming" → 100 000, "35 000" → 35 000.
"""
from __future__ import annotations

from dataclasses import dataclass

UNITS: dict[str, int] = {
    # uz
    "bir": 1, "ikki": 2, "uch": 3, "to'rt": 4, "tort": 4, "to'rtta": 4, "besh": 5, "olti": 6,
    "yetti": 7, "sakkiz": 8, "to'qqiz": 9, "toqqiz": 9, "o'n": 10, "on": 10, "yigirma": 20,
    "o'ttiz": 30, "ottiz": 30, "qirq": 40, "ellik": 50, "oltmish": 60, "yetmish": 70,
    "sakson": 80, "to'qson": 90, "toqson": 90,
    # ru (translit)
    "odin": 1, "odna": 1, "dva": 2, "dve": 2, "tri": 3, "chetire": 4, "pyat": 5, "shest": 6,
    "sem": 7, "vosem": 8, "devyat": 9, "desyat": 10, "dvadtsat": 20, "tridtsat": 30, "sorok": 40,
    "pyatdesyat": 50, "shestdesyat": 60, "semdesyat": 70, "vosemdesyat": 80, "devyanosto": 90,
    "dvesti": 200, "trista": 300, "chetiresta": 400, "pyatsot": 500, "shestsot": 600,
    "semsot": 700, "vosemsot": 800, "devyatsot": 900,
    # en
    "one": 1, "two": 2, "three": 3, "four": 4, "five": 5, "six": 6, "seven": 7, "eight": 8, "nine": 9,
    "ten": 10, "eleven": 11, "twelve": 12, "fifteen": 15, "twenty": 20, "thirty": 30, "forty": 40,
    "fifty": 50, "sixty": 60, "seventy": 70, "eighty": 80, "ninety": 90,
}
HUNDRED = {"yuz", "sto", "hundred"}
THOUSAND = {"ming", "k", "tisyach", "tisyachi", "tisyacha", "tis", "tish", "tishi", "kusok", "kuska", "thousand", "thousands", "th"}
MILLION = {"million", "millon", "mln", "mil", "milyon", "limon", "mlion", "milliona", "millionov", "millions", "m"}
BILLION = {"milliard", "mlrd", "milyard"}
HALF = {"yarim", "polovina", "pol", "half"}
MULTIPLIERS = {**{w: 1_000 for w in THOUSAND}, **{w: 1_000_000 for w in MILLION}, **{w: 1_000_000_000 for w in BILLION}}
CURRENCY = {"so'm", "som", "sum", "sumdan", "so'mlik", "somlik", "uzs", "sw", "sm", "soums", "soum"}
# Summadan keyin kelsa — bu miqdor (dona/kg), pul emas
COUNTERS = {"ta", "dona", "kg", "kilo", "gramm", "gr", "litr", "l", "kishi", "marta", "kun", "kunlik", "kunga", "kunda",
            "oy", "oyga", "oylik", "oyda", "hafta", "haftaga", "haftalik", "haftada", "yil", "yilga", "soat", "minut",
            "daqiqa", "shtuk", "sht", "metr", "m2", "qop", "pachka", "blok", "foiz", "%",
            "den", "dnya", "dney", "nedelya", "nedelyu", "nedeli", "nedel", "mesyats", "mesyatsa", "mesyatsev",
            "day", "days", "week", "weeks", "month", "months"}
MONTHS = {
    "yanvar": 1, "fevral": 2, "mart": 3, "aprel": 4, "may": 5, "iyun": 6, "iyul": 7, "avgust": 8,
    "sentabr": 9, "sentyabr": 9, "oktabr": 10, "oktyabr": 10, "noyabr": 11, "dekabr": 12,
    "yanvarya": 1, "fevralya": 2, "marta": 3, "aprelya": 4, "maya": 5, "iyunya": 6, "iyulya": 7,
    "avgusta": 8, "sentyabrya": 9, "oktyabrya": 10, "noyabrya": 11, "dekabrya": 12,
}


def _is_digit(tok: str) -> bool:
    return tok[0].isdigit()


def _num(tok: str) -> float:
    return float(tok.replace(",", "."))


def is_number_token(tok: str) -> bool:
    return (
        _is_digit(tok) or tok in UNITS or tok in HUNDRED or tok in MULTIPLIERS or tok in HALF
    )


@dataclass(slots=True)
class AmountSpan:
    start: int          # token index (inclusive)
    end: int            # token index (exclusive)
    value: int
    has_multiplier: bool
    from_words_only: bool

    @property
    def is_bare_small(self) -> bool:
        """'Reklama 800' — birlik aytilmagan va < 1000: noaniq."""
        return not self.has_multiplier and self.value < 1000


def _span_value(tokens: list[str]) -> tuple[float, bool]:
    total = 0.0
    current = 0.0
    last_mult = 0
    has_mult = False
    for i, tok in enumerate(tokens):
        nxt = tokens[i + 1] if i + 1 < len(tokens) else ""
        if _is_digit(tok):
            current += _num(tok)
        elif tok in UNITS:
            current += UNITS[tok]
        elif tok in HUNDRED:
            current = (current or 1) * 100
        elif tok in HALF:
            if nxt in MULTIPLIERS:
                current += 0.5 if current else 0.5
            elif last_mult:
                total += last_mult * 0.5
        elif tok in MULTIPLIERS:
            m = MULTIPLIERS[tok]
            total += (current or 1) * m
            current = 0
            last_mult = m
            has_mult = True
    return total + current, has_mult


def find_amounts(tokens: list[str]) -> list[AmountSpan]:
    spans: list[AmountSpan] = []
    i, n = 0, len(tokens)
    while i < n:
        tok = tokens[i]
        if not is_number_token(tok) or (tok in MULTIPLIERS and tok in {"m", "k"} and i > 0 and not is_number_token(tokens[i - 1])):
            i += 1
            continue
        # vaqt: "13:30" / "soat 13"
        if _is_digit(tok) and i + 1 < n and tokens[i + 1] == ":":
            i += 3
            continue
        if _is_digit(tok) and i > 0 and tokens[i - 1] == "soat":
            i += 1
            continue
        j = i
        while j < n and is_number_token(tokens[j]):
            # "1 million 200 ming" — ichida faqat raqam/so'z; ikkita yalang'och raqam ketma-ket bo'lsa ajratamiz
            if j > i and _is_digit(tokens[j]) and _is_digit(tokens[j - 1]):
                break
            if j > i and _is_digit(tokens[j]) and tokens[j - 1] not in MULTIPLIERS and tokens[j - 1] not in HALF:
                break
            # "200 thousand on groceries": ko'paytiruvchidan keyingi yolg'iz so'z-son (on/bir) — summa emas
            if (j > i and tokens[j] in UNITS and tokens[j - 1] in MULTIPLIERS
                    and (j + 1 >= n or not is_number_token(tokens[j + 1]))):
                break
            j += 1
        span_tokens = tokens[i:j]
        # "yarim" yoki faqat ko'paytiruvchi so'zning o'zi summa emas
        if all(t in HALF for t in span_tokens) or (len(span_tokens) == 1 and span_tokens[0] in MULTIPLIERS):
            i = j
            continue
        nxt = tokens[j] if j < n else ""
        # sana: "15 sentabr"
        if nxt in MONTHS and len(span_tokens) == 1 and _is_digit(span_tokens[0]):
            i = j + 1
            continue
        # miqdor: "2 ta", "3 kg"
        if nxt in COUNTERS:
            i = j + 1
            continue
        value, has_mult = _span_value(span_tokens)
        words_only = not any(_is_digit(t) for t in span_tokens)
        # "bir kofe" — maqola sifatidagi "bir": ko'paytiruvchisiz so'z-sonni e'tiborsiz qoldiramiz
        if words_only and not has_mult and not any(t in HUNDRED for t in span_tokens):
            i = j
            continue
        if value > 0:
            spans.append(AmountSpan(i, j, int(round(value)), has_mult, words_only))
        i = j
    return spans
