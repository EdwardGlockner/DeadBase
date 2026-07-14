from __future__ import annotations

import importlib
import sys
import unittest
from unittest.mock import patch


class AgentConfigurationTests(unittest.TestCase):
    def test_coach_agent_runs_without_internal_sub_agents(self) -> None:
        sys.modules.pop("app.agent", None)
        with patch("app.model_factory.build_model", return_value="test-model"):
            module = importlib.import_module("app.agent")

        self.assertEqual(module.coach_agent.sub_agents, [])
        self.assertEqual(module.root_agent.name, "coach_agent")


if __name__ == "__main__":
    unittest.main()
