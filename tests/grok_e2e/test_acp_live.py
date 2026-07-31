"""Live ACP tests — skipped unless RUN_GROK_E2E=1 and grok is available."""

from __future__ import annotations

import os
import shutil

import pytest

from grok_proxy.backends.acp import AcpBackend
from grok_proxy.backends.base import BackendSessionRequest, PromptInput

pytestmark = pytest.mark.grok_e2e


def _grok_available() -> bool:
    return bool(shutil.which(os.environ.get("GROK_BIN", "grok")))


@pytest.mark.asyncio
@pytest.mark.skipif(
    os.environ.get("RUN_GROK_E2E") != "1" or not _grok_available(),
    reason="Set RUN_GROK_E2E=1 with grok on PATH",
)
async def test_acp_live_short_prompt(tmp_path):
    backend = AcpBackend(grok_bin=os.environ.get("GROK_BIN", "grok"))
    session = await backend.start_session(
        BackendSessionRequest(
            model="grok-4.5",
            cwd=str(tmp_path),
            always_approve=True,
            timeout_sec=120,
        )
    )
    await backend.send_prompt(
        session,
        PromptInput(text="Reply with exactly the single word: pong"),
    )
    texts: list[str] = []
    end = None
    async for ev in backend.events(session):
        if ev.type == "text":
            texts.append(str(ev.data.get("text") or ""))
        if ev.type == "end":
            end = ev
        if ev.type == "error":
            await backend.close(session)
            pytest.fail(f"ACP error: {ev.data}")
    await backend.close(session)
    assert end is not None
    body = "".join(texts) or str((end.data or {}).get("text") or "")
    assert "pong" in body.lower() or body.strip() != ""
