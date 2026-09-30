"""Vaqt yordamchilari. DB da hamma vaqt UTC, ko'rsatish user timezone bo'yicha."""
from __future__ import annotations

from datetime import date, datetime, time, timedelta, timezone
from zoneinfo import ZoneInfo

UTC = timezone.utc


def tz(name: str | None) -> ZoneInfo:
    try:
        return ZoneInfo(name or "Asia/Tashkent")
    except Exception:  # noqa: BLE001
        return ZoneInfo("Asia/Tashkent")


def now_utc() -> datetime:
    return datetime.now(UTC)


def local_now(tz_name: str) -> datetime:
    return now_utc().astimezone(tz(tz_name))


def local_day_bounds(day: date, tz_name: str) -> tuple[datetime, datetime]:
    """Lokal kunning [boshi, oxiri) UTC da."""
    z = tz(tz_name)
    start = datetime.combine(day, time.min, tzinfo=z)
    return start.astimezone(UTC), (start + timedelta(days=1)).astimezone(UTC)


def period_bounds(period: str, day: date, tz_name: str) -> tuple[date, date]:
    """period: day|week|month|year → [start, end) lokal sanalar."""
    if period == "day":
        return day, day + timedelta(days=1)
    if period == "week":
        start = day - timedelta(days=day.weekday())
        return start, start + timedelta(days=7)
    if period == "month":
        start = day.replace(day=1)
        nxt = (start.replace(day=28) + timedelta(days=4)).replace(day=1)
        return start, nxt
    if period == "year":
        return day.replace(month=1, day=1), day.replace(year=day.year + 1, month=1, day=1)
    raise ValueError(period)


def to_utc_range(start: date, end: date, tz_name: str) -> tuple[datetime, datetime]:
    z = tz(tz_name)
    return (
        datetime.combine(start, time.min, tzinfo=z).astimezone(UTC),
        datetime.combine(end, time.min, tzinfo=z).astimezone(UTC),
    )


def fmt_money(amount: int) -> str:
    return f"{int(amount):,}".replace(",", " ") + " so'm"


def fmt_money_short(amount: int) -> str:
    a = int(amount)
    if a >= 1_000_000:
        v = a / 1_000_000
        return (f"{v:.1f}".rstrip("0").rstrip(".")) + " mln"
    if a >= 1_000:
        return f"{a // 1000} ming"
    return str(a)
