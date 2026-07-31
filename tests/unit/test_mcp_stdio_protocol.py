from __future__ import annotations

import pytest

from grok_proxy.backends.base import BackendEvent
from grok_proxy.backends.fake import FakeBackend
from grok_proxy.mcp.server import McpToolRouter
from grok_proxy.permissions.broker import PermissionBroker
from grok_proxy.runtime.orchestrator import ResponseOrchestrator
from grok_proxy.storage.database import open_database
from grok_proxy.workspace.manager import WorkspaceManager


@pytest.mark.asyncio
async def test_mcp_stdio_list_and_status(tmp_path, monkeypatch):
    db = open_database(tmp_path / "m.db")
    fake = FakeBackend(
        script=[
            BackendEvent(type="text", data={"text": "ok"}),
            BackendEvent(type="end", data={"text": "ok", "session_id": "s"}),
        ]
    )
    orch = ResponseOrchestrator(
        db,
        fake,
        workspace=WorkspaceManager(),
        permissions=PermissionBroker(db),
    )
    router = McpToolRouter(orch, default_model="m")

    # list tools
    tools = router.list_tools()
    assert any(t["name"] == "grok_consult" for t in tools)

    # call consult
    result = await router.call_tool(
        "grok_consult",
        {"prompt": "x", "cwd": str(tmp_path)},
    )
    assert result.get("status") == "completed" or result.get("id") or result.get("x_grok")
    db.close()
