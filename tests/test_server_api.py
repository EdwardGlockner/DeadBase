from __future__ import annotations

import sys
import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from deadlock_coach.adk_chat import AdkChatUnavailableError
from deadlock_coach.api_models import TelemetryEventsResponse
from deadlock_coach.coach_service import parse_context
from deadlock_coach.config import Settings
from deadlock_coach.server import _build_adk_reply, _resolve_dev_runtime_settings
from deadlock_coach.storage import initialize_workspace, normalize_match_history, save_json_snapshot
from deadlock_coach.telemetry import emit_event


class ServerApiTests(unittest.TestCase):
    def test_adk_route_returns_explicit_unavailable_reply(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            settings = Settings(project_root=Path(tmpdir))
            initialize_workspace(settings)

            match_payload = [
                {
                    "match_id": 2001,
                    "hero_id": 1,
                    "hero_level": 24,
                    "start_time": 1783288584,
                    "game_mode": 1,
                    "match_mode": 4,
                    "player_team": 0,
                    "player_kills": 9,
                    "player_deaths": 8,
                    "player_assists": 11,
                    "denies": 7,
                    "net_worth": 40500,
                    "last_hits": 220,
                    "team_abandoned": False,
                    "abandoned_time_s": None,
                    "match_duration_s": 2200,
                    "match_result": 0,
                    "won": False,
                }
            ]
            match_snapshot = save_json_snapshot(
                settings,
                "deadlock_api",
                "players",
                "500-match-history",
                "https://api.deadlock-api.com/v1/players/500/match-history",
                match_payload,
            )
            normalize_match_history(settings, match_snapshot, 500, match_payload)

            context = parse_context({"account_id": 500, "player_label": "EEE", "window_matches": 10})
            history = [{"role": "user", "text": "Which hero in my pool is most reliable?"}]

            with patch("deadlock_coach.server.run_adk_chat", side_effect=AdkChatUnavailableError("vpn dropped")):
                reply = _build_adk_reply(
                    settings,
                    message="why?",
                    context=context,
                    session_id="demo-session",
                    user_id="local-user",
                    history=history,
                    runtime_settings=None,
                )

            self.assertEqual(reply["source"], "adk_unavailable")
            self.assertEqual(reply["session_id"], "demo-session")
            self.assertEqual(reply["unavailable_reason"], "vpn dropped")
            self.assertEqual(reply["insight"], "Coach unavailable")
            self.assertIn("instruction-driven coach is unavailable", reply["reply"])
            self.assertEqual(reply["summary"]["account_id"], 500)

    def test_adk_route_passes_runtime_settings_to_llm_path(self) -> None:
        settings = Settings(project_root=Path(tempfile.mkdtemp()))
        context = parse_context({"account_id": 500, "player_label": "EEE", "window_matches": 10})
        runtime_settings = {"provider": "openai", "model": "gpt-4o-mini", "api_key": "sk-test"}

        with patch("deadlock_coach.server.run_adk_chat", return_value={"reply": "ok", "source": "google_adk"}) as run_adk_chat:
            reply = _build_adk_reply(
                settings,
                message="hello",
                context=context,
                session_id="demo-session",
                user_id="local-user",
                history=None,
                runtime_settings=runtime_settings,
            )

        self.assertEqual(reply["source"], "google_adk")
        self.assertEqual(run_adk_chat.call_args.kwargs["runtime_settings"], runtime_settings)

    def test_adk_route_short_circuits_utility_questions(self) -> None:
        settings = Settings(project_root=Path(tempfile.mkdtemp()))
        context = parse_context({"account_id": 500, "player_label": "EEE", "window_matches": 10})

        with patch("deadlock_coach.server.run_adk_chat") as run_adk_chat:
            reply = _build_adk_reply(
                settings,
                message="what time is it",
                context=context,
                session_id="demo-session",
                user_id="local-user",
                history=None,
                runtime_settings=None,
            )

        self.assertEqual(reply["source"], "utility")
        self.assertEqual(reply["session_id"], "demo-session")
        run_adk_chat.assert_not_called()

    def test_adk_route_times_out_to_unavailable_reply(self) -> None:
        settings = Settings(project_root=Path(tempfile.mkdtemp()))
        context = parse_context({"account_id": 500, "player_label": "EEE", "window_matches": 10})

        def slow_adk_chat(*args, **kwargs):
            time.sleep(0.05)
            return {"reply": "too late", "source": "google_adk"}

        with patch("deadlock_coach.server.ADK_CHAT_TIMEOUT_SECONDS", 0.01), patch(
            "deadlock_coach.server.run_adk_chat",
            side_effect=slow_adk_chat,
        ):
            reply = _build_adk_reply(
                settings,
                message="hello",
                context=context,
                session_id="demo-session",
                user_id="local-user",
                history=None,
                runtime_settings=None,
            )

        self.assertEqual(reply["source"], "adk_unavailable")
        self.assertEqual(
            reply["unavailable_reason"],
            "ADK chat timed out after 0.01 seconds.",
        )

    def test_resolve_dev_runtime_settings_prefers_openai_key(self) -> None:
        with patch.dict(
            "os.environ",
            {"OPENAI_API_KEY": "sk-live", "OPENAI_MODEL": "gpt-4o"},
            clear=True,
        ):
            payload = _resolve_dev_runtime_settings()

        self.assertEqual(payload.provider, "openai")
        self.assertEqual(payload.model, "gpt-4o")
        self.assertEqual(payload.api_key, "sk-live")

    def test_telemetry_response_model_accepts_recent_events(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            settings = Settings(project_root=Path(tmpdir))
            emit_event(settings, "api.post.finish", request_id="req-1", route="/api/adk/chat")

            payload = TelemetryEventsResponse(events=[{"event_type": "api.post.finish", "request_id": "req-1"}], request_id="req-1")

        self.assertEqual(payload.events[0]["event_type"], "api.post.finish")
        self.assertEqual(payload.request_id, "req-1")


if __name__ == "__main__":
    unittest.main()
