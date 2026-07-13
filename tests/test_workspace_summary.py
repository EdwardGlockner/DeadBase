from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from deadlock_coach.coach_service import DEFAULT_WINDOW_MATCHES, build_workspace_summary, parse_context
from deadlock_coach.config import Settings
from deadlock_coach.storage import initialize_workspace


class WorkspaceSummaryTests(unittest.TestCase):
    def test_workspace_summary_is_empty_before_sync(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            settings = Settings(project_root=Path(tmpdir))
            initialize_workspace(settings)

            payload = build_workspace_summary(settings)
            self.assertEqual(payload["tracked_accounts"], [])

            context = parse_context({"account_id": "", "window_matches": 0, "player_label": "eanu-main"})
            self.assertIsNone(context.account_id)
            self.assertEqual(context.window_matches, DEFAULT_WINDOW_MATCHES)
            self.assertEqual(context.player_label, "eanu-main")


if __name__ == "__main__":
    unittest.main()
