from __future__ import annotations

from pathlib import Path

import pytest

from grok_proxy.errors import ProxyError
from grok_proxy.workspace.manager import WorkspaceManager


def test_allowlist_and_symlink_resolve(tmp_path: Path):
    allowed = tmp_path / "ok"
    allowed.mkdir()
    outside = tmp_path / "nope"
    outside.mkdir()
    wm = WorkspaceManager(allowlist=[str(allowed)], allow_in_place=False)
    alloc = wm.allocate(str(allowed), mode="read_only", response_id="r1")
    assert alloc.run_cwd == str(allowed.resolve())
    with pytest.raises(ProxyError) as ei:
        wm.allocate(str(outside), mode="read_only", response_id="r2")
    assert ei.value.code == "cwd_forbidden"


def test_in_place_forbidden_by_default(tmp_path: Path):
    wm = WorkspaceManager(allow_in_place=False)
    with pytest.raises(ProxyError) as ei:
        wm.allocate(str(tmp_path), mode="in_place", response_id="r1")
    assert ei.value.code == "in_place_forbidden"


def test_write_lock_conflict(tmp_path: Path):
    wm = WorkspaceManager(allow_in_place=True)
    a1 = wm.allocate(str(tmp_path), mode="in_place", response_id="r1")
    with pytest.raises(ProxyError) as ei:
        wm.allocate(str(tmp_path), mode="in_place", response_id="r2")
    assert ei.value.code == "workspace_locked"
    wm.release(a1, "r1")
    a2 = wm.allocate(str(tmp_path), mode="in_place", response_id="r2")
    wm.release(a2, "r2")
