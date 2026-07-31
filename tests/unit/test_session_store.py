from __future__ import annotations

from grok_proxy.errors import ProxyError
from grok_proxy.session_store import SessionStore
from grok_proxy.storage.database import open_database


def test_memory_only_store_still_works(tmp_path):
    store = SessionStore()
    store.remember("s1", str(tmp_path))
    rec = store.get("s1")
    assert rec is not None and rec.cwd == str(tmp_path)
    assert store.get("unknown") is None


def test_session_survives_restart(tmp_path):
    """strict_session_cwd must keep working after a proxy restart (SQLite-backed)."""
    db = open_database(tmp_path / "s.db")
    store = SessionStore(db)
    store.remember("sess-1", str(tmp_path))

    # Simulate restart: fresh store instance over the same database
    store2 = SessionStore(db)
    rec = store2.get("sess-1")
    assert rec is not None
    assert rec.cwd == str(tmp_path)

    # Same cwd passes the strict check
    store2.check_cwd("sess-1", str(tmp_path), strict=True)

    # A different cwd is rejected even after restart
    other = tmp_path / "elsewhere"
    other.mkdir()
    try:
        store2.check_cwd("sess-1", str(other), strict=True)
        raise AssertionError("expected session_cwd_mismatch")
    except ProxyError as e:
        assert e.code == "session_cwd_mismatch"
    db.close()


def test_remember_updates_existing_session(tmp_path):
    db = open_database(tmp_path / "s2.db")
    store = SessionStore(db)
    first = tmp_path / "a"
    second = tmp_path / "b"
    first.mkdir()
    second.mkdir()
    store.remember("sess-2", str(first))
    store.remember("sess-2", str(second))

    fresh = SessionStore(db)
    rec = fresh.get("sess-2")
    assert rec is not None and rec.cwd == str(second)
    db.close()


def test_unknown_session_allowed_in_strict_mode(tmp_path):
    db = open_database(tmp_path / "s3.db")
    store = SessionStore(db)
    # Sessions created outside the proxy are let through (Grok validates them)
    store.check_cwd("never-seen", str(tmp_path), strict=True)
    db.close()
