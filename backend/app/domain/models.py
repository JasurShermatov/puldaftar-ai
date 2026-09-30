"""Domen modellari (DB'dan mustaqil, pydantic)."""
from __future__ import annotations

from datetime import datetime
from enum import Enum
from uuid import UUID

from pydantic import BaseModel, Field


class TxType(str, Enum):
    expense = "expense"
    income = "income"


class AccessState(str, Enum):
    trial = "trial"
    pro = "pro"
    expired = "expired"


class ParsedItem(BaseModel):
    type: TxType
    amount: int = Field(gt=0, lt=1_000_000_000_000)
    category_key: str
    description: str = ""
    occurred_at: datetime
    account_hint: str | None = None      # card | cash | None
    confidence: float = Field(ge=0, le=1)


class ParseResult(BaseModel):
    items: list[ParsedItem] = []
    needs_clarification: bool = False
    clarification_question: str | None = None
    # "Reklama 800" kabi holatlarda tugma variantlari
    amount_options: list[int] = []
    engine: str = "local"                 # local | llm | llm+local


class User(BaseModel):
    id: UUID
    telegram_id: int
    username: str | None = None
    first_name: str | None = None
    language: str = "uz"
    timezone: str = "Asia/Tashkent"
    report_enabled: bool = True
    report_time: str = "23:59"
    role: str = "user"
    is_blocked: bool = False
    trial_ends_at: datetime
    pro_until: datetime | None = None
    created_at: datetime
    last_active_at: datetime

    @property
    def is_superadmin(self) -> bool:
        return self.role == "superadmin"
