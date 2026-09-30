"""OpenAI adapter. Provayder almashtirilishi mumkin: faqat shu modul OpenAI'ni biladi."""
from __future__ import annotations

import json
import logging
import time
from typing import Any

from app.core.config import get_settings

log = logging.getLogger(__name__)

_client = None
_MIME = {"ogg": "audio/ogg", "oga": "audio/ogg", "mp3": "audio/mpeg", "m4a": "audio/mp4", "mp4": "video/mp4",
         "wav": "audio/wav", "flac": "audio/flac", "webm": "audio/webm"}


class AIUnavailable(Exception):
    pass


def client():
    global _client
    s = get_settings()
    if not s.openai_api_key:
        raise AIUnavailable("OPENAI_API_KEY berilmagan")
    if _client is None:
        from openai import AsyncOpenAI

        _client = AsyncOpenAI(
            api_key=s.openai_api_key,
            # DIQQAT: bo'sh OPENAI_BASE_URL="" bo'lsa SDK uni None emas deb oladi va ulanolmaydi — shuning uchun aniq default
            base_url=(s.openai_base_url or "").strip() or "https://api.openai.com/v1",
            timeout=s.openai_timeout_sec,
            max_retries=2,
        )
    return _client


async def chat_json(*, model: str, system: str, user: str, schema: dict[str, Any], name: str,
                    temperature: float = 0.0) -> dict:
    """Strict JSON schema bilan javob. User matni doim `data` sifatida beriladi (prompt injection himoyasi)."""
    t0 = time.perf_counter()
    resp = await client().chat.completions.create(
        model=model,
        temperature=temperature,
        messages=[
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ],
        response_format={"type": "json_schema", "json_schema": {"name": name, "strict": True, "schema": schema}},
    )
    content = resp.choices[0].message.content or "{}"
    log.info("llm %s ok %.0fms", name, (time.perf_counter() - t0) * 1000)
    return json.loads(content)


async def chat_text(*, model: str, system: str, user: str, temperature: float = 0.4, max_tokens: int = 600) -> str:
    resp = await client().chat.completions.create(
        model=model,
        temperature=temperature,
        max_tokens=max_tokens,
        messages=[{"role": "system", "content": system}, {"role": "user", "content": user}],
    )
    return (resp.choices[0].message.content or "").strip()


STT_PROMPT = (
    "Kundalik moliyaviy nutq: o'zbekcha (lotin), ruscha va inglizcha so'zlar aralash bo'lishi mumkin. "
    "Uzbek, Russian and English mixed speech about daily expenses and income. "
    "Summalar: ming, million, mln, yarim, so'm, тысяч, миллион, сум, thousand, k. "
    "Misollar: Bugun taksiga 35 ming, obedga 80 ming ketdi. Segodnya reklama uchun 800 ming rasxod. "
    "Kecha benzin 300 ming. Oylik 6 million tushdi. Кофе 25 тысяч. Lunch 60 ming, taxi 40k. "
    "Dostavka, Korzinka, Evos, Yandex Go, Click, Payme."
)


def describe_error(e: Exception) -> str:
    """Xatoni logga yozish uchun qisqa, maxfiy ma'lumotsiz tavsif."""
    status = getattr(e, "status_code", None)
    msg = str(getattr(e, "message", "") or e)[:300]
    return f"{type(e).__name__} status={status} {msg}"


async def _transcribe_once(model: str, audio: bytes, filename: str) -> str:
    mime = _MIME.get(filename.rsplit(".", 1)[-1].lower(), "application/octet-stream")
    kwargs = dict(model=model, file=(filename, audio, mime), prompt=STT_PROMPT)
    if model.startswith("gpt-4o"):
        kwargs["temperature"] = 0
    resp = await client().audio.transcriptions.create(**kwargs)
    return (getattr(resp, "text", "") or "").strip()


async def transcribe(audio: bytes, filename: str = "voice.ogg") -> str:
    """Ovoz → matn (o'zbek/rus/ingliz aralash). Asosiy model ishlamasa — whisper-1 bilan qayta urinadi.
    Audio diskka yozilmaydi, faqat xotirada ishlanadi."""
    s = get_settings()
    models = [s.openai_stt_model] + (["whisper-1"] if s.openai_stt_model != "whisper-1" else [])
    last: Exception | None = None
    for model in models:
        t0 = time.perf_counter()
        try:
            text = await _transcribe_once(model, audio, filename)
            log.info("stt ok model=%s %.0fms len=%d", model, (time.perf_counter() - t0) * 1000, len(text))
            if text:
                return text
        except Exception as e:  # noqa: BLE001
            last = e
            log.warning("stt failed model=%s: %s", model, describe_error(e))
    if last:
        raise last
    return ""


async def health_check() -> dict:
    """Admin uchun: kalit ishlayaptimi, modellar mavjudmi."""
    s = get_settings()
    out: dict = {"key_set": bool(s.openai_api_key)}
    if not s.openai_api_key:
        return out
    for name, model in (("parser", s.openai_parser_model), ("stt", s.openai_stt_model), ("whisper", "whisper-1")):
        try:
            await client().models.retrieve(model)
            out[name] = f"✅ {model}"
        except Exception as e:  # noqa: BLE001
            out[name] = f"❌ {model}: {describe_error(e)[:160]}"
    try:
        t0 = time.perf_counter()
        r = await client().chat.completions.create(
            model=s.openai_parser_model, max_tokens=5,
            messages=[{"role": "user", "content": "Reply with: OK"}],
        )
        out["chat"] = f"✅ javob '{(r.choices[0].message.content or '').strip()}' {(time.perf_counter() - t0) * 1000:.0f}ms"
    except Exception as e:  # noqa: BLE001
        out["chat"] = f"❌ {describe_error(e)[:200]}"
    return out
