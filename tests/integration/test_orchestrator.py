from __future__ import annotations

import pytest

from grok_proxy.backends.base import BackendEvent
from grok_proxy.backends.fake import FakeBackend
from grok_proxy.permissions.broker import PermissionBroker
from grok_proxy.runtime.commands import CreateResponseCommand, GrokExtensions
from grok_proxy.runtime.orchestrator import ResponseOrchestrator
from grok_proxy.storage.database import open_database
from grok_proxy.workspace.manager import WorkspaceManager


@pytest.mark.asyncio
async def test_orchestrator_fake_complete(tmp_path):
    db = open_database(tmp_path / "o.db")
    fake = FakeBackend(
        script=[
            BackendEvent(type="text", data={"text": "ok"}),
            BackendEvent(
                type="end",
                data={
                    "session_id": "s1",
                    "usage": {"input_tokens": 1, "output_tokens": 1, "total_tokens": 2},
                    "text": "ok",
                },
            ),
        ]
    )
    orch = ResponseOrchestrator(
        db,
        fake,
        workspace=WorkspaceManager(),
        permissions=PermissionBroker(db),
    )
    rec = await orch.create(
        CreateResponseCommand(
            model="m",
            input_text="hi",
            x_grok=GrokExtensions(cwd=str(tmp_path), workspace_mode="read_only"),
            default_cwd=str(tmp_path),
        )
    )
    assert rec.status == "completed"
    assert rec.text == "ok"
    events = list(db.list_events(rec.id, after_sequence=0))
    types = [e.event_type for e in events]
    assert "response.created" in types
    assert "response.completed" in types
    # replay
    async for ev in orch.stream_events(rec.id, after_sequence=0):
        assert ev.sequence_number >= 1
    db.close()


@pytest.mark.asyncio
async def test_orchestrator_cancel(tmp_path):
    db = open_database(tmp_path / "c.db")
    fake = FakeBackend(
        script=[
            BackendEvent(type="text", data={"text": "a"}),
            BackendEvent(type="end", data={"text": "a"}),
        ],
        delay_sec=0.2,
    )
    orch = ResponseOrchestrator(db, fake, workspace=WorkspaceManager())
    rec = await orch.create(
        CreateResponseCommand(
            model="m",
            input_text="hi",
            background=True,
            x_grok=GrokExtensions(cwd=str(tmp_path)),
            default_cwd=str(tmp_path),
        )
    )
    cancelled = await orch.cancel(rec.id)
    assert cancelled.status in ("cancelled", "completed")
    # idempotent
    again = await orch.cancel(rec.id)
    assert again.status in ("cancelled", "completed")
    db.close()
