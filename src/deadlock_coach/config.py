from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


def _project_root() -> Path:
    return Path(__file__).resolve().parents[2]


@dataclass(frozen=True)
class Settings:
    project_root: Path
    api_base_url: str = "https://api.deadlock-api.com"
    api_key: str | None = None

    @property
    def data_dir(self) -> Path:
        return self.project_root / "data"

    @property
    def raw_dir(self) -> Path:
        return self.data_dir / "raw"

    @property
    def cache_dir(self) -> Path:
        return self.data_dir / "cache"

    @property
    def warehouse_dir(self) -> Path:
        return self.data_dir / "warehouse"

    @property
    def memory_dir(self) -> Path:
        return self.data_dir / "memory"

    @property
    def artifact_dir(self) -> Path:
        return self.project_root / "artifacts" / "generated"

    @property
    def telemetry_dir(self) -> Path:
        return self.project_root / "artifacts" / "telemetry"

    @property
    def telemetry_events_path(self) -> Path:
        return self.telemetry_dir / "events.jsonl"

    @property
    def warehouse_db_path(self) -> Path:
        return self.warehouse_dir / "coach.sqlite3"

    @property
    def memory_db_path(self) -> Path:
        return self.memory_dir / "player_memory.sqlite3"

    @property
    def knowledge_db_path(self) -> Path:
        return self.cache_dir / "knowledge.sqlite3"

    @classmethod
    def from_env(cls) -> "Settings":
        root = Path(os.environ.get("DEADLOCK_COACH_HOME", _project_root())).resolve()
        return cls(
            project_root=root,
            api_base_url=os.environ.get("DEADLOCK_API_BASE_URL", "https://api.deadlock-api.com"),
            api_key=os.environ.get("DEADLOCK_API_KEY"),
        )
