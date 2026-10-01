"""TZ acceptance holatlari (AC-01..AC-06) va summa formatlari uchun unit testlar.

Ishga tushirish: pytest -q   (yoki pytest bo'lmasa: python -m tests.test_parser)
"""
from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

from app.services.parsing.local_parser import parse_local
from app.services.parsing.normalize import normalize, tokenize
from app.services.parsing.numbers import find_amounts

TZ = "Asia/Tashkent"
NOW = datetime(2026, 9, 30, 14, 30, tzinfo=ZoneInfo(TZ))


def amounts(text: str) -> list[int]:
    return [s.value for s in find_amounts(tokenize(normalize(text)))]


def test_amount_formats():
    cases = {
        "35 ming": 35_000,
        "uch yuz ellik ming": 350_000,
        "1 yarim million": 1_500_000,
        "ikki yarim mln": 2_500_000,
        "4 million 300 ming": 4_300_000,
        "1.2 mln": 1_200_000,
        "1,5 mln": 1_500_000,
        "800k": 800_000,
        "bir million": 1_000_000,
        "yuz ming": 100_000,
        "35 000 so'm": 35_000,
        "150000": 150_000,
        "yarim million": 500_000,
        "million yarim": 1_500_000,
        "двести тысяч": 200_000,
        "1.5 млн": 1_500_000,
        "45ming": 45_000,
    }
    for text, expected in cases.items():
        assert amounts(text) == [expected], (text, amounts(text))


def test_not_amounts():
    assert amounts("2 ta non") == []
    assert amounts("soat 13:30 da") == []
    assert amounts("15-sentabr") == []
    assert amounts("bir kofe") == []


def _one(text):
    r = parse_local(text, TZ, NOW)
    return r


def test_ac01_two_expenses():
    r = _one("Bugun taksiga 35 ming, obedga 80 ming ketdi")
    assert [(i.amount, i.category_key, i.type.value) for i in r.items] == [
        (35_000, "taxi", "expense"), (80_000, "food", "expense")]
    assert all(i.confidence >= 0.85 for i in r.items)


def test_ac01_no_comma():
    r = _one("Bugun 150 ming taksi 80 ming obed")
    assert [(i.amount, i.category_key) for i in r.items] == [(150_000, "taxi"), (80_000, "food")]
    r = _one("taksi 150 ming obed 80 ming")
    assert [(i.amount, i.category_key) for i in r.items] == [(150_000, "taxi"), (80_000, "food")]


def test_ac02_income():
    r = _one("Bugun 4 yarim million daxod bo'ldi")
    assert len(r.items) == 1
    assert r.items[0].type.value == "income" and r.items[0].amount == 4_500_000


def test_ac03_mixed_russian():
    r = _one("Segodnya reklama uchun 800 ming rasxod, dostavka 120 ming")
    assert [(i.amount, i.category_key) for i in r.items] == [(800_000, "advertising"), (120_000, "delivery")]


def test_ac04_yesterday():
    r = _one("Kecha benzin 300 ming")
    it = r.items[0]
    assert it.category_key == "fuel" and it.amount == 300_000
    assert it.occurred_at.date() == (NOW - timedelta(days=1)).date()


def test_ac05_ambiguous_transfer():
    r = _one("Akmalga 2 million berdim")
    assert r.items and r.items[0].confidence < 0.85  # avto-saqlanmaydi, tasdiq so'raladi


def test_ac06_unit_unknown():
    r = _one("Reklama 800")
    assert not r.items and r.needs_clarification and 800_000 in r.amount_options


def test_no_amount():
    r = _one("Bozorga bordim")
    assert not r.items and r.needs_clarification


def test_card_utilities():
    r = _one("Kartadan 250 ming kommunal to'ladim")
    it = r.items[0]
    assert (it.category_key, it.account_hint, it.amount) == ("utilities", "card", 250_000)


def test_income_unknown_source_needs_confirm():
    r = _one("2 million keldi")
    assert r.items[0].type.value == "income" and r.items[0].confidence < 0.85


def test_cyrillic():
    r = _one("Такси 40 тысяч")
    assert (r.items[0].amount, r.items[0].category_key) == (40_000, "taxi")


def test_english_and_mixed():
    r = _one("Lunch 60 thousand and taxi 40k")
    assert [(i.amount, i.category_key) for i in r.items] == [(60_000, "food"), (40_000, "taxi")]
    r = _one("Кофе 25 тысяч, dostavka 30 ming")
    assert [(i.amount, i.category_key) for i in r.items] == [(25_000, "food"), (30_000, "delivery")]
    r = _one("Yesterday spent 200 thousand on groceries")
    assert r.items[0].amount == 200_000 and r.items[0].category_key == "groceries"
    assert r.items[0].occurred_at.date() == (NOW - timedelta(days=1)).date()
    r = _one("Такси сто пятьдесят тысяч")
    assert r.items[0].amount == 150_000


def test_found_and_lost():
    r = _one("ko'chadan 100 ming topib oldim")
    assert r.items[0].type.value == "income" and r.items[0].category_key == "found" and r.items[0].amount == 100_000
    r = _one("100 ming yo'qotib qo'ydim")
    assert r.items[0].type.value == "expense" and r.items[0].category_key == "loss"
    r = _one("yutib oldim 300 ming")
    assert r.items[0].type.value == "income" and r.items[0].category_key == "found"


def test_debt_given_with_due():
    r = _one("Jasurga 100 ming qarz berdim 2 kunga")
    assert not r.items and len(r.debts) == 1
    d = r.debts[0]
    assert (d.direction, d.amount, d.counterparty) == ("given", 100_000, "Jasur")
    assert d.due_at.date() == (NOW + timedelta(days=2)).date()
    assert d.confidence >= 0.85


def test_debt_taken_with_due_and_name_after():
    r = _one("500 ming qarz oldim 3 kunga Jasurdan")
    d = r.debts[0]
    assert (d.direction, d.amount, d.counterparty) == ("taken", 500_000, "Jasur")
    assert d.due_at.date() == (NOW + timedelta(days=3)).date()


def test_debt_russian_english_cyrillic():
    r = _one("Дал в долг Азизу 200 тысяч на неделю")
    d = r.debts[0]
    assert (d.direction, d.amount, d.counterparty) == ("given", 200_000, "Азиз")
    assert d.due_at.date() == (NOW + timedelta(days=7)).date()
    r = _one("Lent 50k to Bob for 3 days")
    assert (r.debts[0].direction, r.debts[0].counterparty, r.debts[0].amount) == ("given", "Bob", 50_000)
    r = _one("Шерзодга 50 минг қарз бердим 2 кунга")
    assert (r.debts[0].direction, r.debts[0].counterparty) == ("given", "Шерзод")


def test_debt_without_name_needs_confirm():
    r = _one("qarz oldim 200 ming")
    assert r.debts and r.debts[0].direction == "taken" and r.debts[0].confidence < 0.85


def test_ambiguous_transfer_has_alt_debt():
    r = _one("Akmalga 2 million berdim")
    assert r.items[0].confidence < 0.85 and r.alt_debt is not None
    assert (r.alt_debt.direction, r.alt_debt.counterparty) == ("given", "Akmal")
    r = _one("Akmaldan 500 ming oldim")
    assert r.items[0].type.value == "income" and r.alt_debt and r.alt_debt.direction == "taken"


def test_repayments():
    r = _one("Jasur qarzini qaytardi")
    assert r.repayments and r.repayments[0].direction == "given" and r.repayments[0].counterparty == "Jasur"
    assert r.repayments[0].amount is None
    r = _one("Jasurga qarzimni qaytardim 300 ming")
    assert r.repayments[0].direction == "taken" and r.repayments[0].amount == 300_000


def test_due_variants():
    assert _one("Dilshodga 1 million qarz berdim jumagacha").debts[0].due_at.date().weekday() == 4
    assert _one("Jasurdan 500 ming qarz oldim 15 oktabrgacha").debts[0].due_at.date() == date(2026, 10, 15)
    assert _one("Aliga 300 ming qarz berdim ertagacha").debts[0].due_at.date() == (NOW + timedelta(days=1)).date()
    assert _one("Aliga 300 ming qarz berdim bir haftaga").debts[0].due_at.date() == (NOW + timedelta(days=7)).date()
    assert _one("Aliga 300 ming qarz berdim").debts[0].due_at is None


if __name__ == "__main__":
    import sys
    fails = 0
    for name, fn in list(globals().items()):
        if name.startswith("test_") and callable(fn):
            try:
                fn()
                print("PASS", name)
            except AssertionError as e:
                fails += 1
                print("FAIL", name, e)
    sys.exit(1 if fails else 0)
