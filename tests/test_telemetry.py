from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from deadlock_coach.config import Settings
from deadlock_coach.telemetry import emit_event, read_recent_events, traced_operation


class TelemetryTests(unittest.TestCase):
    def test_emit_event_writes_jsonl_record(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            settings = Settings(project_root=Path(tmpdir))

            emit_event(settings, "chat.test", request_id="abc123", route="/api/adk/chat")

            lines = settings.telemetry_events_path.read_text(encoding="utf-8").strip().splitlines()
            payload = json.loads(lines[-1])
            self.assertEqual(payload["event_type"], "chat.test")
            self.assertEqual(payload["request_id"], "abc123")

    def test_traced_operation_writes_finish_event(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            settings = Settings(project_root=Path(tmpdir))

            with traced_operation(settings, "api.post", request_id="req1", route="/api/chat") as trace:
                trace["status_code"] = 200
                trace["source"] = "adk_unavailable"

            lines = settings.telemetry_events_path.read_text(encoding="utf-8").strip().splitlines()
            payload = json.loads(lines[-1])
            self.assertEqual(payload["event_type"], "api.post.finish")
            self.assertEqual(payload["status_code"], 200)
            self.assertEqual(payload["source"], "adk_unavailable")

    def test_read_recent_events_returns_tail_slice(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            settings = Settings(project_root=Path(tmpdir))

            emit_event(settings, "chat.one", request_id="r1")
            emit_event(settings, "chat.two", request_id="r2")
            emit_event(settings, "chat.three", request_id="r3")

            events = read_recent_events(settings, limit=2)

            self.assertEqual([event["event_type"] for event in events], ["chat.two", "chat.three"])


if __name__ == "__main__":
    unittest.main()
