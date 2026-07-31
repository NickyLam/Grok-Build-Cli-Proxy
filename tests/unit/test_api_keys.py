from __future__ import annotations

import pytest

from grok_proxy.api_keys import ApiKeyStore, hash_api_key
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
