"""Xavfsizlik: ma'lumot shifrlash (AES-256-GCM), HMAC, Telegram WebApp initData tekshiruvi."""
from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
import time
from dataclasses import dataclass
from urllib.parse import parse_qsl

from cryptography.hazmat.primitives.ciphers.aead import AESGCM

from app.core.config import get_settings

_VERSION = b"\x01"


class CryptoError(Exception):
    pass


class Cipher:
    """Matnni AES-256-GCM bilan shifrlaydi. Format: version(1) | nonce(12) | ciphertext+tag."""

    def __init__(self, key_b64: str):
        if not key_b64:
            raise CryptoError("DATA_ENCRYPTION_KEY .env da berilmagan")
        key = base64.b64decode(key_b64)
        if len(key) != 32:
            raise CryptoError("DATA_ENCRYPTION_KEY 32 bayt (base64) bo'lishi kerak")
        self._aes = AESGCM(key)

    def encrypt(self, text: str | None, aad: bytes = b"") -> bytes | None:
        if text is None or text == "":
            return None
        nonce = os.urandom(12)
        return _VERSION + nonce + self._aes.encrypt(nonce, text.encode("utf-8"), aad or None)

    def decrypt(self, blob: bytes | memoryview | None, aad: bytes = b"") -> str:
        if not blob:
            return ""
        blob = bytes(blob)
        if blob[:1] != _VERSION:
            raise CryptoError("noma'lum shifr versiyasi")
        nonce, ct = blob[1:13], blob[13:]
        return self._aes.decrypt(nonce, ct, aad or None).decode("utf-8")


_cipher: Cipher | None = None


def cipher() -> Cipher:
    global _cipher
    if _cipher is None:
        _cipher = Cipher(get_settings().data_encryption_key)
    return _cipher


def user_aad(user_id) -> bytes:
    """Shifrlangan matn aynan shu userga bog'lanadi: boshqa user qatoriga ko'chirilsa ochilmaydi."""
    return str(user_id).encode()


def phrase_hash(user_id, phrase: str) -> str:
    s = get_settings()
    secret = (s.hash_secret or s.data_encryption_key or "hisobchi").encode()
    return hmac.new(secret, f"{user_id}:{phrase}".encode(), hashlib.sha256).hexdigest()[:40]


# ---------------- Telegram WebApp initData ----------------

@dataclass(slots=True)
class TelegramWebUser:
    id: int
    first_name: str | None
    username: str | None
    language_code: str | None


class InitDataError(Exception):
    pass


def validate_init_data(init_data: str, bot_token: str, max_age_sec: int) -> TelegramWebUser:
    """https://core.telegram.org/bots/webapps#validating-data-received-via-the-mini-app

    Mini app yuborgan har bir so'rov imzosi bot token bilan HMAC orqali tekshiriladi.
    user_id hech qachon clientdan parametr sifatida olinmaydi — faqat imzolangan initData dan.
    """
    if not init_data or not bot_token:
        raise InitDataError("initData yo'q")
    pairs = dict(parse_qsl(init_data, keep_blank_values=True, strict_parsing=False))
    received_hash = pairs.pop("hash", None)
    if not received_hash:
        raise InitDataError("hash yo'q")
    # Eslatma: "signature" maydoni ham data-check-string ga kiradi (faqat "hash" chiqariladi).
    check_string = "\n".join(f"{k}={pairs[k]}" for k in sorted(pairs))
    secret_key = hmac.new(b"WebAppData", bot_token.encode(), hashlib.sha256).digest()
    calc = hmac.new(secret_key, check_string.encode(), hashlib.sha256).hexdigest()
    if not hmac.compare_digest(calc, received_hash):
        raise InitDataError("imzo noto'g'ri")
    try:
        auth_date = int(pairs.get("auth_date", "0"))
    except ValueError as e:
        raise InitDataError("auth_date noto'g'ri") from e
    if max_age_sec and time.time() - auth_date > max_age_sec:
        raise InitDataError("initData eskirgan")
    try:
        u = json.loads(pairs.get("user", "{}"))
        return TelegramWebUser(
            id=int(u["id"]),
            first_name=u.get("first_name"),
            username=u.get("username"),
            language_code=u.get("language_code"),
        )
    except Exception as e:  # noqa: BLE001
        raise InitDataError("user maydoni noto'g'ri") from e


# ---------------- Qisqa muddatli imzolangan tokenlar (fayl yuklab olish) ----------------

def sign_token(payload: dict, ttl_sec: int = 300) -> str:
    s = get_settings()
    body = dict(payload, exp=int(time.time()) + ttl_sec)
    raw = base64.urlsafe_b64encode(json.dumps(body, separators=(",", ":")).encode()).rstrip(b"=")
    sig = hmac.new((s.hash_secret or s.bot_token).encode(), raw, hashlib.sha256).digest()
    return raw.decode() + "." + base64.urlsafe_b64encode(sig).rstrip(b"=").decode()


def verify_token(token: str) -> dict:
    s = get_settings()
    try:
        raw, sig = token.split(".", 1)
        expected = base64.urlsafe_b64encode(
            hmac.new((s.hash_secret or s.bot_token).encode(), raw.encode(), hashlib.sha256).digest()
        ).rstrip(b"=").decode()
        if not hmac.compare_digest(expected, sig):
            raise ValueError("sig")
        body = json.loads(base64.urlsafe_b64decode(raw + "=" * (-len(raw) % 4)))
        if body.get("exp", 0) < time.time():
            raise ValueError("exp")
        return body
    except Exception as e:  # noqa: BLE001
        raise InitDataError("token yaroqsiz") from e
