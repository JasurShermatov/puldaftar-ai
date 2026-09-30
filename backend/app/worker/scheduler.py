"""Fon jarayoni (alohida konteyner): kunlik 23:59 hisobot, AI tahlil, trial/PRO eslatmalari, tozalash.

    python -m app.worker.scheduler

Bir nechta worker ishga tushsa ham hisobot IKKI MARTA ketmaydi: har bir (user, kun) reports jadvalida
UNIQUE; avval "claim" qilinadi, keyin yuboriladi.
"""
from __future__ import annotations

import asyncio
import logging
import signal
from datetime import date

from app.bot import keyboards as kb
from app.bot.setup import create_bot
from app.bot.texts import uz as T
from app.core.config import get_settings
from app.core.logging import setup_logging
from app.db.database import db
from app.repositories import system as sysrepo
from app.repositories import users as userrepo
from app.services import insights as insight_svc
from app.services import notifier
from app.services import reports as report_svc
from app.services.access import access_of

log = logging.getLogger("worker")
_stop = asyncio.Event()
SEM = asyncio.Semaphore(20)


async def _send_daily(user_id, day: date) -> None:
    async with SEM:
        async with db.system_tx() as conn:
            if not await sysrepo.claim_report(conn, user_id, "daily", day):
                return
            user = await userrepo.get(conn, user_id)
        if not user:
            return
        try:
            text = await report_svc.daily_report_text(user, day, final=True)
            ok = await notifier.send(user.telegram_id, text, reply_markup=kb.open_dashboard(text="📊 Grafiklar"))
            status = "sent" if ok else "failed"
            # AI tahlil: har kuni qisqa, yakshanba — haftalik chuqur
            if ok and get_settings().ai_enabled and access_of(user).can_ai:
                kind = "weekly" if day.weekday() == 6 else "daily"
                try:
                    insight = await insight_svc.generate(user, kind)
                    if insight and "yetarli emas" not in insight:
                        await notifier.send(user.telegram_id, insight)
                except Exception as e:  # noqa: BLE001
                    log.warning("insight failed: %s", type(e).__name__)
        except Exception:  # noqa: BLE001
            log.exception("daily report failed")
            status = "failed"
        async with db.system_tx() as conn:
            await sysrepo.mark_report(conn, user_id, "daily", day, status)
            if status == "sent":
                await sysrepo.event(conn, "daily_report_sent", user_id)


async def daily_reports_loop() -> None:
    while not _stop.is_set():
        try:
            async with db.system_tx() as conn:
                due = await userrepo.due_reports(conn)
            if due:
                log.info("daily reports due: %d", len(due))
                await asyncio.gather(*(_send_daily(r["id"], r["day"]) for r in due))
        except Exception:  # noqa: BLE001
            log.exception("report loop error")
        await _sleep(15)


REMINDER_TEXT = {"trial_d2": T.TRIAL_D2, "trial_end": T.TRIAL_END, "pro_d3": T.PRO_D3, "pro_end": T.PRO_END}


async def reminders_loop() -> None:
    while not _stop.is_set():
        try:
            for kind, text in REMINDER_TEXT.items():
                async with db.system_tx() as conn:
                    rows = await userrepo.list_for_reminders(conn, kind)
                for r in rows:
                    async with db.system_tx() as conn:
                        if not await sysrepo.claim_report(conn, r["id"], kind, r["key_day"]):
                            continue
                    await notifier.send(r["telegram_id"], text, reply_markup=kb.plan(True))
                    await asyncio.sleep(0.05)
        except Exception:  # noqa: BLE001
            log.exception("reminder loop error")
        await _sleep(600)


async def cleanup_loop() -> None:
    while not _stop.is_set():
        try:
            async with db.system_tx() as conn:
                await sysrepo.cleanup(conn)
        except Exception:  # noqa: BLE001
            log.exception("cleanup error")
        await _sleep(3600)


async def _sleep(sec: float) -> None:
    try:
        await asyncio.wait_for(_stop.wait(), timeout=sec)
    except asyncio.TimeoutError:
        pass


async def main() -> None:
    s = get_settings()
    setup_logging(s.log_level)
    await db.connect()
    bot = create_bot()
    notifier.set_bot(bot)
    loop = asyncio.get_running_loop()
    for sig in (signal.SIGTERM, signal.SIGINT):
        try:
            loop.add_signal_handler(sig, _stop.set)
        except NotImplementedError:
            pass
    log.info("worker started")
    await asyncio.gather(daily_reports_loop(), reminders_loop(), cleanup_loop())
    await bot.session.close()
    await db.close()


if __name__ == "__main__":
    asyncio.run(main())
