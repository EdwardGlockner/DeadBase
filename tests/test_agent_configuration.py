from __future__ import annotations

import importlib
import sys
import unittest
from unittest.mock import patch


class AgentConfigurationTests(unittest.TestCase):
    def test_coach_agent_registers_internal_data_and_knowledge_sub_agents(self) -> None:
        sys.modules.pop("app.agent", None)
        with patch("app.model_factory.build_model", return_value="test-model"):
            module = importlib.import_module("app.agent")

        sub_agent_names = [agent.name for agent in module.coach_agent.sub_agents]

        self.assertIn("data_analyst", sub_agent_names)
        self.assertIn("knowledge_analyst", sub_agent_names)
        self.assertEqual(module.root_agent.name, "coach_agent")


if __name__ == "__main__":
    unittest.main()
