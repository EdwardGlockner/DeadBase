# Chat Agent Architecture

This is the current chat architecture for Deadbase.

## Current Shape

The live system is simpler than the file tree makes it look:

1. `coach_agent` is the root conversational agent.
2. `data_analyst` is the active internal specialist for telemetry, analytics, build flow, win rates, and player/global data questions.
3. `knowledge_analyst` is the active internal specialist for concepts, KB grounding, imported wiki notes, and patch/reference questions.
4. `comparison_analyst` is the active internal specialist for player-vs-rank, player-vs-meta, and broader comparison questions.
5. The other specialist files currently exist as placeholders and are not meaningful parts of the live routing path yet.

So the real active structure today is:

- root agent: `coach_agent`
- active sub-agents:
  - `data_analyst`
  - `knowledge_analyst`
  - `comparison_analyst`

## Runtime Flow

The runtime path is:

1. `semantic_router.py`
   - infers the question family
   - infers likely scope such as `player_specific`, `global`, or `knowledge`
   - suggests tool lanes and analyst lanes
2. `agent_orchestration.py`
   - builds prompt support
   - gathers deterministic evidence and context
   - prepares confidence, evidence graph, and trace metadata
3. `adk_chat.py`
   - builds the final user prompt
   - sends it to the ADK-backed root agent
4. `app/agent.py`
   - defines the root `coach_agent`
   - exposes tools
   - exposes internal sub-agents

## What This Means In Practice

This is not a large workflow graph right now.

It is best described as:

- one root chat agent
- a thin deterministic orchestration layer around it
- three active specialist sub-agents
- tools for data and knowledge retrieval

That is good enough for the current phase because the main product problem is still answer quality, scope discipline, and grounding.

## Why This Shape Is Reasonable For Now

This architecture keeps the important responsibilities separated:

- `coach_agent` owns tone, final answer shape, and user-facing conversation
- `data_analyst` owns structured retrieval for telemetry and meta questions
- `knowledge_analyst` owns KB and reference grounding
- `comparison_analyst` owns player-vs-rank and player-vs-meta framing
- orchestration owns routing hints, evidence packaging, and confidence/trace scaffolding

That is cleaner than a giant root-agent prompt trying to do everything from memory.

## Current Weaknesses

The current architecture still has some rough edges:

- some routing and evidence behavior is still heuristic-heavy
- scope discipline is improving but still needs stronger eval pressure
- the placeholder specialist files make the repo look more mature than the live routing actually is
- the answer contract is still too loose for some families, especially build answers and concept answers

## Recommended Next Step

The next architectural step should be:

1. keep `coach_agent` as the root
2. keep `data_analyst`, `knowledge_analyst`, and `comparison_analyst` as the only real active sub-agents for now
3. make every answer explicitly choose one primary scope before generation:
   - `player`
   - `global`
   - `knowledge`
4. add stronger typed answer contracts for the main families:
   - concept
   - player build
   - global build
   - hero meta
   - patch summary

That would make the system feel much more intentional without prematurely turning it into an over-engineered workflow graph.
