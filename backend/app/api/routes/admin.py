"""Superadmin API (mini app ichidagi admin panel). Faqat role=superadmin."""
from __future__ import annotations

import base64
import binascii
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query

from app.api.deps import admin_user
from app.api.schemas import (
    AISettingsIn, BillingSettingsIn, BlockIn, BroadcastIn, DaysIn, GrantPlanIn, PlanCreate, PlanPatch, RejectIn,
)
from app.core.config import get_settings
from app.db.database import db
from app.domain.models import User
from app.services import ratelimit
from app.repositories import payments as payrepo
from app.repositories import plans as planrepo
from app.repositories import system as sysrepo
from app.repositories import users as userrepo
from app.services import admin as admin_svc
from app.services import billing, notifier
from app.services import broadcast as bc
from app.services.access import access_of

router = APIRouter(prefix="/api/admin", tags=["admin"])


@router.get("/stats")
async def stats(_: User = Depends(admin_user)):
    return await admin_svc.dashboard_stats()


@router.get("/users")
async def users(q: str | None = None, status: str | None = Query(default=None, pattern="^(blocked|pro|trial|expired)$"),
                limit: int = Query(default=30, le=100), offset: int = Query(default=0, ge=0),
                _: User = Depends(admin_user)):
    async with db.system_tx() as conn:
        rows, total = await userrepo.search(conn, q, status, limit, offset)
    items = []
    for r in rows:
        u = User(**{k: r[k] for k in User.model_fields if k in r})
        acc = access_of(u)
        items.append({
            "id": str(r["id"]), "telegram_id": r["telegram_id"], "username": r["username"],
            "first_name": r["first_name"], "role": r["role"], "is_blocked": r["is_blocked"],
            "created_at": r["created_at"].isoformat(), "last_active_at": r["last_active_at"].isoformat(),
            "tx_count": r["tx_count"], "access": acc.state.value, "days_left": acc.days_left,
            "pro_until": r["pro_until"].isoformat() if r["pro_until"] else None,
            "trial_ends_at": r["trial_ends_at"].isoformat(),
        })
    return {"total": total, "items": items}


@router.get("/users/{user_id}")
async def user_detail(user_id: UUID, _: User = Depends(admin_user)):
    d = await admin_svc.user_detail(user_id)
    if not d:
        raise HTTPException(404)
    return d


@router.post("/users/{user_id}/block")
async def block(user_id: UUID, body: BlockIn, admin: User = Depends(admin_user)):
    if not await admin_svc.block(admin.telegram_id, user_id, body.blocked, body.reason):
        raise HTTPException(400, "bloklab bo'lmaydi")
    return {"ok": True}


@router.post("/users/{user_id}/pro")
async def grant_pro(user_id: UUID, body: DaysIn, admin: User = Depends(admin_user)):
    until = await admin_svc.grant_pro(admin.telegram_id, user_id, body.days)
    if not until:
        raise HTTPException(404)
    return {"ok": True, "pro_until": until}


@router.post("/users/{user_id}/plan")
async def grant_plan(user_id: UUID, body: GrantPlanIn, admin: User = Depends(admin_user)):
    """Admin userga 1 oylik / 3 oylik / 1 yillik obunani to'lovsiz ochib beradi."""
    res = await admin_svc.grant_plan(admin.telegram_id, user_id, body.plan_code)
    if not res:
        raise HTTPException(404, "user yoki tarif topilmadi")
    return {"ok": True, "pro_until": res}


@router.get("/plans")
async def plans(_: User = Depends(admin_user)):
    async with db.system_tx() as conn:
        return await planrepo.list_plans(conn, active_only=False)


@router.post("/plans")
async def create_plan(body: PlanCreate, admin: User = Depends(admin_user)):
    async with db.system_tx() as conn:
        row = await planrepo.create(conn, name=body.name.strip(), days=body.days, price=body.price,
                                    old_price=body.old_price or None, badge=(body.badge or "").strip() or None,
                                    is_active=body.is_active)
        await sysrepo.audit(conn, admin.telegram_id, "plan.create", meta=row)
    return row


@router.delete("/plans/{code}")
async def delete_plan(code: str, admin: User = Depends(admin_user)):
    async with db.system_tx() as conn:
        active_left = await conn.fetchval("SELECT count(*) FROM plans WHERE is_active AND NOT archived AND code<>$1", code)
        if not active_left:
            raise HTTPException(409, "Kamida bitta faol tarif qolishi kerak")
        res = await planrepo.delete(conn, code)
        if not res:
            raise HTTPException(404)
        await sysrepo.audit(conn, admin.telegram_id, "plan.delete", meta={"code": code, "result": res})
    return {"ok": True, "result": res}


@router.patch("/plans/{code}")
async def patch_plan(code: str, body: PlanPatch, admin: User = Depends(admin_user)):
    patch = body.model_dump(exclude_none=True)
    if patch.get("old_price") == 0:
        patch["old_price"] = None
    if "badge" in patch and not patch["badge"].strip():
        patch["badge"] = None
    async with db.system_tx() as conn:
        row = await planrepo.update(conn, code, patch)
        if not row:
            raise HTTPException(404)
        await sysrepo.audit(conn, admin.telegram_id, "plan.update", meta={"code": code, **{k: v for k, v in patch.items()}})
    return row


@router.delete("/users/{user_id}/pro")
async def revoke_pro(user_id: UUID, admin: User = Depends(admin_user)):
    await admin_svc.revoke_pro(admin.telegram_id, user_id)
    return {"ok": True}


@router.post("/users/{user_id}/trial")
async def extend_trial(user_id: UUID, body: DaysIn, admin: User = Depends(admin_user)):
    until = await admin_svc.extend_trial(admin.telegram_id, user_id, body.days)
    if not until:
        raise HTTPException(404)
    return {"ok": True, "trial_ends_at": until}


@router.delete("/users/{user_id}")
async def delete_user(user_id: UUID, admin: User = Depends(admin_user)):
    if not await admin_svc.delete_user(admin.telegram_id, user_id):
        raise HTTPException(400, "o'chirib bo'lmaydi")
    return {"ok": True}


@router.get("/payments")
async def payments(status: str | None = Query(default="pending", pattern="^(pending|approved|rejected|all)$"),
                   limit: int = Query(default=50, le=200), offset: int = 0, _: User = Depends(admin_user)):
    async with db.system_tx() as conn:
        rows = await payrepo.list_requests(conn, None if status == "all" else status, limit, offset)
    return [{**r, "id": str(r["id"]), "user_id": str(r["user_id"])} for r in rows]


@router.post("/payments/{req_id}/approve")
async def approve(req_id: UUID, admin: User = Depends(admin_user)):
    d = await billing.approve(req_id, admin.telegram_id)
    if not d.ok:
        raise HTTPException(409, d.message)
    await notifier.send(d.user_tg_id, billing.approved_text(d.pro_until))
    return {"ok": True, "pro_until": d.pro_until}


@router.post("/payments/{req_id}/reject")
async def reject(req_id: UUID, body: RejectIn, admin: User = Depends(admin_user)):
    d = await billing.reject(req_id, admin.telegram_id, body.reason)
    if not d.ok:
        raise HTTPException(409, d.message)
    await notifier.send(d.user_tg_id, billing.rejected_text(body.reason))
    return {"ok": True}


@router.get("/settings")
async def get_all_settings(_: User = Depends(admin_user)):
    async with db.system_tx() as conn:
        return {k: await sysrepo.get_setting(conn, k) for k in ("billing", "ai")}


@router.patch("/settings/billing")
async def patch_billing(body: BillingSettingsIn, admin: User = Depends(admin_user)):
    patch = body.model_dump(exclude_none=True)
    if patch.get("card_number"):
        digits = patch["card_number"].replace(" ", "")
        if not 16 <= len(digits) <= 19:
            raise HTTPException(422, "Karta raqami 16–19 raqam bo'lishi kerak")
        patch["card_number"] = " ".join(digits[i:i + 4] for i in range(0, len(digits), 4))
    if "admin_username" in patch:
        patch["admin_username"] = patch["admin_username"].lstrip("@")
    async with db.system_tx() as conn:
        val = await sysrepo.set_setting(conn, "billing", patch)
        await sysrepo.audit(conn, admin.telegram_id, "settings.billing",
                            meta={k: ("***" if k == "card_number" else v) for k, v in patch.items()})
    return val


@router.patch("/settings/ai")
async def patch_ai(body: AISettingsIn, admin: User = Depends(admin_user)):
    patch = body.model_dump(exclude_none=True)
    async with db.system_tx() as conn:
        val = await sysrepo.set_setting(conn, "ai", patch)
        await sysrepo.audit(conn, admin.telegram_id, "settings.ai", meta=patch)
    return val


@router.get("/broadcast/count")
async def broadcast_count(segment: str = "all", admin: User = Depends(admin_user)):
    try:
        return {"count": await bc.count(segment, admin.telegram_id)}
    except ValueError as e:
        raise HTTPException(422, "segment") from e


@router.post("/broadcast")
async def broadcast(body: BroadcastIn, admin: User = Depends(admin_user)):
    """Reklama / chegirma e'loni: matn, ixtiyoriy rasm va tugma (havola) bilan barcha userlarga."""
    text = bc.normalize_html(body.text.strip())
    err = bc.validate_html(text)
    if err:
        raise HTTPException(422, f"Matnda xato: {err}")
    if bool(body.button_text) != bool(body.button_url):
        raise HTTPException(422, "Tugma uchun matn ham, havola ham kerak")
    if body.photo_base64:
        try:
            raw = body.photo_base64.split(",", 1)[-1]          # "data:image/jpeg;base64,..." ham qabul qilinadi
            photo = base64.b64decode(raw, validate=True)
        except (binascii.Error, ValueError) as e:
            raise HTTPException(422, "Rasm noto'g'ri") from e
        if len(photo) > 5 * 1024 * 1024 or not (photo[:3] == b"\xff\xd8\xff" or photo[:8] == b"\x89PNG\r\n\x1a\n"):
            raise HTTPException(422, "Faqat JPG/PNG, 5 MB gacha")
        if len(text) > 1024:
            raise HTTPException(422, "Rasm bilan matn 1024 belgidan oshmasin")
        res = await bc.start_photo(admin.telegram_id, body.segment, photo, text or None, body.button_text, body.button_url)
    else:
        if not text:
            raise HTTPException(422, "Matn bo'sh")
        res = await bc.start_text(admin.telegram_id, body.segment, text, body.button_text, body.button_url)
    return {"ok": True, **res}


@router.get("/broadcasts")
async def broadcasts(_: User = Depends(admin_user)):
    return await bc.history()


@router.get("/audit")
async def audit(limit: int = Query(default=100, le=500), offset: int = 0, _: User = Depends(admin_user)):
    async with db.system_tx() as conn:
        rows = await sysrepo.audit_list(conn, limit, offset)
    return [{**r, "target_user_id": str(r["target_user_id"]) if r["target_user_id"] else None} for r in rows]


@router.get("/health")
async def health(_: User = Depends(admin_user)):
    s = get_settings()
    redis_ok = None
    if ratelimit.redis() is not None:
        try:
            redis_ok = bool(await ratelimit.redis().ping())
        except Exception:  # noqa: BLE001
            redis_ok = False
    webhook = None
    try:
        info = await notifier.bot().get_webhook_info()
        webhook = {"url_set": bool(info.url), "pending": info.pending_update_count,
                   "last_error": info.last_error_message}
    except Exception:  # noqa: BLE001
        pass
    return {"db": await db.ping(), "redis": redis_ok, "ai_enabled": s.ai_enabled, "bot_mode": s.bot_mode,
            "webhook": webhook, "models": {"parser": s.openai_parser_model, "stt": s.openai_stt_model,
                                           "insight": s.openai_insight_model}}
