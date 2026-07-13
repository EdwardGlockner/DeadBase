# Deadbase Developer Guide

This file is for implementation work inside the Deadbase repo.

Use [`README.md`](/Users/eanu/Documents/deadlock-coach/README.md) for the product overview. Use this file when changing agent behavior, backend logic, UI flows, knowledge files, or evals.

## Development Priorities

The current repo priority order is:

1. make the Coach chat genuinely useful
2. keep answers grounded in evidence
3. keep the UI minimal, polished, and chat-first
4. improve agent architecture without turning the product into a demo of complexity

When in doubt, favor:

- better coaching answers
- cleaner evidence handling
- less UI clutter
- fewer but stronger abstractions

## Repo Map

### Product shell

- [`web/index.html`](/Users/eanu/Documents/deadlock-coach/web/index.html)
- [`web/styles.css`](/Users/eanu/Documents/deadlock-coach/web/styles.css)
- [`web/app.js`](/Users/eanu/Documents/deadlock-coach/web/app.js)

### ADK agent app

- [`app/agent.py`](/Users/eanu/Documents/deadlock-coach/app/agent.py)
- [`app/tools.py`](/Users/eanu/Documents/deadlock-coach/app/tools.py)
- [`app/model_factory.py`](/Users/eanu/Documents/deadlock-coach/app/model_factory.py)
- [`app/instruction_loader.py`](/Users/eanu/Documents/deadlock-coach/app/instruction_loader.py)
- [`app/instructions`](/Users/eanu/Documents/deadlock-coach/app/instructions)

### Backend and orchestration

- [`src/deadlock_coach/server.py`](/Users/eanu/Documents/deadlock-coach/src/deadlock_coach/server.py)
- [`src/deadlock_coach/api.py`](/Users/eanu/Documents/deadlock-coach/src/deadlock_coach/api.py)
- [`src/deadlock_coach/adk_chat.py`](/Users/eanu/Documents/deadlock-coach/src/deadlock_coach/adk_chat.py)
- [`src/deadlock_coach/coach_service.py`](/Users/eanu/Documents/deadlock-coach/src/deadlock_coach/coach_service.py)
- [`src/deadlock_coach/agent_orchestration.py`](/Users/eanu/Documents/deadlock-coach/src/deadlock_coach/agent_orchestration.py)
- [`src/deadlock_coach/agent_contracts.py`](/Users/eanu/Documents/deadlock-coach/src/deadlock_coach/agent_contracts.py)
- [`src/deadlock_coach/api_models.py`](/Users/eanu/Documents/deadlock-coach/src/deadlock_coach/api_models.py)

### Data and knowledge

- [`src/deadlock_coach/account_service.py`](/Users/eanu/Documents/deadlock-coach/src/deadlock_coach/account_service.py)
- [`src/deadlock_coach/knowledge_base.py`](/Users/eanu/Documents/deadlock-coach/src/deadlock_coach/knowledge_base.py)
- [`docs/knowledge`](/Users/eanu/Documents/deadlock-coach/docs/knowledge)

### Telemetry and testing

- [`src/deadlock_coach/telemetry.py`](/Users/eanu/Documents/deadlock-coach/src/deadlock_coach/telemetry.py)
- [`tests`](/Users/eanu/Documents/deadlock-coach/tests)
- [`tests/eval`](/Users/eanu/Documents/deadlock-coach/tests/eval)

## Agent Architecture

The current stack should behave like one sharp coach with tools, not like a visible swarm of agents.

Current structure:

- `coach_agent` is the only real user-facing agent
- the root coach should answer most turns directly with narrow tool usage
- specialist files currently exist as placeholders so we can preserve the future architecture without letting it dominate the MVP

Design rule:

- the user should feel like they are talking to one sharp coach
- orchestration should stay light and mostly exist to attach evidence, routing hints, and typed response metadata
- KB-first behavior should come from the root instructions and tool lanes, not from brittle keyword gates

## Instruction Files

Agent instructions now live in markdown files and are loaded from disk.

Loader:

- [`app/instruction_loader.py`](/Users/eanu/Documents/deadlock-coach/app/instruction_loader.py)

Instruction directory:

- [`app/instructions`](/Users/eanu/Documents/deadlock-coach/app/instructions)

Shared formatting rules:

- [`app/instructions/shared/chat_formatting_rules.md`](/Users/eanu/Documents/deadlock-coach/app/instructions/shared/chat_formatting_rules.md)

Root agent prompt:

- [`app/instructions/coach_agent.md`](/Users/eanu/Documents/deadlock-coach/app/instructions/coach_agent.md)

Rules for prompt work:

- keep the root coach direct and natural
- do not let prompts drift into product-tour language
- avoid repetitive stat dumping
- avoid giant walls of text
- prefer grounded conclusions, then evidence, then one useful next step
- keep specialist prompts narrower than the root prompt
- for game concepts, mechanics, theory, items, heroes, patches, and systems questions, make the coach check the KB before answering from memory

## Tooling Model

The repo currently uses a mix of:

- backend functions that produce local player summaries and evidence
- ADK tools exposed through [`app/tools.py`](/Users/eanu/Documents/deadlock-coach/app/tools.py)
- knowledge-base search and reference lookup
- orchestration helpers that enrich replies with evidence metadata

Current philosophy:

- let the LLM and instructions drive the conversation
- give the coach strong, narrow tools
- keep backend heuristics minimal and utility-shaped
- avoid hardcoding domain concepts in service logic when the KB can answer them

When adding tools:

- give each tool a narrow job
- prefer typed outputs when possible
- keep tool names concrete
- make sure the output is useful for both the root coach and future UI rendering

Good future contract examples:

- `HeroPoolDiagnosis`
- `BuildTimingAudit`
- `ConfidenceReport`
- `PracticePlan`
- `ExperimentStatus`

## Knowledge Base Strategy

The KB is currently centered on local imported reference material, not a handwritten coaching-note layer.

Current layers:

1. imported reference material
2. synced patch data
3. fallback live lookup

### Imported reference files

These live in [`docs/knowledge/_imports/wiki`](/Users/eanu/Documents/deadlock-coach/docs/knowledge/_imports/wiki).

These files are the current file-based game-knowledge layer for heroes, items, systems, tables, and general concepts.

### Knowledge rules

- imported wiki files should support factual lookup and table-backed answers
- synced patch data should support patch-specific grounding
- retrieval should move toward chunking, tagging, and reranking over time
- curated productized notes can be reintroduced later, but they are not the current top layer

## Data Sources

Current product thinking:

- profile-specific and recent-match grounding can come from the Deadlock API and local storage
- knowledge and hero or item reference can come from the local KB and imported wiki files
- external build or meta layers can be added carefully, but the root coach should always distinguish between:
  - player telemetry
  - external comparison context
  - knowledge-base guidance
  - inference

That distinction matters for trust and future provenance rendering.

## Running the Project

### macOS / Linux

Install dependencies:

```bash
uv sync
```

Bootstrap local storage:

```bash
PYTHONPATH=src .venv/bin/python -m deadlock_coach bootstrap
```

Start backend:

```bash
PYTHONPATH=src .venv/bin/python -m deadlock_coach serve --host 127.0.0.1 --port 3000
```

Start frontend:

```bash
python3 -m http.server 4173 -d web
```

### Windows (PowerShell)

On Windows the venv interpreter lives at `.venv\Scripts\python.exe`, and
`PYTHONPATH` is set per-session with `$env:PYTHONPATH` instead of an inline
`VAR=value` prefix. Run each long-running server in its own PowerShell window.

Install dependencies:

```powershell
uv sync
```

Bootstrap local storage:

```powershell
$env:PYTHONPATH = "src"
.venv\Scripts\python.exe -m deadlock_coach bootstrap
```

Start backend (leave this terminal running):

```powershell
$env:PYTHONPATH = "src"
.venv\Scripts\python.exe -m deadlock_coach serve --host 127.0.0.1 --port 3000
```

Start frontend (second terminal):

```powershell
.venv\Scripts\python.exe -m http.server 4173 -d web
```

Then open [http://127.0.0.1:4173/](http://127.0.0.1:4173/). For a quick health
check, `curl.exe http://127.0.0.1:3000/api/health` (use `curl.exe`, since bare
`curl` is a PowerShell alias for `Invoke-WebRequest`).

Provider setup and local secret-handling notes live in [`docs/provider-setup.md`](/Users/eanu/Documents/deadlock-coach/docs/provider-setup.md).

## Knowledge Import Commands

Import a slice of wiki pages:

```bash
PYTHONPATH=src .venv/bin/python -m deadlock_coach knowledge sync-wiki --kind heroes --limit 12
PYTHONPATH=src .venv/bin/python -m deadlock_coach knowledge sync-wiki --kind items --title "Active Reload" --title "Healing Rite"
```

Import the broader reference corpus:

```bash
PYTHONPATH=src .venv/bin/python -m deadlock_coach knowledge sync-reference --json
```

## Testing Workflow

Default regression pass:

```bash
PYTHONPATH=src .venv/bin/python -m unittest discover -s tests -q
```

When changing agents, do all of this:

1. test the chat route
2. test the UI flow manually
3. run unit and integration coverage
4. inspect the output for formatting regressions

Useful local checks:

```bash
curl -s http://127.0.0.1:3000/api/health
curl -s "http://127.0.0.1:3000/api/account-search?q=EEE&limit=5"
curl -s "http://127.0.0.1:3000/api/summary?account_id=303017110&window_matches=10"
curl -s -X POST http://127.0.0.1:3000/api/adk/chat \
  -H "Content-Type: application/json" \
  -d '{"message":"What should I focus on right now?","context":{"account_id":303017110,"window_matches":10}}'
```

## Eval Direction

The repo already has eval scaffolding in [`tests/eval`](/Users/eanu/Documents/deadlock-coach/tests/eval).

Target eval qualities:

- directness
- factual grounding
- non-redundancy
- correct uncertainty behavior
- clean formatting
- correct tool selection

Longer term, build a proper golden dataset that covers:

- greetings
- player-form questions
- hero-pool questions
- build timing questions
- uncertainty cases
- missing-data cases
- knowledge-only cases
- comparison cases

## Telemetry and Observability

The repo already contains telemetry plumbing and local event traces.

Relevant files:

- [`src/deadlock_coach/telemetry.py`](/Users/eanu/Documents/deadlock-coach/src/deadlock_coach/telemetry.py)
- [`artifacts/telemetry/events.jsonl`](/Users/eanu/Documents/deadlock-coach/artifacts/telemetry/events.jsonl)

The intended direction is per-turn observability:

- which agent handled what
- which tools ran
- latency per step
- failures and fallbacks
- evidence used
- final confidence

## UI Conventions

The frontend direction is strict:

- coach-first
- dark
- minimal
- quiet surfaces
- no dashboard spam
- no landing-page hero behavior

For the Coach tab specifically:

- chat is the main event
- context should not dominate the screen
- responses must feel natural and readable
- scroll behavior must stay solid
- sidebar and settings must not overlap

## Current Quality Bar

A change is probably not good enough if:

- it makes the coach more verbose
- it adds more dashboard furniture
- it introduces another boxy UI pattern
- it makes the root coach sound like an internal router
- it mixes player evidence and theory without saying so
- it cannot be tested easily

## Good Next Steps

High-value next improvements:

- tighten `coach_agent.md` until the chat feels genuinely sharp
- move more specialist outputs to typed Pydantic contracts
- attach evidence provenance to every answer
- add explicit confidence reporting
- strengthen the eval dataset
- keep refining the curated KB instead of relying on raw imports
