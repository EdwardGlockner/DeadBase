from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.instruction_loader import load_instruction


class InstructionLoaderTests(unittest.TestCase):
    def test_load_instruction_reads_file_relative_to_anchor(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            anchor = root / "pkg" / "agent.py"
            anchor.parent.mkdir(parents=True, exist_ok=True)
            anchor.write_text("# anchor\n", encoding="utf-8")
            instruction = anchor.parent / "instructions" / "coach.md"
            instruction.parent.mkdir(parents=True, exist_ok=True)
            instruction.write_text("Hello {{NAME}}", encoding="utf-8")

            body = load_instruction(anchor, "instructions/coach.md", NAME="Deadbase")

        self.assertEqual(body, "Hello Deadbase")

    def test_load_instruction_rejects_path_escape(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            anchor = root / "pkg" / "agent.py"
            anchor.parent.mkdir(parents=True, exist_ok=True)
            anchor.write_text("# anchor\n", encoding="utf-8")

            with self.assertRaises(ValueError):
                load_instruction(anchor, "../outside.md")

    def test_load_instruction_requires_existing_file(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            anchor = root / "pkg" / "agent.py"
            anchor.parent.mkdir(parents=True, exist_ok=True)
            anchor.write_text("# anchor\n", encoding="utf-8")

            with self.assertRaises(FileNotFoundError):
                load_instruction(anchor, "instructions/missing.md")


if __name__ == "__main__":
    unittest.main()
