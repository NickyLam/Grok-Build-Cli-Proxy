from __future__ import annotations

import time

from grok_proxy.storage.database import open_database
from grok_proxy.storage.models import ResponseRecord


def test_response_and_events_persist(tmp_path):
    db = open_database(tmp_path / "t.db")
    rec = ResponseRecord(
        id="resp_1",
        status="queued",
        model="m",
        backend="fake",
        input_json={"input": "hi"},
        created_at=time.time(),
    )
    db.create_response(rec)
    e1 = db.append_event("resp_1", "response.created", {"id": "resp_1"})
    e2 = db.append_event("resp_1", "response.in_progress", {})
    assert e1.sequence_number == 1
    assert e2.sequence_number == 2
    events = db.list_events("resp_1", after_sequence=1)
    assert len(events) == 1
    assert events[0].event_type == "response.in_progress"
    got = db.get_response("resp_1")
    assert got is not None
    assert got.last_sequence_number == 2
    db.close()
