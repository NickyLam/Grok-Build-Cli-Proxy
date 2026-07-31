from __future__ import annotations

import pytest

from grok_proxy.api_keys import (
    PEPPER_META_KEY,
    ApiKeyStore,
    get_or_create_pepper,
    hash_api_key,
)
from grok_proxy.errors import ProxyError
from grok_proxy.scopes import ALL_SCOPES, DEFAULT_AGENT_SCOPES, Scope, has_scope
from grok_proxy.storage.database import open_database


def test_hash_stable():
    assert hash_api_key("gp_live_abc", pepper="p") == hash_api_key("gp_live_abc", pepper="p")
    assert hash_api_key("gp_live_abc", pepper="p") != hash_api_key("gp_live_abc", pepper="q")


def test_create_auth_revoke(tmp_path):
    db = open_database(tmp_path / "k.db")
    store = ApiKeyStore(db, pepper="test")
    rec = store.create(name="codex", scopes=list(DEFAULT_AGENT_SCOPES), test=True)
    assert rec.plaintext_once and rec.plaintext_once.startswith("gp_test_")
    assert store.authenticate(rec.plaintext_once) is not None
    assert store.authenticate("wrong") is None
    store.revoke(rec.id)
    assert store.authenticate(rec.plaintext_once) is None
    db.close()


def test_unknown_scope_rejected(tmp_path):
    db = open_database(tmp_path / "k2.db")
    store = ApiKeyStore(db)
    with pytest.raises(ProxyError) as ei:
        store.create(name="bad", scopes=["not:a:scope"])
    assert ei.value.code == "invalid_scope"
    db.close()


def test_has_scope():
    assert has_scope(ALL_SCOPES, Scope.ADMIN_KEYS.value)
    assert not has_scope(DEFAULT_AGENT_SCOPES, Scope.PERMISSION_APPROVE.value)
    assert has_scope(DEFAULT_AGENT_SCOPES, Scope.RESPONSE_CREATE.value)


def test_pepper_random_on_fresh_install(tmp_path):
    db = open_database(tmp_path / "p1.db")
    pepper = get_or_create_pepper(db, legacy_pepper="master-key-prefix")
    # Fresh install (no keys yet): pepper is random, not derived from master key
    assert pepper != "master-key-prefix"
    assert len(pepper) == 32  # token_hex(16)
    # Stable across restarts
    assert get_or_create_pepper(db, legacy_pepper="other") == pepper
    assert db.get_meta(PEPPER_META_KEY) == pepper
    db.close()


def test_pepper_keeps_legacy_when_keys_exist(tmp_path):
    """Existing scoped keys were hashed with api_key[:16]; upgrading must not break them."""
    db = open_database(tmp_path / "p2.db")
    legacy = "master-key-prefix"
    store = ApiKeyStore(db, pepper=legacy)
    rec = store.create(name="old", test=True)
    raw = rec.plaintext_once
    assert raw is not None

    # Simulate upgrade: meta table empty, keys already present
    pepper = get_or_create_pepper(db, legacy_pepper=legacy)
    assert pepper == legacy
    upgraded = ApiKeyStore(db, pepper=pepper)
    assert upgraded.authenticate(raw) is not None
    db.close()


def test_pepper_independent_of_master_key_change(tmp_path):
    db = open_database(tmp_path / "p3.db")
    pepper = get_or_create_pepper(db, legacy_pepper="first-master-key")
    store = ApiKeyStore(db, pepper=pepper)
    rec = store.create(name="agent", test=True)
    raw = rec.plaintext_once
    assert raw is not None

    # Master key rotation: pepper resolved again with a different legacy value
    pepper2 = get_or_create_pepper(db, legacy_pepper="second-master-key")
    assert pepper2 == pepper
    assert ApiKeyStore(db, pepper=pepper2).authenticate(raw) is not None
    db.close()
