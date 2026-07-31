from __future__ import annotations

import logging
import os
import shutil
import subprocess
import time
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Literal

from grok_proxy.config import cwd_is_allowed, resolve_cwd
from grok_proxy.errors import ProxyError

logger = logging.getLogger(__name__)

WorkspaceMode = Literal["read_only", "in_place", "worktree", "temporary_copy"]


@dataclass
class WorkspaceAllocation:
    source_cwd: str
    run_cwd: str
    mode: WorkspaceMode
    worktree_path: str | None = None
    branch: str | None = None
    lock_key: str | None = None
    metadata: dict = field(default_factory=dict)


class WorkspaceManager:
    def __init__(
        self,
        *,
        allowlist: list[str] | None = None,
        allow_in_place: bool = False,
        default_mode: WorkspaceMode = "read_only",
        worktree_root: str | Path | None = None,
    ) -> None:
        self.allowlist = allowlist or []
        self.allow_in_place = allow_in_place
        self.default_mode = default_mode
        self.worktree_root = Path(worktree_root) if worktree_root else None
        # workspace_key -> exclusive response_id
        self._write_locks: dict[str, str] = {}
        self._read_locks: dict[str, set[str]] = {}

    def resolve_and_check(self, cwd: str) -> Path:
        path = resolve_cwd(cwd)
        if not path.exists() or not path.is_dir():
            raise ProxyError(
                f"cwd does not exist or is not a directory: {path}",
                status_code=400,
                code="invalid_cwd",
            )
        # Prevent symlink escape relative to allowlist by resolving real path
        real = Path(os.path.realpath(path))
        if not cwd_is_allowed(real, self.allowlist):
            raise ProxyError(
                f"cwd not allowed by GROK_PROXY_CWD_ALLOWLIST: {real}",
                status_code=403,
                code="cwd_forbidden",
            )
        return real

    def allocate(
        self,
        cwd: str,
        *,
        mode: WorkspaceMode | None,
        response_id: str,
        worktree: str | bool | None = None,
    ) -> WorkspaceAllocation:
        source = self.resolve_and_check(cwd)
        resolved_mode: WorkspaceMode = mode or self.default_mode
        if worktree is True or isinstance(worktree, str):
            resolved_mode = "worktree"

        if resolved_mode == "in_place" and not self.allow_in_place:
            raise ProxyError(
                "in_place workspace mode is disabled (set GROK_PROXY_ALLOW_IN_PLACE=1)",
                status_code=403,
                code="in_place_forbidden",
            )

        key = str(source)
        if resolved_mode in ("in_place", "worktree", "temporary_copy"):
            self._acquire_write_lock(key, response_id)
        else:
            self._acquire_read_lock(key, response_id)

        if resolved_mode == "worktree":
            wt = self._create_worktree(source, response_id=response_id, name=worktree)
            return WorkspaceAllocation(
                source_cwd=str(source),
                run_cwd=str(wt),
                mode="worktree",
                worktree_path=str(wt),
                branch=f"grok-proxy/{response_id[:12]}",
                lock_key=key,
            )

        if resolved_mode == "temporary_copy":
            dest = self._temp_copy(source, response_id)
            return WorkspaceAllocation(
                source_cwd=str(source),
                run_cwd=str(dest),
                mode="temporary_copy",
                lock_key=key,
            )

        return WorkspaceAllocation(
            source_cwd=str(source),
            run_cwd=str(source),
            mode=resolved_mode,
            lock_key=key,
        )

    def release(self, allocation: WorkspaceAllocation, response_id: str) -> None:
        key = allocation.lock_key
        if not key:
            return
        if allocation.mode == "read_only":
            holders = self._read_locks.get(key)
            if holders:
                holders.discard(response_id)
                if not holders:
                    self._read_locks.pop(key, None)
        else:
            if self._write_locks.get(key) == response_id:
                self._write_locks.pop(key, None)

    def cleanup(self, allocation: WorkspaceAllocation, *, keep_on_failure: bool = False) -> None:
        if allocation.mode == "worktree" and allocation.worktree_path:
            if keep_on_failure:
                return
            self._remove_worktree(allocation.source_cwd, allocation.worktree_path)
        if allocation.mode == "temporary_copy" and allocation.run_cwd != allocation.source_cwd:
            shutil.rmtree(allocation.run_cwd, ignore_errors=True)

    def collect_diff(self, allocation: WorkspaceAllocation) -> str:
        if allocation.mode != "worktree" or not allocation.worktree_path:
            return ""
        try:
            proc = subprocess.run(
                ["git", "-C", allocation.worktree_path, "diff", "--stat"],
                check=False,
                capture_output=True,
                text=True,
                timeout=30,
            )
            return (proc.stdout or "") + (proc.stderr or "")
        except (OSError, subprocess.SubprocessError) as e:
            logger.warning("diff failed: %s", e)
            return ""

    def _acquire_write_lock(self, key: str, response_id: str) -> None:
        if key in self._write_locks and self._write_locks[key] != response_id:
            raise ProxyError(
                f"workspace write lock held by {self._write_locks[key]}",
                status_code=409,
                code="workspace_locked",
            )
        if self._read_locks.get(key):
            raise ProxyError(
                "workspace has active read locks",
                status_code=409,
                code="workspace_locked",
            )
        self._write_locks[key] = response_id

    def _acquire_read_lock(self, key: str, response_id: str) -> None:
        if key in self._write_locks:
            raise ProxyError(
                f"workspace write lock held by {self._write_locks[key]}",
                status_code=409,
                code="workspace_locked",
            )
        self._read_locks.setdefault(key, set()).add(response_id)

    def _create_worktree(
        self,
        source: Path,
        *,
        response_id: str,
        name: str | bool | None,
    ) -> Path:
        if not (source / ".git").exists() and not self._is_git_repo(source):
            raise ProxyError(
                f"worktree requires a git repository: {source}",
                status_code=400,
                code="not_a_git_repo",
            )
        root = self.worktree_root or (source / ".grok-proxy-worktrees")
        root.mkdir(parents=True, exist_ok=True)
        branch = f"grok-proxy/{response_id[:12]}-{int(time.time())}"
        if isinstance(name, str) and name:
            dest = Path(name)
            if not dest.is_absolute():
                dest = root / name
        else:
            dest = root / f"wt-{uuid.uuid4().hex[:10]}"
        dest.parent.mkdir(parents=True, exist_ok=True)
        proc = subprocess.run(
            ["git", "-C", str(source), "worktree", "add", "-b", branch, str(dest)],
            check=False,
            capture_output=True,
            text=True,
        )
        if proc.returncode != 0:
            raise ProxyError(
                f"failed to create git worktree: {proc.stderr or proc.stdout}",
                status_code=500,
                code="worktree_create_failed",
            )
        return dest.resolve()

    @staticmethod
    def _is_git_repo(path: Path) -> bool:
        proc = subprocess.run(
            ["git", "-C", str(path), "rev-parse", "--is-inside-work-tree"],
            check=False,
            capture_output=True,
            text=True,
        )
        return proc.returncode == 0 and "true" in (proc.stdout or "").lower()

    @staticmethod
    def _remove_worktree(source_cwd: str, worktree_path: str) -> None:
        subprocess.run(
            ["git", "-C", source_cwd, "worktree", "remove", "--force", worktree_path],
            check=False,
            capture_output=True,
            text=True,
        )
        shutil.rmtree(worktree_path, ignore_errors=True)

    @staticmethod
    def _temp_copy(source: Path, response_id: str) -> Path:
        dest = Path(os.environ.get("TMPDIR", "/tmp")) / f"grok-proxy-copy-{response_id[:12]}"
        if dest.exists():
            shutil.rmtree(dest, ignore_errors=True)
        shutil.copytree(source, dest, dirs_exist_ok=False)
        return dest
