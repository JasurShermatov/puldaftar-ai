"""Obuna/entitlement qoidalari (trial → PRO → expired). Backend har PRO amalda tekshiradi."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from app.core.timeutil import now_utc
from app.domain.models import AccessState, User


@dataclass(slots=True)
class Access:
    state: AccessState
    ends_at: datetime | None
    days_left: int

    @property
    def can_add(self) -> bool:
        return self.state != AccessState.expired

    @property
    def can_export(self) -> bool:
        return self.state != AccessState.expired

    @property
    def can_ai(self) -> bool:
        return self.state != AccessState.expired


def access_of(user: User, now: datetime | None = None) -> Access:
    now = now or now_utc()
    if user.is_superadmin:
        return Access(AccessState.pro, None, 9999)
    if user.pro_until and user.pro_until > now:
        return Access(AccessState.pro, user.pro_until, max(0, (user.pro_until - now).days))
    if user.trial_ends_at > now:
        return Access(AccessState.trial, user.trial_ends_at, max(0, (user.trial_ends_at - now).days))
    return Access(AccessState.expired, user.pro_until or user.trial_ends_at, 0)
