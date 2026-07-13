from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from deadlock_coach.config import Settings
from deadlock_coach.storage import initialize_workspace


class BootstrapTests(unittest.TestCase):
    def test_initialize_workspace_creates_directories_and_databases(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            settings = Settings(project_root=Path(tmpdir))
            initialize_workspace(settings)

            self.assertTrue(settings.raw_dir.exists())
            self.assertTrue(settings.artifact_dir.exists())
            self.assertTrue(settings.telemetry_dir.exists())
            self.assertTrue(settings.warehouse_db_path.exists())
            self.assertTrue(settings.memory_db_path.exists())


if __name__ == "__main__":
    unittest.main()
