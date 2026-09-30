"""Deterministik (AI'siz) parser. AI o'chiq bo'lsa asosiy parser, AI yoqilgan bo'lsa —
summalarni tekshiruvchi "hakam" (LLM gallyutsinatsiyasiga qarshi)."""
from __future__ import annotations

import re
from datetime import date, datetime, time, timedelta

from app.core.timeutil import tz
from app.domain.models import ParsedItem, ParseResult, TxType
from app.services.parsing import lexicon as L
from app.services.parsing.normalize import normalize, tokenize
from app.services.parsing.numbers import MONTHS, AmountSpan, find_amounts

_CLAUSE_SPLIT = re.compile(r"[,;\n]+|\.(?!\d)|\s+va\s+|\s+ham\s+|\s+keyin\s+|\s+i\s+|\s+yana\s+|\s+and\s+")


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
        if m and m.group(2) in MONTHS:
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


def _clean_description(clause: str, span: AmountSpan, tokens: list[str]) -> str:
    words = [t for k, t in enumerate(tokens) if not (span.start <= k < span.end)]
    out = []
    for w in words:
        if w in L.STOPWORDS or w.isdigit() or w in {":", "-", "/"} or w in MONTHS:
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


def parse_local(raw_text: str, tz_name: str = "Asia/Tashkent", now: datetime | None = None) -> ParseResult:
    text = normalize(raw_text)
    occurred_at, date_uncertain = detect_date(text, tz_name, now)
    global_income = _contains(text, L.INCOME_VERBS)

    # 1) bo'laklarga ajratish; bitta bo'lakda bir nechta summa bo'lsa — summalar orasidan bo'lamiz
    segments: list[tuple[str, list[str], AmountSpan]] = []
    orphan_context: list[str] = []
    for clause in _split_clauses(text):
        toks = tokenize(clause)
        spans = find_amounts(toks)
        if not spans:
            orphan_context.append(clause)
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
        return ParseResult(
            needs_clarification=True,
            clarification_question="Summani topa olmadim. Masalan: «Taksiga 35 ming» deb yozing yoki ayting.",
        )

    items: list[ParsedItem] = []
    ambiguous_small: list[int] = []
    questions: list[str] = []
    for clause, toks, span in segments:
        if span.is_bare_small:
            ambiguous_small.append(span.value)
            continue
        is_income = _contains(clause, L.INCOME_VERBS) or bool(_match_keywords(clause, toks, L.INCOME_KEYWORDS))
        is_expense_verb = _contains(clause, L.EXPENSE_VERBS)
        if len(segments) == 1 and global_income:
            is_income = True
        if is_income and is_expense_verb and _match_keywords(clause, toks, L.EXPENSE_KEYWORDS):
            is_income = False  # "oylik berdim" — xarajat (ishchiga)

        conf = 0.93
        if is_income:
            cat = _match_keywords(clause, toks, L.INCOME_KEYWORDS) or "other_income"
            if cat == "other_income" and not _contains(clause, ["daromad", "doxod", "daxod", "dohod", "prixod"]):
                conf = 0.72  # "2 million keldi" — manba noma'lum, tasdiq so'raymiz
            ttype = TxType.income
        else:
            cat = _match_keywords(clause, toks, L.EXPENSE_KEYWORDS)
            ttype = TxType.expense
            if not cat:
                cat = "other"
                conf = 0.8
                # "Akmalga 2 million berdim" — qarz/o'tkazma bo'lishi mumkin
                if any(t.endswith("ga") and len(t) > 4 for t in toks) and _contains(clause, ["berdim", "o'tkazdim", "otkazdim"]):
                    conf = 0.65
                    questions.append("Bu xarajatmi yoki qarz/o'tkazmami?")
        if span.from_words_only:
            conf -= 0.03
        if date_uncertain:
            conf = min(conf, 0.75)

        account = "card" if _contains(clause, L.CARD_WORDS) else ("cash" if _contains(clause, L.CASH_WORDS) else None)
        desc = _clean_description(clause, span, toks)
        items.append(ParsedItem(
            type=ttype, amount=span.value, category_key=cat, description=desc,
            occurred_at=occurred_at, account_hint=account, confidence=round(conf, 2),
        ))

    if ambiguous_small and not items:
        v = ambiguous_small[0]
        return ParseResult(
            needs_clarification=True,
            clarification_question=f"{v} — bu {v} ming so'mmi?",
            amount_options=[v * 1000, v * 1_000_000 if v < 100 else v],
        )
    return ParseResult(items=items, needs_clarification=bool(questions),
                       clarification_question=questions[0] if questions else None)
