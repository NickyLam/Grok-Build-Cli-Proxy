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
async def test_mcp_consult_and_status(tmp_path):
    db = open_database(tmp_path / "m.db")
    fake = FakeBackend(
        script=[
            BackendEvent(type="text", data={"text": "review ok"}),
            BackendEvent(type="end", data={"text": "review ok", "session_id": "s"}),
        ]
    )
    orch = ResponseOrchestrator(
        db,
        fake,
        workspace=WorkspaceManager(),
        permissions=PermissionBroker(db),
    )
    router = McpToolRouter(orch, default_model="m")
    tools = {t["name"] for t in router.list_tools()}
    assert "grok_consult" in tools
    assert "grok_delegate" in tools
    result = await router.call_tool(
        "grok_consult",
        {"prompt": "analyze", "cwd": str(tmp_path)},
    )
    assert result.get("status") == "completed" or result.get("x_grok", {}).get("text") == "review ok"
    rid = result.get("id") or result.get("response_id")
    if not rid and "response" in result:
        rid = result["response"]["id"]
    assert rid
    status = await router.call_tool("grok_status", {"response_id": rid})
    assert status["id"] == rid
    db.close()
