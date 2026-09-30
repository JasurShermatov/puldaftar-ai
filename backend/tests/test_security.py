"""initData imzo tekshiruvi, shifrlash va token testlari."""
import base64
import hashlib
import hmac
import json
import os
import time
from urllib.parse import urlencode

os.environ.setdefault("DATA_ENCRYPTION_KEY", base64.b64encode(b"k" * 32).decode())
os.environ.setdefault("BOT_TOKEN", "123456:TEST_TOKEN_abcdefghijklmnopqrstuvwxyz")
os.environ.setdefault("HASH_SECRET", "test-secret")

from app.core.security import (  # noqa: E402
    Cipher, CryptoError, InitDataError, sign_token, user_aad, validate_init_data, verify_token,
)

BOT = os.environ["BOT_TOKEN"]


def make_init_data(user_id=42, auth_date=None, token=BOT):
    data = {"auth_date": str(auth_date or int(time.time())), "query_id": "AAE",
            "user": json.dumps({"id": user_id, "first_name": "Ali", "username": "ali"})}
    check = "\n".join(f"{k}={data[k]}" for k in sorted(data))
    secret = hmac.new(b"WebAppData", token.encode(), hashlib.sha256).digest()
    data["hash"] = hmac.new(secret, check.encode(), hashlib.sha256).hexdigest()
    return urlencode(data)


def test_init_data_ok():
    u = validate_init_data(make_init_data(42), BOT, 3600)
    assert u.id == 42 and u.username == "ali"


def test_init_data_tampered():
    raw = make_init_data(42).replace("42", "43", 1)
    try:
        validate_init_data(raw, BOT, 3600)
        raise AssertionError("tampered accepted")
    except InitDataError:
        pass


def test_init_data_wrong_bot():
    try:
        validate_init_data(make_init_data(42, token="999:OTHER"), BOT, 3600)
        raise AssertionError("foreign bot accepted")
    except InitDataError:
        pass


def test_init_data_expired():
    try:
        validate_init_data(make_init_data(42, auth_date=int(time.time()) - 100000), BOT, 3600)
        raise AssertionError("expired accepted")
    except InitDataError:
        pass


def test_cipher_roundtrip_and_user_binding():
    c = Cipher(os.environ["DATA_ENCRYPTION_KEY"])
    blob = c.encrypt("taksi", user_aad("user-A"))
    assert c.decrypt(blob, user_aad("user-A")) == "taksi"
    try:
        c.decrypt(blob, user_aad("user-B"))   # boshqa userga ko'chirilgan shifr ochilmaydi
        raise AssertionError("cross-user decrypt")
    except Exception as e:  # noqa: BLE001
        assert not isinstance(e, AssertionError)
    assert c.encrypt("taksi") != c.encrypt("taksi")   # har safar yangi nonce


def test_cipher_bad_key():
    try:
        Cipher(base64.b64encode(b"short").decode())
        raise AssertionError
    except CryptoError:
        pass


def test_signed_token():
    t = sign_token({"u": "x"}, ttl_sec=60)
    assert verify_token(t)["u"] == "x"
    try:
        verify_token(t[:-2] + "aa")
        raise AssertionError
    except InitDataError:
        pass


if __name__ == "__main__":
    for name, fn in list(globals().items()):
        if name.startswith("test_") and callable(fn):
            fn()
            print("PASS", name)
