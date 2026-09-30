from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field

Period = Literal["day", "week", "month", "year"]


class SettingsIn(BaseModel):
    report_enabled: bool | None = None
    report_time: str | None = Field(default=None, pattern=r"^([01]\d|2[0-3]):[0-5]\d$")
    timezone: str | None = Field(default=None, max_length=64)
    language: Literal["uz", "ru"] | None = None


class TxCreate(BaseModel):
    amount: int = Field(gt=0, lt=1_000_000_000_000)
    category_id: int
    description: str = Field(default="", max_length=120)
    occurred_at: datetime | None = None


class TxUpdate(BaseModel):
    amount: int | None = Field(default=None, gt=0, lt=1_000_000_000_000)
    category_id: int | None = None
    description: str | None = Field(default=None, max_length=120)
    occurred_at: datetime | None = None


class TextIn(BaseModel):
    text: str = Field(min_length=1, max_length=1000)


class CategoryIn(BaseModel):
    type: Literal["expense", "income"] = "expense"
    name: str = Field(min_length=1, max_length=40)
    emoji: str = Field(default="•", max_length=4)


class CategoryPatch(BaseModel):
    name: str | None = Field(default=None, max_length=40)
    is_active: bool | None = None


class ExportIn(BaseModel):
    period: Period = "month"
    format: Literal["xlsx", "csv"] = "xlsx"
    date: str | None = None          # YYYY-MM-DD (shu sana tushgan davr)
    delivery: Literal["chat", "link"] = "chat"


# ---- admin ----
class BlockIn(BaseModel):
    blocked: bool
    reason: str | None = Field(default=None, max_length=200)


class DaysIn(BaseModel):
    days: int = Field(gt=0, le=3650)


class RejectIn(BaseModel):
    reason: str | None = Field(default=None, max_length=200)


class BillingSettingsIn(BaseModel):
    trial_days: int | None = Field(default=None, ge=0, le=365)
    card_number: str | None = Field(default=None, max_length=32, pattern=r"^([\d ]{16,23})?$")
    card_holder: str | None = Field(default=None, max_length=80)
    admin_username: str | None = Field(default=None, max_length=64)


class PlanPatch(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=40)
    days: int | None = Field(default=None, gt=0, le=3650)
    price: int | None = Field(default=None, gt=0, lt=1_000_000_000)
    old_price: int | None = Field(default=None, ge=0, lt=1_000_000_000)   # 0 = chegirmani olib tashlash
    badge: str | None = Field(default=None, max_length=24)                 # "" = olib tashlash
    is_active: bool | None = None


class PlanCreate(BaseModel):
    name: str = Field(min_length=1, max_length=40)
    days: int = Field(gt=0, le=3650)
    price: int = Field(gt=0, lt=1_000_000_000)
    old_price: int | None = Field(default=None, ge=0, lt=1_000_000_000)
    badge: str | None = Field(default=None, max_length=24)
    is_active: bool = True


class GrantPlanIn(BaseModel):
    plan_code: str = Field(pattern=r"^[a-z0-9_]{1,16}$")


class AISettingsIn(BaseModel):
    auto_save_threshold: float | None = Field(default=None, ge=0.5, le=1.0)
    confirm_threshold: float | None = Field(default=None, ge=0.1, le=0.95)


class BroadcastIn(BaseModel):
    text: str = Field(default="", max_length=3500)
    segment: Literal["all", "pro", "trial", "expired", "active7", "inactive7", "self"] = "all"
    button_text: str | None = Field(default=None, max_length=40)
    button_url: str | None = Field(default=None, max_length=300, pattern=r"^(https://|tg://)\S+$")
    photo_base64: str | None = Field(default=None, max_length=7_000_000)   # ~5 MB rasm
