from __future__ import annotations

import os
from functools import lru_cache
from pathlib import Path

from pydantic import AliasChoices, Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


def _split_allowlist(value: str | list[str] | None) -> list[str]:
    if value is None:
        return []
    if isinstance(value, list):
        parts = value
    else:
        raw = value.replace(":", ",")
        parts = [p.strip() for p in raw.split(",") if p.strip()]
    return parts


def _alias(*names: str) -> AliasChoices:
    return AliasChoices(*names)


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        populate_by_name=True,
    )

    api_key: str = Field(
        default="",
        validation_alias=_alias("GROK_PROXY_API_KEY", "api_key"),
    )
    host: str = Field(
        default="127.0.0.1",
        validation_alias=_alias("GROK_PROXY_HOST", "host"),
    )
    port: int = Field(
        default=8787,
        validation_alias=_alias("GROK_PROXY_PORT", "port"),
    )
    grok_bin: str = Field(
        default="grok",
        validation_alias=_alias("GROK_BIN", "grok_bin"),
    )
    default_cwd: str = Field(
        default_factory=lambda: str(Path.cwd()),
        validation_alias=_alias("GROK_PROXY_DEFAULT_CWD", "default_cwd"),
    )
    cwd_allowlist: list[str] = Field(
        default_factory=list,
        validation_alias=_alias("GROK_PROXY_CWD_ALLOWLIST", "cwd_allowlist"),
    )
    max_concurrent: int = Field(
        default=2,
        validation_alias=_alias("GROK_PROXY_MAX_CONCURRENT", "max_concurrent"),
    )
    default_timeout_sec: int = Field(
        default=600,
        validation_alias=_alias("GROK_PROXY_DEFAULT_TIMEOUT_SEC", "default_timeout_sec"),
    )
    # Empty / "auto" / "grok-build" → resolved from `grok models` / models_cache at bootstrap
    default_model: str = Field(
        default="auto",
        validation_alias=_alias("GROK_PROXY_DEFAULT_MODEL", "default_model"),
    )
    always_approve: bool = Field(
        default=True,
        validation_alias=_alias("GROK_PROXY_ALWAYS_APPROVE", "always_approve"),
    )
    strict_session_cwd: bool = Field(
        default=True,
        validation_alias=_alias("GROK_PROXY_STRICT_SESSION_CWD", "strict_session_cwd"),
    )
    # Comma-separated model ids advertised on GET /v1/models (empty = auto-detect)
    models: str = Field(
        default="",
        validation_alias=_alias("GROK_PROXY_MODELS", "models"),
    )

    @field_validator("cwd_allowlist", mode="before")
    @classmethod
    def parse_allowlist(cls, v: object) -> list[str]:
        if v is None or v == "":
            return []
        if isinstance(v, list):
            return [str(x) for x in v]
        return _split_allowlist(str(v))

    def model_ids(self) -> list[str]:
        ids = [m.strip() for m in self.models.split(",") if m.strip()]
        return ids or [self.default_model]

    def require_api_key(self) -> None:
        """Legacy check. Prefer bootstrap.ensure via bootstrap_settings (auto-generates)."""
        if not self.api_key.strip():
            raise RuntimeError(
                "GROK_PROXY_API_KEY is empty. "
                "Start via `grok-proxy` so a key is auto-generated, "
                "or set GROK_PROXY_API_KEY / rely on ~/.grok-proxy/api_key."
            )


@lru_cache
def get_settings() -> Settings:
    return Settings()


def clear_settings_cache() -> None:
    get_settings.cache_clear()


def resolve_cwd(path: str) -> Path:
    """Resolve to an absolute real path (follows symlinks)."""
    return Path(path).expanduser().resolve(strict=False)


def cwd_is_allowed(cwd: str | Path, allowlist: list[str]) -> bool:
    if not allowlist:
        return True
    target = resolve_cwd(str(cwd))
    for prefix in allowlist:
        base = resolve_cwd(prefix)
        try:
            target.relative_to(base)
            return True
        except ValueError:
            continue
    return False
