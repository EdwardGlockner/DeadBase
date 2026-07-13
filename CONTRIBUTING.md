# Contributing To Deadbase

This repo is still in an MVP phase, but it is structured to be shareable and reviewable by other engineers.

The most important thing to understand before making changes is that the product is chat-first. We are optimizing for a sharp coaching conversation, not for a dashboard-heavy analytics app.

## Working Agreement

- Keep the coach chat as the main workflow.
- Prefer grounded answers over clever answers.
- Prefer small, explicit tools over hidden service heuristics.
- Treat `coach_agent` as the main product surface.
- Do not expand placeholder specialist agents unless that is the specific task.

## Current Live Architecture

The repo tree is broader than the currently active runtime.

Today, the live coaching stack is mainly:

- root agent: `coach_agent`
- active supporting lanes:
  - `data_analyst`
  - `knowledge_analyst`
  - `comparison_analyst`
- deterministic backend support for:
  - routing hints
  - evidence packaging
  - confidence
  - trace metadata

Several other specialist files still exist as placeholders so the future architecture has a home, but they are not meaningful parts of the live routing path yet.

## Local Setup

Install dependencies:

```bash
uv sync
```

Create local env:

```bash
cp .env.example .env
```

Then edit `.env` with the provider settings you actually want to use.

If you are not sure which env values belong together, use [`docs/provider-setup.md`](/Users/eanu/Documents/deadlock-coach/docs/provider-setup.md).

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

## Secrets And Local State

- `.env` is local-only and is ignored by git.
- `.env.*`, common credential file extensions, local telemetry, and generated eval artifacts are also ignored.
- Do not commit API keys, Cloud Run proxy keys, or exported runtime settings.
- `artifacts/traces` and `artifacts/grade_results` are also ignored because they are generated locally.
- If you need to share eval output, export or summarize it intentionally instead of committing raw local artifacts by default.

Run this before pushing:

```bash
bash scripts/prepush_safety_check.sh
```

## Repo Map

- [`app`](/Users/eanu/Documents/deadlock-coach/app): ADK agent definitions, tools, model setup, instruction loading
- [`src/deadlock_coach`](/Users/eanu/Documents/deadlock-coach/src/deadlock_coach): backend API, orchestration, telemetry, storage, knowledge retrieval
- [`web`](/Users/eanu/Documents/deadlock-coach/web): static frontend shell
- [`docs/knowledge/_imports/wiki`](/Users/eanu/Documents/deadlock-coach/docs/knowledge/_imports/wiki): imported reference corpus
- [`tests`](/Users/eanu/Documents/deadlock-coach/tests): unit, integration, API, and eval coverage

## Before Opening A PR

Minimum expected local validation:

```bash
PYTHONPATH=src .venv/bin/python -m unittest discover -s tests -q
```

If you changed agent behavior, also do these:

1. Run at least one manual chat pass in the browser.
2. Run the relevant eval dataset.
3. Inspect answer formatting, not just correctness.
4. Check that the answer uses the right evidence scope:
   - player telemetry
   - global/meta data
   - KB/reference grounding

Useful eval commands:

```bash
/Users/eanu/.local/bin/agents-cli eval generate --dataset tests/eval/datasets/common-basic-questions.json --output artifacts/traces/common-basic-questions
/Users/eanu/.local/bin/agents-cli eval grade --traces artifacts/traces/common-basic-questions
```

If the app runtime uses a Cloud Run LiteLLM proxy, you may still want a simpler
dedicated judge for eval grading. The eval stack supports separate `EVAL_*`
provider settings for that reason.

## Review Priorities

When reviewing or contributing, prioritize:

1. answer quality
2. grounding and evidence discipline
3. scope correctness
4. output formatting
5. maintainability of tools and orchestration

Good changes usually make one of these better without making the product noisier or more complex.

## Areas That Need Extra Care

- [`app/instructions/coach_agent.md`](/Users/eanu/Documents/deadlock-coach/app/instructions/coach_agent.md)
  - easiest place to improve or accidentally degrade product behavior
- [`app/tools.py`](/Users/eanu/Documents/deadlock-coach/app/tools.py)
  - high leverage, but easy to bloat
- [`src/deadlock_coach/agent_orchestration.py`](/Users/eanu/Documents/deadlock-coach/src/deadlock_coach/agent_orchestration.py)
  - should stay supportive, not become a second hidden product
- [`src/deadlock_coach/knowledge_base.py`](/Users/eanu/Documents/deadlock-coach/src/deadlock_coach/knowledge_base.py)
  - important for table-backed and concept-backed grounding
- [`web/app.js`](/Users/eanu/Documents/deadlock-coach/web/app.js)
  - chat UX polish and evidence presentation

## Good First Contribution Shapes

- tighten a specific answer family with eval coverage
- improve one retrieval/tool contract
- improve one chat UX edge case
- add one focused analytics surface with tests
- add one reviewer-visible architecture or setup doc

## Reviewer Docs

If you are reviewing rather than contributing first, start with:

- [`README.md`](/Users/eanu/Documents/deadlock-coach/README.md)
- [`docs/review-guide.md`](/Users/eanu/Documents/deadlock-coach/docs/review-guide.md)
- [`docs/architecture/chat-agent-architecture.md`](/Users/eanu/Documents/deadlock-coach/docs/architecture/chat-agent-architecture.md)
