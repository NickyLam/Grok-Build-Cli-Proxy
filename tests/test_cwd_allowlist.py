from __future__ import annotations

from pathlib import Path

from grok_proxy.config import cwd_is_allowed, resolve_cwd


def test_empty_allowlist_allows_all(tmp_path: Path):
    assert cwd_is_allowed(tmp_path, []) is True


def test_allowlist_prefix(tmp_path: Path):
    allowed = tmp_path / "ok"
    allowed.mkdir()
    denied = tmp_path / "nope"
    denied.mkdir()
    assert cwd_is_allowed(allowed, [str(allowed)]) is True
    assert cwd_is_allowed(denied, [str(allowed)]) is False


def test_nested_under_prefix(tmp_path: Path):
    root = tmp_path / "projects"
    nested = root / "a" / "b"
    nested.mkdir(parents=True)
    assert cwd_is_allowed(nested, [str(root)]) is True


def test_resolve_cwd_absolute(tmp_path: Path):
    p = resolve_cwd(str(tmp_path))
    assert p.is_absolute()
