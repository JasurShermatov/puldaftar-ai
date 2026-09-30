"""Barcha sozlamalar .env dan o'qiladi. Kodda hech qanday secret yo'q."""
from __future__ import annotations

from functools import lru_cache

from pydantic import Field, field_validator, model_validator
from typing import Annotated

from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    # --- App ---
    app_env: str = "production"               # development | production
    app_name: str = "Hisobchi AI"
    public_base_url: str = "https://example.com"   # HTTPS domen (mini app + webhook)
    log_level: str = "INFO"

    # --- Telegram ---
    bot_token: str = ""
    bot_mode: str = "webhook"                 # webhook | polling
    webhook_secret: str = ""                  # X-Telegram-Bot-Api-Secret-Token
    superadmin_ids: Annotated[list[int], NoDecode] = Field(default_factory=list)   # "123,456"
    init_data_max_age_sec: int = 86400

    # --- Database ---
    # URL berilmasa quyidagi qismlardan avtomatik yig'iladi
    database_url: str = ""                    # RLS rolida (app)
    migration_database_url: str = ""          # jadval egasi (migratsiya)
    db_host: str = "db"
    db_port: int = 5432
    postgres_db: str = "hisobchi"
    postgres_user: str = "hisobchi_owner"
    postgres_password: str = ""
    db_app_role: str = "hisobchi_app"
    db_app_password: str = ""
    db_pool_min: int = 2
    db_pool_max: int = 20

    # --- Redis ---
    redis_url: str = ""                       # bo'sh bo'lsa in-memory

    # --- Security ---
    data_encryption_key: str = ""             # 32 bayt, base64 (python -c "import os,base64;print(base64.b64encode(os.urandom(32)).decode())")
    hash_secret: str = ""                     # HMAC uchun ixtiyoriy uzun random satr

    # --- OpenAI ---
    openai_api_key: str = ""
    openai_base_url: str = ""
    openai_parser_model: str = "gpt-4o-mini"
    openai_insight_model: str = "gpt-4o-mini"
    openai_stt_model: str = "gpt-4o-transcribe"   # yoki whisper-1
    openai_timeout_sec: float = 25.0

    # --- Limits ---
    rate_limit_per_minute: int = 30
    max_text_len: int = 1000
    max_voice_seconds: int = 120
    max_voice_bytes: int = 10 * 1024 * 1024

    @field_validator("superadmin_ids", mode="before")
    @classmethod
    def _split_ids(cls, v):
        if isinstance(v, str):
            return [int(x) for x in v.replace(" ", "").split(",") if x]
        if isinstance(v, int):
            return [v]
        return v

    @model_validator(mode="after")
    def _build_urls(self):
        from urllib.parse import quote
        if not self.database_url:
            self.database_url = (f"postgresql://{self.db_app_role}:{quote(self.db_app_password)}@"
                                 f"{self.db_host}:{self.db_port}/{self.postgres_db}")
        if not self.migration_database_url:
            self.migration_database_url = (f"postgresql://{self.postgres_user}:{quote(self.postgres_password)}@"
                                           f"{self.db_host}:{self.db_port}/{self.postgres_db}")
        return self

    @property
    def is_dev(self) -> bool:
        return self.app_env == "development"

    @property
    def ai_enabled(self) -> bool:
        return bool(self.openai_api_key)


@lru_cache
def get_settings() -> Settings:
    return Settings()
