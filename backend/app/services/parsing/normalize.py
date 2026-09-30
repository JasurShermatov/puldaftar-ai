"""Matnni normalizatsiya qilish: apostroflar, kirill→lotin (asosiy so'zlar uchun), tokenlash."""
from __future__ import annotations

import re

_APOS = str.maketrans({"ʻ": "'", "’": "'", "‘": "'", "`": "'", "ʼ": "'", "´": "'"})

_CYR = {
    "а": "a", "б": "b", "в": "v", "г": "g", "д": "d", "е": "e", "ё": "yo", "ж": "j", "з": "z",
    "и": "i", "й": "y", "к": "k", "л": "l", "м": "m", "н": "n", "о": "o", "п": "p", "р": "r",
    "с": "s", "т": "t", "у": "u", "ф": "f", "х": "x", "ц": "ts", "ч": "ch", "ш": "sh", "щ": "sh",
    "ъ": "", "ы": "i", "ь": "", "э": "e", "ю": "yu", "я": "ya", "ў": "o'", "қ": "q", "ғ": "g'", "ҳ": "h",
}

_TOKEN_RE = re.compile(r"\d+(?:[.,]\d+)?|[a-z']+|[:\-/]")
# "35 000" → "35000" (faqat 3 xonali guruhlar)
_THOUSANDS_RE = re.compile(r"(?<![\d.,])(\d{1,3})((?:[  ]\d{3})+)(?![\d])")
# "800k", "1.2mln", "35ming" → raqam va birlikni ajratish
_GLUED_RE = re.compile(r"(\d)([a-z])")


def translit(text: str) -> str:
    return "".join(_CYR.get(ch, ch) for ch in text)


def normalize(text: str) -> str:
    t = text.lower().translate(_APOS)
    t = translit(t)
    t = _THOUSANDS_RE.sub(lambda m: m.group(1) + m.group(2).replace(" ", "").replace(" ", ""), t)
    t = _GLUED_RE.sub(r"\1 \2", t)
    t = re.sub(r"(\d)-(?=[a-z])", r"\1 ", t)  # "15-sentabr" → "15 sentabr"
    return t


def tokenize(text: str) -> list[str]:
    return _TOKEN_RE.findall(text)
