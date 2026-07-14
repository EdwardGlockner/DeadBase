# Deadbase Review Guide

This guide is for engineers reviewing the repo before deeper collaboration.

The short version:

- the product is a chat-first Deadlock coaching workspace
- the root product surface is `coach_agent`
- the strongest current work is around answer grounding, knowledge retrieval, scoped analytics, and eval infrastructure

## What To Review First

If you only have 20 to 30 minutes, read these in order:

1. [`README.md`](/Users/eanu/Documents/deadlock-coach/README.md)
2. [`docs/architecture/chat-agent-architecture.md`](/Users/eanu/Documents/deadlock-coach/docs/architecture/chat-agent-architecture.md)
3. [`app/instructions/coach_agent.md`](/Users/eanu/Documents/deadlock-coach/app/instructions/coach_agent.md)
4. [`app/tools.py`](/Users/eanu/Documents/deadlock-coach/app/tools.py)
5. [`src/deadlock_coach/agent_orchestration.py`](/Users/eanu/Documents/deadlock-coach/src/deadlock_coach/agent_orchestration.py)
6. [`src/deadlock_coach/knowledge_base.py`](/Users/eanu/Documents/deadlock-coach/src/deadlock_coach/knowledge_base.py)

## What Is Actually Live

The live runtime today is best understood as:

- one root conversational agent
- a thin orchestration layer that attaches routing and evidence support
- tools for telemetry, global analytics, patches, and KB/reference retrieval

## Review Questions That Matter Most

When reviewing changes, the highest-signal questions are:

1. Does the coach answer the actual user question first?
2. Is the answer grounded in the right evidence scope?
3. Does the orchestration support the coach instead of silently taking over?
4. Are tools narrow and reusable, or are they hiding product logic?
5. Is the answer shape clean enough for a premium chat UX?

## Evidence Model

The product deliberately separates four kinds of support:

- player telemetry
- global or rank-scoped comparison data
- local KB/reference material
- inference

Good answers keep those distinct.

Bad answers usually fail by:

- mixing scopes without saying so
- treating a loaded player context as the default answer for every question
- bluffing game concepts that should have been KB-backed
- mislabeling build phases, tiers, or item families

## Current Strong Areas

- instruction-driven root coach behavior
- file-based KB plus imported wiki reference retrieval
- hybrid retrieval for concept and table-backed questions
- analytics tools for hero stats, item stats, item flow, patch context, and player curves
- eval scaffolding with common and regression datasets
- browser-testable local chat shell

## Current Rough Edges

- some architecture docs still describe a more ambitious future than the live system
- the eval system is now robust, but the live model judge still depends on unsandboxed auth access in local Codex runs
- answer quality still needs more pressure on some build and scope-heavy families

## Quick Validation Pass

Install dependencies:

```bash
uv sync
```

Set local env:

```bash
cp .env.example .env
```

Run backend:

```bash
PYTHONPATH=src .venv/bin/python -m deadlock_coach serve --host 127.0.0.1 --port 3000
```

Run frontend:

```bash
python3 -m http.server 4173 -d web
```

Then review via:

- [http://127.0.0.1:4173/](http://127.0.0.1:4173/)
- `curl -s http://127.0.0.1:3000/api/accounts`
- `curl -s http://127.0.0.1:3000/api/dev/runtime-settings`

## Suggested Reviewer Chat Prompts

These are useful because they exercise different evidence scopes:

- `what hero has the highest win rate right now?`
- `how does the winrate look in Eternus 6?`
- `what do people mean by 4.8k spirit?`
- `what are boons?`
- `what do high-mmr players build on shiv?`
- `what true T4 items do Shiv players usually finish on late?`
- `can you explain the latest patch and what happened to Shiv?`
- `what do I usually build on Billy?`

## Test And Eval Commands

Unit and integration pass:

```bash
PYTHONPATH=src .venv/bin/python -m unittest discover -s tests -q
```

Common eval pack:

```bash
/Users/eanu/.local/bin/agents-cli eval generate --dataset tests/eval/datasets/common-basic-questions.json --output artifacts/traces/common-basic-questions
/Users/eanu/.local/bin/agents-cli eval grade --traces artifacts/traces/common-basic-questions
```

Regression pack:

```bash
/Users/eanu/.local/bin/agents-cli eval generate --dataset tests/eval/datasets/coach-regression-pack.json --output artifacts/traces/coach-regression-pack
/Users/eanu/.local/bin/agents-cli eval grade --traces artifacts/traces/coach-regression-pack
```

Note: eval grading can use a dedicated `EVAL_*` provider config that is
separate from the app runtime. That is the recommended local setup if the app
itself uses a proxy-backed model path.

## Reviewer Notes On Naming

The product direction uses `Deadbase`, while some internal files and prompts still use `Deadlock Coach`.

For review purposes:

- treat `Deadbase` as the product name
- treat `Deadlock Coach` as the current coach persona / legacy repo naming

That inconsistency is known and not a blocker for reviewing architecture or behavior.
