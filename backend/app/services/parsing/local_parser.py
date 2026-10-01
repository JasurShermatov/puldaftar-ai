"""Deterministik (AI'siz) parser. AI o'chiq bo'lsa asosiy parser, AI yoqilgan bo'lsa —
summalarni tekshiruvchi "hakam" (LLM gallyutsinatsiyasiga qarshi).

Tushunadi: xarajat, daromad, topilgan/yo'qotilgan pul, qarz berdim/oldim (kimga, qachongacha),
qarz qaytarildi/qaytardim.
"""
from __future__ import annotations

import re
from datetime import date, datetime, time, timedelta

from app.core.timeutil import tz
from app.domain.models import ParsedDebt, ParsedItem, ParsedRepayment, ParseResult, TxType
from app.services.parsing import lexicon as L
from app.services.parsing.normalize import normalize, tokenize
from app.services.parsing.numbers import MONTHS, UNITS, AmountSpan, find_amounts

_CLAUSE_SPLIT = re.compile(r"[,;\n]+|\.(?!\d)|\s+va\s+|\s+ham\s+|\s+keyin\s+|\s+i\s+|\s+yana\s+|\s+and\s+")
_NAME_SUFFIXES_TO = ("larga", "imga", "ga", "ka", "qa")
_NAME_SUFFIXES_FROM = ("lardan", "imdan", "dan")
_DEBT_NOISE_PREFIXES = ("qarz", "nasiya", "ber", "ol", "turdim", "dal", "dolg", "zaym", "zayom", "zanyal", "odolzh", "odolj",
                        "vzyal", "lent", "lend", "borrow", "loan", "took", "gave", "muddat", "nedel", "mesyats", "dn")
_DEBT_NOISE = {"v", "na", "to", "from", "for", "u", "ot", "do", "until", "by", "bittasi", "birov", "kimdir"}


def _match_keywords(text: str, tokens: list[str], table: dict[str, list[str]]) -> str | None:
    padded = f" {text} "
    best: tuple[int, str] | None = None
    for key, words in table.items():
        for w in words:
            hit = False
            if w.endswith(" ") and w.strip().isalpha():   # qisqa so'z: aniq token (+ qo'shimcha)
                ws = w.strip()
                hit = any(t == ws or (t.startswith(ws) and len(t) <= len(ws) + 3) for t in tokens)
            elif " " in w.strip() or not w.strip().replace("'", "").isalpha():
                hit = f" {w.strip()}" in padded or w in padded
            else:
                hit = any(t.startswith(w) for t in tokens)
            if hit:
                score = len(w)
                if best is None or score > best[0]:
                    best = (score, key)
    return best[1] if best else None


def _contains(text: str, words) -> bool:
    padded = f" {text} "
    return any((f" {w}" in padded) for w in words)


def detect_date(text: str, tz_name: str, now: datetime | None = None) -> tuple[datetime, bool]:
    """Qaytaradi: (occurred_at, aniq_emasmi). Kelajak sanaga ruxsat yo'q."""
    z = tz(tz_name)
    now_local = (now or datetime.now(z)).astimezone(z)
    today = now_local.date()
    day: date = today
    uncertain = False
    if _contains(text, L.DAY_BEFORE):
        day = today - timedelta(days=2)
    elif _contains(text, L.YESTERDAY):
        day = today - timedelta(days=1)
    else:
        m = re.search(r"(\d{1,2})\s+([a-z']+)", text)
        if m and m.group(2) in MONTHS and not m.group(2).endswith("gacha"):
            d, mon = int(m.group(1)), MONTHS[m.group(2)]
            try:
                cand = date(today.year, mon, d)
                if cand > today:  # eng yaqin o'tgan yil
                    cand = date(today.year - 1, mon, d)
                day = cand
            except ValueError:
                uncertain = True
        m2 = re.search(r"\b(\d{1,2})[./](\d{1,2})(?:[./](\d{2,4}))?\b", text)
        if m2 and not m:
            try:
                y = int(m2.group(3)) if m2.group(3) else today.year
                y = y + 2000 if y < 100 else y
                cand = date(y, int(m2.group(2)), int(m2.group(1)))
                if cand <= today:
                    day = cand
            except ValueError:
                pass
    if day == today:
        return now_local, uncertain
    # o'tgan kun: vaqt noma'lum → 12:00 lokal
    return datetime.combine(day, time(12, 0), tzinfo=z), uncertain


# ---------------- Muddat (qarz uchun) ----------------

def detect_due(text: str, tokens: list[str], now_local: datetime) -> datetime | None:
    """«2 kunga», «bir haftaga», «ertagacha», «jumagacha», «15 oktabrgacha», «oy oxirigacha» → sana (12:00 lokal)."""
    z = now_local.tzinfo
    today = now_local.date()

    def at(d: date) -> datetime:
        return datetime.combine(d, time(12, 0), tzinfo=z)

    # 1) davomiylik: N + birlik
    for i, tok in enumerate(tokens):
        if tok in L.DURATION_UNITS:
            prev = tokens[i - 1] if i else ""
            n: int | None = None
            if prev and prev[0].isdigit():
                try:
                    n = int(float(prev.replace(",", ".")))
                except ValueError:
                    n = None
            elif prev in UNITS and UNITS[prev] < 100:
                n = UNITS[prev]
            elif tok.endswith(("ga", "lik", "yu", "u")):      # "haftaga" = 1 hafta, "nedelyu"
                n = 1
            if n and 0 < n <= 3650:
                return at(today + timedelta(days=n * L.DURATION_UNITS[tok]))
    # 2) "...gacha"
    for i, tok in enumerate(tokens):
        if tok in L.UNTIL_WORDS:
            return at(today + timedelta(days=L.UNTIL_WORDS[tok]))
        if tok.endswith("gacha") or tok.endswith("kacha"):
            base = tok[:-5]
            if base in L.WEEKDAY_WORDS:
                return at(_next_weekday(today, L.WEEKDAY_WORDS[base]))
            if base in MONTHS and i > 0 and tokens[i - 1].isdigit():
                return _month_day(today, MONTHS[base], int(tokens[i - 1]), z)
            if base.startswith("oxiri") and i > 0 and tokens[i - 1] in ("oy", "oyning"):
                nxt = (today.replace(day=28) + timedelta(days=4)).replace(day=1)
                return at(nxt - timedelta(days=1))
            if base.startswith("oxiri") and i > 0 and tokens[i - 1] in ("hafta", "haftaning"):
                return at(today + timedelta(days=6 - today.weekday()))
            if base in ("ertaga",):
                return at(today + timedelta(days=1))
    # 3) ruscha "do pyatnitsy" / inglizcha "until friday", "by friday"
    for i, tok in enumerate(tokens):
        if tok in ("do", "until", "till", "by") and i + 1 < len(tokens):
            nxt = tokens[i + 1]
            for cand in (nxt, nxt[:-1], nxt[:-1] + "a", nxt[:-2] + "a"):
                if cand in L.WEEKDAY_WORDS:
                    return at(_next_weekday(today, L.WEEKDAY_WORDS[cand]))
            if nxt.isdigit() and i + 2 < len(tokens) and tokens[i + 2] in MONTHS:
                return _month_day(today, MONTHS[tokens[i + 2]], int(nxt), z)
    return None


def _next_weekday(today: date, wd: int) -> date:
    delta = (wd - today.weekday()) % 7
    return today + timedelta(days=delta or 7)


def _month_day(today: date, mon: int, d: int, z) -> datetime | None:
    try:
        cand = date(today.year, mon, d)
        if cand < today:
            cand = date(today.year + 1, mon, d)
        return datetime.combine(cand, time(12, 0), tzinfo=z)
    except ValueError:
        return None


# ---------------- Kim bilan (qarz) ----------------

def _restore_case(raw: str, base: str) -> str:
    """Normalizatsiya hamma narsani kichik qiladi; asl matndan ismning yozilishini qaytaramiz."""
    m = re.search(re.escape(base), raw, flags=re.IGNORECASE)
    word = m.group(0) if m else base
    if not m:
        # kirill yozuvidagi ism: asl matndan topamiz (translit orqali), qo'shimchasiz qismini olamiz
        for w in re.findall(r"[А-Яа-яЎўҚқҒғҲҳЁё']{3,}", raw):
            if normalize(w).startswith(base):
                for k in range(len(w), 0, -1):
                    if normalize(w[:k]) == base:
                        word = w[:k]
                        break
                else:
                    word = w
                break
    if re.fullmatch(r"[А-Яа-яЎўҚқҒғҲҳЁё']+", word) and len(word) > 4 and word[-1] in "уаеы":
        word = word[:-1]   # ruscha kelishik qo'shimchasi: Азизу → Азиз
    return word[:1].upper() + word[1:]


def detect_counterparty(raw: str, tokens: list[str], prefer: str) -> str:
    """prefer: 'to' (-ga: kimga berdim), 'from' (-dan: kimdan oldim), 'subject' (Jasur qarzini qaytardi)."""
    def is_word(t: str) -> bool:
        return t.isalpha() or "'" in t

    def candidate(t: str, suffixes) -> str | None:
        if not is_word(t) or t in L.NOT_A_NAME or t in UNITS or t in MONTHS or t in L.DURATION_UNITS:
            return None
        if _match_keywords(t, [t], L.EXPENSE_KEYWORDS) or _match_keywords(t, [t], L.INCOME_KEYWORDS):
            return None
        for suf in suffixes:
            if t.endswith(suf) and len(t) - len(suf) >= 3:
                return t[: -len(suf)]
        return None

    order = {"to": (_NAME_SUFFIXES_TO, _NAME_SUFFIXES_FROM), "from": (_NAME_SUFFIXES_FROM, _NAME_SUFFIXES_TO)}
    if prefer == "subject":
        for i, t in enumerate(tokens):
            if t.startswith("qarz") and i > 0:
                prev = tokens[i - 1]
                if is_word(prev) and prev not in L.NOT_A_NAME and prev not in L.STOPWORDS and len(prev) >= 3 \
                        and not _contains(prev, L.REPAY_TO_ME):
                    return _restore_case(raw, prev)
        # "Jasur 100 ming qaytardi"
        for t in tokens:
            if is_word(t) and t not in L.NOT_A_NAME and t not in L.STOPWORDS and len(t) >= 3 and \
                    not any(t.startswith(v) for v in ("qaytar", "berdi", "vernul", "otdal", "qarz", "pul", "oldi", "uzdi", "to'la", "tola", "yop", "tashla")) and \
                    not _match_keywords(t, [t], L.EXPENSE_KEYWORDS):
                base = t
                for suf in (*_NAME_SUFFIXES_FROM, *_NAME_SUFFIXES_TO, "ning", "ni"):
                    if t.endswith(suf) and len(t) - len(suf) >= 3:
                        base = t[: -len(suf)]
                        break
                return _restore_case(raw, base)
        return ""
    for suffixes in order.get(prefer, (_NAME_SUFFIXES_TO, _NAME_SUFFIXES_FROM)):
        for t in tokens:
            base = candidate(t, suffixes)
            if base:
                return _restore_case(raw, base)
    # ruscha/inglizcha: "u Jasura", "ot Jasura", "to Jasur", "from Jasur", "Jasuru"
    for i, t in enumerate(tokens):
        if t in ("u", "ot", "to", "from", "dlya") and i + 1 < len(tokens):
            n = tokens[i + 1]
            if is_word(n) and n not in L.NOT_A_NAME and len(n) >= 3 and not n[0].isdigit():
                return _restore_case(raw, n.rstrip("a") if t in ("u", "ot") and len(n) > 4 else n)
    # bosh harf bilan yozilgan so'z (gap boshi emas)
    for w in re.findall(r"(?<!^)(?<=[\s,])([A-ZА-ЯЎҚҒҲ][a-zа-яўқғҳ']{2,})", raw):
        wl = normalize(w)
        if wl not in L.NOT_A_NAME and wl not in L.STOPWORDS and not _match_keywords(wl, [wl], L.EXPENSE_KEYWORDS):
            return _restore_case(raw, wl)
    return ""


_REPAY_STEMS = ("ber", "qaytar", "tashla", "uz", "to'la", "tola", "o'tkaz", "otkaz", "yop", "tushir", "jo'nat", "jonat")
_MY_OBJ = ("qarzimni", "qarzimdan", "qarzim", "pulimni", "pulim", "pulimdan")
_HIS_OBJ = ("qarzini", "qarzi", "qarzni", "qarzidan", "pulini", "puli", "pulni", "pulidan")


def _verb_person(toks: list[str]) -> str | None:
    """Qaytarish fe'li kim tomonidan: 'me' (berdim/qaytardim/berdik) yoki 'they' (berdi/qaytardi/berishdi)."""
    for t in reversed(toks):
        if t.startswith(_REPAY_STEMS):
            if t.endswith(("dim", "dik", "ganman", "dimku")):
                return "me"
            if t.endswith(("di", "dilar", "shdi", "gan", "diku")):
                return "they"
    return None


def _genitive_owner(raw: str, toks: list[str]) -> str:
    """«Alisherni qarzini», «Alisherning pulini» → Alisher."""
    for i, t in enumerate(toks):
        if t.startswith(("qarz", "pul")) and i > 0:
            for j in range(i - 1, -1, -1):
                w = toks[j]
                if w in L.NOT_A_NAME or w in L.STOPWORDS or not (w.isalpha() or "'" in w):
                    continue
                for suf in ("ning", "ni", "ing"):
                    if w.endswith(suf) and len(w) - len(suf) >= 3 and w not in _MY_OBJ and w not in _HIS_OBJ:
                        base = w[: -len(suf)]
                        if not _match_keywords(base, [base], L.EXPENSE_KEYWORDS) and base not in L.NOT_A_NAME:
                            return _restore_case(raw, base)
    return ""


def _contains_exact(text: str, words) -> bool:
    """So'z chegarasi ikki tomondan: 'qarzini berdi' ⊄ 'qarzini berdim'."""
    padded = f" {text} "
    return any(f" {w} " in padded for w in words)


def detect_repayment(raw: str, clause: str, toks: list[str]) -> tuple[str, str, bool] | None:
    """Qaytaradi: (direction, counterparty, hard). direction: 'given' = menga qaytarildi, 'taken' = men qaytardim.
    hard=True — «qarz» so'zi bilan aniq; False — «pulini berdim» kabi yumshoq (ochiq qarz bo'lsa qaytarish)."""
    # 1) tayyor iboralar (uz/ru/en)
    by_me = _contains_exact(clause, L.REPAY_BY_ME)
    to_me = _contains_exact(clause, L.REPAY_TO_ME) and not by_me
    if by_me or to_me:
        who = _genitive_owner(raw, toks) or detect_counterparty(raw, toks, "subject" if to_me else "to")
        return ("given" if to_me else "taken"), who, True
    # 2) umumiy qolip: [Ism-ni] qarzini/pulini + berdim/qaytardim/tashlab berdim/uzdim (yoki 3-shaxs)
    my_obj = any(t in _MY_OBJ for t in toks)
    his_obj = any(t in _HIS_OBJ for t in toks)
    if not (my_obj or his_obj):
        return None
    person = _verb_person(toks)
    took = any(t in ("oldim", "olib oldim", "undirdim", "qaytarib oldim") for t in toks) or _contains_exact(clause, ["qaytarib oldim", "olib oldim"])
    if took and my_obj:
        direction, person = "given", "me"          # "Alisherdan qarzimni oldim" → menga qaytdi
    elif not person:
        return None
    else:
        # "qarzimni berdim" / "Alisherni qarzini berdim" → men qaytardim; "qarzini berdi" / "pulimni qaytardi" → menga
        direction = "taken" if person == "me" else "given"
    # "Jasurga 100 ming qarz berdim" — yangi qarz (qarz so'zi qo'shimchasiz) → bu yerga tushmaydi
    hard = any(t.startswith("qarz") for t in toks)
    who = _genitive_owner(raw, toks)
    if not who:
        prefer = "from" if took else ("to" if direction == "taken" else "subject")
        who = detect_counterparty(raw, toks, prefer)
        if not who and prefer != "subject":
            who = detect_counterparty(raw, toks, "subject")
    if not hard and not who:
        return None          # "pulini berdim" — kim ekani noma'lum, yumshoq holat: oddiy yozuv bo'lib qoladi
    return direction, who, hard


def _is_name_token(t: str) -> bool:
    return (t.endswith(_NAME_SUFFIXES_TO) or t.endswith(_NAME_SUFFIXES_FROM)) and len(t) > 5 \
        and t not in L.NOT_A_NAME and (t.isalpha() or "'" in t)


def _clean_description(clause: str, span: AmountSpan, tokens: list[str], drop: set[str] | None = None) -> str:
    words = [t for k, t in enumerate(tokens) if not (span.start <= k < span.end)]
    out = []
    for w in words:
        if w in L.STOPWORDS or w.isdigit() or w in {":", "-", "/"} or w in MONTHS or (drop and w in drop):
            continue
        if w in L.DURATION_UNITS or w in L.UNTIL_WORDS or w.endswith("gacha") or w in L.WEEKDAY_WORDS:
            continue
        # qo'shimchalarni biroz tozalash: "taksiga" → "taksi"
        for suf in ("larga", "dagi", "ga", "dan", "ni", "da"):
            if len(w) > len(suf) + 3 and w.endswith(suf):
                w = w[: -len(suf)]
                break
        out.append(w)
    return " ".join(out[:6]).strip()


def _split_clauses(text: str) -> list[str]:
    parts = [p.strip() for p in _CLAUSE_SPLIT.split(text) if p and p.strip()]
    return parts or [text]


def _is_debt_clause(clause: str, toks: list[str]) -> bool:
    return any(t.startswith(("qarz", "nasiya", "zaym", "zayom", "zanyal", "odolzh", "odolj")) for t in toks) \
        or _contains(clause, ["v dolg", "dolg", "loan", "lent", "borrowed", "lend", "borrow"])


def _debt_direction(clause: str, toks: list[str]) -> tuple[str | None, float]:
    """(direction, ishonch). None — aniqlab bo'lmadi."""
    given = _contains(clause, L.DEBT_GIVEN_VERBS) or any(t.startswith(("berdi", "berib", "odolzh", "odolj", "lent", "lend")) for t in toks)
    taken = _contains(clause, L.DEBT_TAKEN_VERBS) or any(t.startswith(("oldi", "olib", "vzyal", "zanyal", "borrow")) for t in toks)
    if given and not taken:
        return "given", 0.92
    if taken and not given:
        return "taken", 0.92
    if given and taken:   # "qarz olib berdim" kabi — berdi oxirgi bo'lsa given
        last_g = max((i for i, t in enumerate(toks) if t.startswith(("berdi", "berib"))), default=-1)
        last_t = max((i for i, t in enumerate(toks) if t.startswith(("oldi", "olib"))), default=-1)
        return ("given" if last_g > last_t else "taken"), 0.7
    # fe'l yo'q: qo'shimcha bo'yicha taxmin
    if any(t.endswith(_NAME_SUFFIXES_FROM) and _is_name_token(t) for t in toks):
        return "taken", 0.7
    if any(t.endswith(_NAME_SUFFIXES_TO) and _is_name_token(t) for t in toks):
        return "given", 0.7
    return None, 0.55


def parse_local(raw_text: str, tz_name: str = "Asia/Tashkent", now: datetime | None = None) -> ParseResult:
    text = normalize(raw_text)
    occurred_at, date_uncertain = detect_date(text, tz_name, now)
    now_local = (now or datetime.now(tz(tz_name))).astimezone(tz(tz_name))
    global_income = _contains(text, L.INCOME_VERBS)
    all_tokens = tokenize(text)
    global_due = detect_due(text, all_tokens, now_local)

    result = ParseResult()

    # 0) Qarz qaytarildi / qaytardim (summa bo'lmasa ham ishlaydi)
    soft_only = True
    for clause in _split_clauses(text):
        toks = tokenize(clause)
        rep = detect_repayment(raw_text, clause, toks)
        if not rep:
            continue
        direction, who, hard = rep
        spans = [s for s in find_amounts(toks) if not s.is_bare_small]
        amount = spans[0].value if spans else None
        result.repayments.append(ParsedRepayment(
            direction=direction, amount=amount, counterparty=who,
            confidence=(0.9 if who else 0.75) if hard else 0.6,
        ))
        soft_only = soft_only and not hard
    # "qarz" so'zi aniq bo'lsa — bu faqat qaytarish. "pulini berdim" kabi yumshoq holatda xarajat/daromad
    # variantini ham qaytaramiz: ingest mos ochiq qarz topsa qaytarish, topmasa oddiy yozuv deb hisoblaydi.
    if result.repayments and not soft_only:
        return result

    # 1) bo'laklarga ajratish; bitta bo'lakda bir nechta summa bo'lsa — summalar orasidan bo'lamiz
    segments: list[tuple[str, list[str], AmountSpan]] = []
    for clause in _split_clauses(text):
        toks = tokenize(clause)
        spans = find_amounts(toks)
        if not spans:
            continue
        if len(spans) == 1:
            segments.append((clause, toks, spans[0]))
            continue
        # "150 ming taksi 80 ming obed" (summa → so'z) yoki "taksi 150 ming obed 80 ming" (so'z → summa).
        # Ikkala variantni quramiz va kategoriya kalit so'zlari ko'proq mos kelganini tanlaymiz.
        def build(mode: str) -> list[tuple[str, list[str], AmountSpan]]:
            out = []
            for k, sp in enumerate(spans):
                if mode == "before":
                    lo = spans[k - 1].end if k else 0
                    hi = sp.end if k + 1 < len(spans) else len(toks)
                else:
                    lo = sp.start if k else 0
                    hi = spans[k + 1].start if k + 1 < len(spans) else len(toks)
                sub = toks[lo:hi]
                out.append((" ".join(sub), sub,
                            AmountSpan(sp.start - lo, sp.end - lo, sp.value, sp.has_multiplier, sp.from_words_only)))
            return out

        def score(segs) -> int:
            return sum(
                1 for c, t, _ in segs
                if _match_keywords(c, t, L.EXPENSE_KEYWORDS) or _match_keywords(c, t, L.INCOME_KEYWORDS)
            )

        after, before = build("after"), build("before")
        segments.extend(before if score(before) > score(after) else after)

    if not segments:
        if result.repayments:
            return result
        return ParseResult(
            needs_clarification=True,
            clarification_question="Summani topa olmadim. Masalan: «Taksiga 35 ming» deb yozing yoki ayting.",
        )

    ambiguous_small: list[int] = []
    questions: list[str] = []
    for clause, toks, span in segments:
        if span.is_bare_small:
            ambiguous_small.append(span.value)
            continue

        account = "card" if _contains(clause, L.CARD_WORDS) else ("cash" if _contains(clause, L.CASH_WORDS) else None)
        conf = 0.93

        # ---- Qarz ----
        if _is_debt_clause(clause, toks):
            direction, dconf = _debt_direction(clause, toks)
            who = detect_counterparty(raw_text, toks, "to" if direction == "given" else "from")
            due = detect_due(clause, toks, now_local) or global_due
            if direction is None:
                direction = "given"
                questions.append("Qarzni siz berdingizmi yoki oldingizmi?")
            if not who:
                dconf = min(dconf, 0.72)
            who_n = normalize(who)[:4] if who else "§"
            drop = {t for t in toks if t.startswith(who_n) or t.startswith(_DEBT_NOISE_PREFIXES) or t in _DEBT_NOISE}
            note = _clean_description(clause, span, toks, drop=drop)
            result.debts.append(ParsedDebt(
                direction=direction, amount=span.value, counterparty=who[:40], note=note[:60],
                occurred_at=occurred_at, due_at=due, confidence=round(dconf - (0.03 if span.from_words_only else 0), 2),
            ))
            continue

        # ---- Xarajat / daromad ----
        is_income = _contains(clause, L.INCOME_VERBS) or bool(_match_keywords(clause, toks, L.INCOME_KEYWORDS))
        is_expense_verb = _contains(clause, L.EXPENSE_VERBS)
        if len(segments) == 1 and global_income:
            is_income = True
        exp_cat = _match_keywords(clause, toks, L.EXPENSE_KEYWORDS)
        # "Akmaldan 500 ming oldim" — kimdandir pul oldim: daromad yoki qarz (xarajat emas)
        if not exp_cat and not is_income and _contains(clause, ["oldim", "olib turdim", "berdi", "vzyal", "poluchil"]) \
                and any(t.endswith(_NAME_SUFFIXES_FROM) and _is_name_token(t) for t in toks):
            is_income = True
        if is_income and is_expense_verb and exp_cat:
            is_income = False  # "oylik berdim" — xarajat (ishchiga)
        if exp_cat == "loss":
            is_income = False  # "100 ming yo'qotib qo'ydim" — zarar

        alt: ParsedDebt | None = None
        if is_income:
            cat = _match_keywords(clause, toks, L.INCOME_KEYWORDS) or "other_income"
            if cat == "other_income" and not _contains(clause, ["daromad", "doxod", "daxod", "dohod", "prixod"]):
                conf = 0.72  # "2 million keldi" — manba noma'lum, tasdiq so'raymiz
            ttype = TxType.income
            # "Akmaldan 500 ming oldim" — daromadmi yoki qarz oldimmi?
            if cat == "other_income" and _contains(clause, ["oldim", "olib turdim", "berdi", "vzyal"]) \
                    and any(t.endswith(_NAME_SUFFIXES_FROM) and _is_name_token(t) for t in toks):
                who = detect_counterparty(raw_text, toks, "from")
                if who:
                    conf = 0.62
                    questions.append(f"{who}dan olingan pul — daromadmi yoki qarzmi?")
                    alt = ParsedDebt(direction="taken", amount=span.value, counterparty=who[:40],
                                     occurred_at=occurred_at, due_at=global_due, confidence=0.6)
        else:
            cat = exp_cat
            ttype = TxType.expense
            if not cat:
                cat = "other"
                conf = 0.8
                # "Akmalga 2 million berdim" — qarz/o'tkazma bo'lishi mumkin
                if any(t.endswith(_NAME_SUFFIXES_TO) and _is_name_token(t) for t in toks) and \
                        (_contains(clause, ["berdim", "o'tkazdim", "otkazdim", "tashladim", "tashlab", "jo'natdim", "dal", "perevel"])
                         or not is_expense_verb):
                    conf = 0.62
                    who = detect_counterparty(raw_text, toks, "to")
                    questions.append(f"{who or 'Bu'}ga berilgan pul — xarajatmi yoki qarzmi?")
                    alt = ParsedDebt(direction="given", amount=span.value, counterparty=(who or "")[:40],
                                     occurred_at=occurred_at, due_at=global_due, confidence=0.6)
            elif cat == "loss":
                conf = 0.9
        if span.from_words_only:
            conf -= 0.03
        if date_uncertain:
            conf = min(conf, 0.75)

        desc = _clean_description(clause, span, toks)
        if cat == "loss" and not desc:
            desc = "yo'qotilgan pul"
        if cat == "found" and not desc:
            desc = "topilgan pul"
        result.items.append(ParsedItem(
            type=ttype, amount=span.value, category_key=cat, description=desc,
            occurred_at=occurred_at, account_hint=account, confidence=round(conf, 2),
        ))
        if alt and result.alt_debt is None:
            result.alt_debt = alt

    if ambiguous_small and result.is_empty:
        v = ambiguous_small[0]
        return ParseResult(
            needs_clarification=True,
            clarification_question=f"{v} — bu {v} ming so'mmi?",
            amount_options=[v * 1000, v * 1_000_000 if v < 100 else v],
        )
    result.needs_clarification = bool(questions)
    result.clarification_question = questions[0] if questions else None
    return result
