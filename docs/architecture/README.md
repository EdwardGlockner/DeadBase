# Deadbase Architecture

These diagrams reflect the current repo shape as of the latest coach-agent pass.

Files:

- `system-overview.svg`
  - end-to-end product and runtime view
- `agent-orchestration.svg`
  - how a chat turn is routed, grounded, and answered
- `knowledge-and-data-flow.svg`
  - how wiki/reference content and analytics data move into the coach

Notes:

- `coach_agent` is the root conversational agent.
- The live internal sub-agents are currently:
  - `data_analyst`
  - `knowledge_analyst`
  - `comparison_analyst`
- The other specialist agent files are placeholders right now.
- The backend still has a deterministic orchestration layer around the agent so we can attach routing hints, evidence, confidence, and trace metadata.
