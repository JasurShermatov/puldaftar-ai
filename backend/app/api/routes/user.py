"""Mini App user API. Har bir endpoint faqat autentifikatsiyalangan userning o'z ma'lumotiga tegadi."""
from __future__ import annotations

from datetime import date, timedelta
from urllib.parse import quote
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, Response

from app.api.deps import current_user
from app.api.schemas import (CategoryIn, CategoryPatch, ChatIn, DebtCreate, DebtPatch, DebtPay, ExportIn, Period,
                             SettingsIn, TextIn, TxCreate, TxUpdate)
from app.core.config import get_settings
from app.core.security import InitDataError, sign_token, verify_token
from app.core.timeutil import local_now, period_bounds, to_utc_range
from app.db.database import db
from app.domain.models import User
from app.repositories import categories as catrepo
from app.repositories import transactions as txrepo
from app.repositories import users as userrepo
from app.services import ai_chat
from app.services import debts as debt_svc
from app.services import export as export_svc
from app.services import insights as insight_svc
from app.services import notifier, ratelimit
from app.services import reports as report_svc
from app.services import transactions as tx_svc
from app.services.access import access_of
from app.services.billing import list_plans

router = APIRouter(prefix="/api", tags=["user"])


def _parse_day(s: str | None, user: User) -> date:
    if not s:
        return local_now(user.timezone).date()
    try:
        return date.fromisoformat(s)
    except ValueError as e:
        raise HTTPException(422, "date format YYYY-MM-DD") from e


@router.get("/me")
async def me(user: User = Depends(current_user)):
    acc = access_of(user)
    plans = await list_plans()
    return {
        "user": {"first_name": user.first_name, "username": user.username, "language": user.language,
                 "timezone": user.timezone, "report_enabled": user.report_enabled, "report_time": user.report_time,
                 "created_at": user.created_at.isoformat()},
        "access": {"state": acc.state.value, "ends_at": acc.ends_at.isoformat() if acc.ends_at else None,
                   "days_left": acc.days_left},
        "plans": [{k: p[k] for k in ("code", "name", "days", "price", "old_price", "badge")} for p in plans],
        "is_admin": user.is_superadmin,
        "ai_enabled": get_settings().ai_enabled,
    }


@router.patch("/me/settings")
async def update_settings(body: SettingsIn, user: User = Depends(current_user)):
    if body.timezone:
        try:
            from zoneinfo import ZoneInfo
            ZoneInfo(body.timezone)
        except Exception as e:  # noqa: BLE001
            raise HTTPException(422, "timezone noto'g'ri") from e
    async with db.user_tx(user.id) as conn:
        await userrepo.update_settings(conn, user.id, report_enabled=body.report_enabled,
                                       report_time=body.report_time, timezone=body.timezone, language=body.language)
    return {"ok": True}


@router.get("/dashboard")
async def dashboard(user: User = Depends(current_user)):
    return await report_svc.dashboard(user)


@router.get("/transactions")
async def list_transactions(
    period: Period = "month", date_: str | None = Query(default=None, alias="date"),
    type: str | None = Query(default=None, pattern="^(expense|income)$"),
    category_id: int | None = None, limit: int = Query(default=100, le=500), offset: int = Query(default=0, ge=0),
    user: User = Depends(current_user),
):
    day = _parse_day(date_, user)
    ps, pe = period_bounds(period, day, user.timezone)
    s, e = to_utc_range(ps, pe, user.timezone)
    async with db.user_tx(user.id) as conn:
        rows = await txrepo.list_range(conn, user.id, s, e, limit=limit, offset=offset, type_=type,
                                       category_id=category_id)
        totals = await txrepo.totals(conn, user.id, s, e)
        cats = await txrepo.by_category(conn, user.id, s, e, "expense")
    return {"period": period, "start": ps.isoformat(), "end": (pe - timedelta(days=1)).isoformat(),
            "totals": totals, "categories": cats,
            "items": [report_svc.serialize_tx(r, user.timezone) for r in rows]}


@router.post("/transactions")
async def create_transaction(body: TxCreate, user: User = Depends(current_user)):
    row = await tx_svc.add_manual(user, type_="", amount=body.amount, category_id=body.category_id,
                                  description=body.description, occurred_at=body.occurred_at)
    if not row:
        raise HTTPException(402 if not access_of(user).can_add else 422, "not allowed")
    return report_svc.serialize_tx(row, user.timezone)


@router.post("/transactions/text")
async def create_from_text(body: TextIn, user: User = Depends(current_user)):
    if not await ratelimit.hit(f"parse:{user.telegram_id}", get_settings().rate_limit_per_minute):
        raise HTTPException(429, "Juda tez, biroz kuting")
    out = await tx_svc.ingest(user, body.text, source="text", source_key=None)
    return _ingest_json(out, user)


def _ingest_json(out: tx_svc.IngestOutcome, user: User) -> dict:
    today = local_now(user.timezone).date()
    return {
        "kind": out.kind,
        "saved": [report_svc.serialize_tx(r, user.timezone) for r in out.saved],
        "saved_debts": [debt_svc.serialize(d, user.timezone, today) for d in out.saved_debts],
        "repaid": [debt_svc.serialize(d, user.timezone, today) for d in out.repaid],
        "repay_status": out.repay_status,
        "pending_id": str(out.pending_id) if out.pending_id else None,
        "pending_items": out.pending_items,
        "pending_debts": out.pending_debts,
        "has_alt_debt": out.has_alt_debt,
        "question": out.question,
        "amount_options": out.amount_options,
    }


@router.post("/pending/{pending_id}/confirm")
async def confirm_pending(pending_id: UUID, choice: str = Query(default="ok", pattern="^(ok|debt)$"),
                          user: User = Depends(current_user)):
    res = await tx_svc.confirm_pending(user, pending_id, choice=choice)
    today = local_now(user.timezone).date()
    return {"saved": [report_svc.serialize_tx(r, user.timezone) for r in res.saved],
            "saved_debts": [debt_svc.serialize(d, user.timezone, today) for d in res.saved_debts]}


@router.post("/pending/{pending_id}/amount/{amount}")
async def choose_amount(pending_id: UUID, amount: int, user: User = Depends(current_user)):
    if amount <= 0:
        raise HTTPException(422)
    out = await tx_svc.choose_amount(user, pending_id, amount)
    return {"kind": out.kind, "saved": [report_svc.serialize_tx(r, user.timezone) for r in out.saved]}


@router.delete("/pending/{pending_id}")
async def cancel_pending(pending_id: UUID, user: User = Depends(current_user)):
    await tx_svc.cancel_pending(user, pending_id)
    return {"ok": True}


@router.patch("/transactions/{tx_id}")
async def update_transaction(tx_id: UUID, body: TxUpdate, user: User = Depends(current_user)):
    row = await tx_svc.update_tx(user, tx_id, amount=body.amount, category_id=body.category_id,
                                 description=body.description, occurred_at=body.occurred_at)
    if not row:
        raise HTTPException(404, "topilmadi")
    return report_svc.serialize_tx(row, user.timezone)


@router.delete("/transactions/{tx_id}")
async def delete_transaction(tx_id: UUID, user: User = Depends(current_user)):
    if not await tx_svc.delete_tx(user, tx_id):
        raise HTTPException(404, "topilmadi")
    return {"ok": True}


@router.post("/transactions/{tx_id}/restore")
async def restore_transaction(tx_id: UUID, user: User = Depends(current_user)):
    async with db.user_tx(user.id) as conn:
        ok = await txrepo.restore(conn, user.id, tx_id)
    if not ok:
        raise HTTPException(404)
    return {"ok": True}


@router.get("/categories")
async def categories(user: User = Depends(current_user)):
    async with db.user_tx(user.id) as conn:
        return await catrepo.list_for_user(conn, user.id)


@router.post("/categories")
async def create_category(body: CategoryIn, user: User = Depends(current_user)):
    async with db.user_tx(user.id) as conn:
        return await catrepo.create_custom(conn, user.id, body.type, body.name.strip(), body.emoji)


@router.patch("/categories/{cat_id}")
async def patch_category(cat_id: int, body: CategoryPatch, user: User = Depends(current_user)):
    async with db.user_tx(user.id) as conn:
        ok = await catrepo.update_custom(conn, user.id, cat_id, body.name, body.is_active)
    if not ok:
        raise HTTPException(404, "faqat o'zingiz yaratgan kategoriyani o'zgartira olasiz")
    return {"ok": True}


@router.get("/insights")
async def insights(kind: str = Query(default="weekly", pattern="^(daily|weekly)$"),
                   refresh: bool = False, user: User = Depends(current_user)):
    if not access_of(user).can_ai:
        raise HTTPException(402, "PRO kerak")
    if refresh and not await ratelimit.hit(f"insight:{user.telegram_id}", 5, 3600):
        refresh = False
    text = await insight_svc.generate(user, kind, force=refresh)
    stats = await insight_svc.compute_stats(user)
    return {"text": text, "stats": stats}


# ---------------- Qarzlar ----------------

@router.get("/debts")
async def debts_list(status: str = Query(default="open", pattern="^(open|paid|all)$"),
                     user: User = Depends(current_user)):
    return await debt_svc.list_debts(user, None if status == "all" else status)


@router.post("/debts")
async def debts_create(body: DebtCreate, user: User = Depends(current_user)):
    if not access_of(user).can_add:
        raise HTTPException(402, "PRO kerak")
    row = await debt_svc.create_manual(user, direction=body.direction, amount=body.amount,
                                       counterparty=body.counterparty.strip(), note=body.note.strip(),
                                       due_at=body.due_at, occurred_at=body.occurred_at)
    if not row:
        raise HTTPException(422, "saqlab bo'lmadi")
    return debt_svc.serialize(row, user.timezone)


@router.patch("/debts/{debt_id}")
async def debts_update(debt_id: UUID, body: DebtPatch, user: User = Depends(current_user)):
    row = await debt_svc.update(user, debt_id, amount=body.amount, counterparty=body.counterparty, note=body.note,
                                due_at=body.due_at, clear_due=body.clear_due)
    if not row:
        raise HTTPException(404, "topilmadi")
    return debt_svc.serialize(row, user.timezone)


@router.post("/debts/{debt_id}/pay")
async def debts_pay(debt_id: UUID, body: DebtPay, user: User = Depends(current_user)):
    row = await debt_svc.pay(user, debt_id, body.amount)
    if not row:
        raise HTTPException(404, "topilmadi yoki allaqachon yopilgan")
    return debt_svc.serialize(row, user.timezone)


@router.post("/debts/{debt_id}/reopen")
async def debts_reopen(debt_id: UUID, user: User = Depends(current_user)):
    if not await debt_svc.reopen(user, debt_id):
        raise HTTPException(404, "topilmadi")
    return {"ok": True}


@router.delete("/debts/{debt_id}")
async def debts_delete(debt_id: UUID, user: User = Depends(current_user)):
    if not await debt_svc.delete(user, debt_id):
        raise HTTPException(404, "topilmadi")
    return {"ok": True}


# ---------------- AI chat ----------------

@router.get("/ai/chat")
async def chat_history(user: User = Depends(current_user)):
    return {"messages": await ai_chat.history(user), "suggestions": ai_chat.SUGGESTIONS,
            "ai_enabled": get_settings().ai_enabled}


@router.post("/ai/chat")
async def chat_ask(body: ChatIn, user: User = Depends(current_user)):
    if not access_of(user).can_ai:
        raise HTTPException(402, "PRO kerak")
    if not await ratelimit.hit(f"aichat:{user.telegram_id}", 20, 3600):
        raise HTTPException(429, "Soatiga 20 ta savol. Biroz kuting.")
    res = await ai_chat.ask(user, body.message)
    return {"answer": res["answer"], "ai": res["ai"]}


@router.delete("/ai/chat")
async def chat_clear(user: User = Depends(current_user)):
    await ai_chat.clear(user)
    return {"ok": True}


@router.post("/export")
async def export(body: ExportIn, user: User = Depends(current_user)):
    if not access_of(user).can_export:
        raise HTTPException(402, "PRO kerak")
    if not await ratelimit.hit(f"export:{user.telegram_id}", 10, 600):
        raise HTTPException(429, "Juda ko'p eksport, 10 daqiqadan keyin urinib ko'ring")
    day = _parse_day(body.date, user)
    if body.delivery == "link":
        token = sign_token({"u": str(user.id), "p": body.period, "f": body.format, "d": day.isoformat()}, ttl_sec=300)
        return {"url": f"{get_settings().public_base_url.rstrip('/')}/api/export/download?token={token}"}
    fn = export_svc.export_xlsx if body.format == "xlsx" else export_svc.export_csv
    name, data = await fn(user, body.period, day)
    ok = await notifier.send_document(user.telegram_id, name, data,
                                      caption=f"📥 {export_svc.PERIOD_LABEL[body.period].capitalize()} hisobot")
    if not ok:
        raise HTTPException(502, "Faylni yuborib bo'lmadi")
    return {"ok": True, "filename": name}


@router.get("/export/download", include_in_schema=False)
async def export_download(token: str):
    """Qisqa muddatli (5 daqiqa) imzolangan link — Telegram.WebApp.downloadFile uchun."""
    try:
        body = verify_token(token)
    except InitDataError as e:
        raise HTTPException(403, "link eskirgan") from e
    async with db.system_tx() as conn:
        user = await userrepo.get(conn, UUID(body["u"]))
    if not user or user.is_blocked:
        raise HTTPException(404)
    fn = export_svc.export_xlsx if body["f"] == "xlsx" else export_svc.export_csv
    name, data = await fn(user, body["p"], date.fromisoformat(body["d"]))
    media = ("application/vnd.openxmlformats-officedocument.spreadsheetml.sheet" if body["f"] == "xlsx"
             else "text/csv; charset=utf-8")
    return Response(data, media_type=media, headers={
        "Content-Disposition": f"attachment; filename*=UTF-8''{quote(name)}",
        "Cache-Control": "no-store",
    })


@router.post("/billing/plans-to-chat")
async def plans_to_chat(user: User = Depends(current_user)):
    """Mini app'dagi «Botda to'lash» → bot user chatiga tariflar ro'yxatini tugmalar bilan yuboradi."""
    from app.bot import keyboards as kb
    from app.bot import views
    from app.services import billing

    plans = await list_plans()
    ok = await notifier.send(user.telegram_id, views.plan_text(user) + billing.plans_text(plans),
                             reply_markup=kb.plans(plans))
    if not ok:
        raise HTTPException(502)
    return {"ok": True}


@router.delete("/me")
async def delete_me(user: User = Depends(current_user)):
    """Userning barcha ma'lumotlari butunlay o'chiriladi (CASCADE)."""
    if user.is_superadmin:
        raise HTTPException(400, "superadmin o'chira olmaydi")
    async with db.system_tx() as conn:
        await userrepo.delete(conn, user.id)
    return {"ok": True}

