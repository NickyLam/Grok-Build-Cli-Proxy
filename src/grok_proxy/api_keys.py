from __future__ import annotations

import hashlib
import hmac
import secrets
import time
from dataclasses import dataclass, field
from typing import Any, Literal

from grok_proxy.errors import ProxyError
from grok_proxy.scopes import ALL_SCOPES, DEFAULT_AGENT_SCOPES
from grok_proxy.storage.database import Database, new_id

KeyPrefix = Literal["gp_live_", "gp_test_"]

# Meta key under which the hash pepper is persisted in the database.
PEPPER_META_KEY = "api_key_pepper"


def hash_api_key(raw_key: str, *, pepper: str = "") -> str:
    """Store only a keyed hash of the secret (never plaintext)."""
    material = f"{pepper}{raw_key}".encode()
    return hashlib.sha256(material).hexdigest()


# Pre-computed hash of an unguessable value; compared against candidate hashes
# on lookup misses so the miss path does similar work to the hit path.
_DUMMY_HASH = hash_api_key(secrets.token_urlsafe(32))


def get_or_create_pepper(db: Database, *, legacy_pepper: str = "") -> str:
    """Resolve the hash pepper from the database, creating one if missing.

    Historically the pepper was derived from the master key (api_key[:16]);
    if scoped keys already exist we keep that legacy pepper so their hashes
    stay valid. Fresh installs get an independent random pepper.
    """
    existing = db.get_meta(PEPPER_META_KEY)
    if existing is not None:
        return existing
    if legacy_pepper and db.list_api_keys():
        pepper = legacy_pepper
    else:
        pepper = secrets.token_hex(16)
    db.set_meta(PEPPER_META_KEY, pepper)
    return pepper


def generate_api_key(*, test: bool = False) -> str:
    prefix = "gp_test_" if test else "gp_live_"
    return prefix + secrets.token_urlsafe(32)


@dataclass
class ApiKeyRecord:
    id: str
    key_hash: str
    name: str
    scopes: list[str] = field(default_factory=list)
    workspace_allowlist: list[str] = field(default_factory=list)
    max_concurrent: int | None = None
    max_runtime_sec: int | None = None
    workspace_mode: str | None = None
    enabled: bool = True
    created_at: float = 0.0
    last_used_at: float | None = None
    revoked_at: float | None = None
    # Only set on create response once
    plaintext_once: str | None = None


@dataclass
class AuthContext:
    """Resolved caller after authentication."""

    actor_type: str  # master | api_key
    actor_id: str
    scopes: frozenset[str]
    workspace_allowlist: list[str] = field(default_factory=list)
    max_concurrent: int | None = None
    max_runtime_sec: int | None = None
    workspace_mode: str | None = None
    key_id: str | None = None
    key_name: str | None = None
    is_master: bool = False

    def require_scopes(self, *required: str) -> None:
        missing = [s for s in required if s not in self.scopes]
        if missing:
            raise ProxyError(
                f"Missing required scope(s): {', '.join(missing)}",
                status_code=403,
                code="insufficient_scope",
                details={"missing": missing, "granted": sorted(self.scopes)},
            )

    def check_workspace(self, cwd: str) -> None:
        from grok_proxy.config import cwd_is_allowed

        # Empty allowlist on scoped key means inherit server-level only (no extra restriction here)
        if not self.workspace_allowlist:
            return
        if not cwd_is_allowed(cwd, self.workspace_allowlist):
            raise ProxyError(
                f"cwd not allowed for this API key: {cwd}",
                status_code=403,
                code="key_cwd_forbidden",
            )


class ApiKeyStore:
    def __init__(self, db: Database, *, pepper: str = "") -> None:
        self.db = db
        self.pepper = pepper

    def create(
        self,
        *,
        name: str,
        scopes: list[str] | None = None,
        workspace_allowlist: list[str] | None = None,
        max_concurrent: int | None = None,
        max_runtime_sec: int | None = None,
        workspace_mode: str | None = None,
        test: bool = False,
    ) -> ApiKeyRecord:
        raw = generate_api_key(test=test)
        key_hash = hash_api_key(raw, pepper=self.pepper)
        now = time.time()
        rec = ApiKeyRecord(
            id=new_id("key"),
            key_hash=key_hash,
            name=name,
            scopes=sorted(set(scopes or list(DEFAULT_AGENT_SCOPES))),
            workspace_allowlist=list(workspace_allowlist or []),
            max_concurrent=max_concurrent,
            max_runtime_sec=max_runtime_sec,
            workspace_mode=workspace_mode,
            enabled=True,
            created_at=now,
            plaintext_once=raw,
        )
        # Validate scopes
        unknown = [s for s in rec.scopes if s not in ALL_SCOPES]
        if unknown:
            raise ProxyError(
                f"Unknown scopes: {unknown}",
                status_code=400,
                code="invalid_scope",
            )
        self.db.create_api_key(rec)
        self.db.insert_audit(
            actor_type="system",
            actor_id="api_key_store",
            action="api_key.created",
            resource_type="api_key",
            resource_id=rec.id,
            payload={"name": name, "scopes": rec.scopes},
        )
        return rec

    def list_keys(self) -> list[ApiKeyRecord]:
        return self.db.list_api_keys()

    def get(self, key_id: str) -> ApiKeyRecord:
        rec = self.db.get_api_key(key_id)
        if rec is None:
            raise ProxyError("API key not found", status_code=404, code="key_not_found")
        return rec

    def revoke(self, key_id: str) -> ApiKeyRecord:
        rec = self.get(key_id)
        if not rec.enabled or rec.revoked_at is not None:
            return rec
        rec.enabled = False
        rec.revoked_at = time.time()
        self.db.update_api_key(rec)
        self.db.insert_audit(
            actor_type="system",
            actor_id="api_key_store",
            action="api_key.revoked",
            resource_type="api_key",
            resource_id=rec.id,
            payload={},
        )
        return rec

    def set_enabled(self, key_id: str, enabled: bool) -> ApiKeyRecord:
        rec = self.get(key_id)
        rec.enabled = enabled
        if enabled:
            rec.revoked_at = None
        self.db.update_api_key(rec)
        return rec

    def authenticate(self, raw_token: str) -> ApiKeyRecord | None:
        key_hash = hash_api_key(raw_token, pepper=self.pepper)
        rec = self.db.get_api_key_by_hash(key_hash)
        if rec is None:
            # Equalize work on the miss path (compare against a fixed dummy hash)
            hmac.compare_digest(key_hash, _DUMMY_HASH)
            return None
        if not rec.enabled or rec.revoked_at is not None:
            return None
        self.db.touch_api_key(rec.id)
        return rec

    def public_view(self, rec: ApiKeyRecord) -> dict[str, Any]:
        return {
            "id": rec.id,
            "name": rec.name,
            "scopes": rec.scopes,
            "workspace_allowlist": rec.workspace_allowlist,
            "max_concurrent": rec.max_concurrent,
            "max_runtime_sec": rec.max_runtime_sec,
            "workspace_mode": rec.workspace_mode,
            "enabled": rec.enabled,
            "created_at": rec.created_at,
            "last_used_at": rec.last_used_at,
            "revoked_at": rec.revoked_at,
            # never include hash or plaintext
        }
