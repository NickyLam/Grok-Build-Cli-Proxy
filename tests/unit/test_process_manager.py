from __future__ import annotations

import asyncio
import json
import signal
from pathlib import Path

from grok_proxy.runtime.process_manager import ProcessManager, terminate_process_tree


async def _spawn_sleep() -> asyncio.subprocess.Process:
    return await asyncio.create_subprocess_exec(
        "sleep",
        "30",
        start_new_session=True,
    )


async def _cleanup(proc: asyncio.subprocess.Process) -> None:
    if proc.returncode is None:
        await terminate_process_tree(proc, force=True)


async def test_terminate_process_tree_kills_child_quickly():
    proc = await _spawn_sleep()
    try:
        await asyncio.wait_for(terminate_process_tree(proc), timeout=8)
        assert proc.returncode is not None
        # SIGTERM to the process group -> negative signal exit
        assert proc.returncode == -signal.SIGTERM
    finally:
        await _cleanup(proc)


async def test_register_and_unregister_persist_pid_state(tmp_path: Path):
    state_path = tmp_path / "pids.json"
    pm = ProcessManager(state_path=state_path)
    proc = await _spawn_sleep()
    try:
        await pm.register("resp_1", proc, model="grok-code")

        data = json.loads(state_path.read_text(encoding="utf-8"))
        assert len(data["pids"]) == 1
        row = data["pids"][0]
        assert row["response_id"] == "resp_1"
        assert row["pid"] == proc.pid
        assert row["pgid"] == proc.pid
        assert row["meta"] == {"model": "grok-code"}

        await pm.unregister("resp_1")
        data = json.loads(state_path.read_text(encoding="utf-8"))
        assert data["pids"] == []
    finally:
        await _cleanup(proc)


async def test_stop_terminates_and_removes_tracked_process(tmp_path: Path):
    pm = ProcessManager(state_path=tmp_path / "pids.json")
    proc = await _spawn_sleep()
    try:
        await pm.register("resp_stop", proc)
        await asyncio.wait_for(pm.stop("resp_stop"), timeout=8)
        assert proc.returncode is not None
        data = json.loads(pm.state_path.read_text(encoding="utf-8"))
        assert data["pids"] == []
    finally:
        await _cleanup(proc)


def test_reclaim_stale_pids_ignores_dead_pid_and_clears_file(tmp_path: Path):
    state_path = tmp_path / "pids.json"
    state_path.write_text(
        json.dumps({"pids": [{"response_id": "old", "pid": 99999999, "pgid": 99999999}]}),
        encoding="utf-8",
    )
    pm = ProcessManager(state_path=state_path)

    assert pm.reclaim_stale_pids() == 0

    data = json.loads(state_path.read_text(encoding="utf-8"))
    assert data["pids"] == []


def test_reclaim_stale_pids_missing_or_invalid_file(tmp_path: Path):
    pm = ProcessManager(state_path=tmp_path / "missing.json")
    assert pm.reclaim_stale_pids() == 0

    bad = tmp_path / "bad.json"
    bad.write_text("not json", encoding="utf-8")
    pm2 = ProcessManager(state_path=bad)
    assert pm2.reclaim_stale_pids() == 0


async def test_reclaim_stale_pids_terminates_live_process(tmp_path: Path):
    state_path = tmp_path / "pids.json"
    proc = await _spawn_sleep()
    try:
        state_path.write_text(
            json.dumps(
                {"pids": [{"response_id": "stale", "pid": proc.pid, "pgid": proc.pid}]}
            ),
            encoding="utf-8",
        )
        pm = ProcessManager(state_path=state_path)

        assert pm.reclaim_stale_pids() == 1

        await asyncio.wait_for(proc.wait(), timeout=8)
        assert proc.returncode == -signal.SIGTERM
        data = json.loads(state_path.read_text(encoding="utf-8"))
        assert data["pids"] == []
    finally:
        await _cleanup(proc)
