# Deadbase

Deadbase is an open source Deadlock coaching product focused on one primary workflow: a chat-first coaching workspace that can ground advice in player telemetry, structured tools, and a local knowledge base.

The repo directory is still named `deadlock-coach`, but the product direction and reviewer docs use `Deadbase`.

The goal is not to build a generic chatbot or a dashboard full of cards. The goal is to build a polished, agent-driven coaching product that helps answer questions like:

- what should I focus on right now
- which hero is most reliable for me
- which build branch is actually working
- how do my item timings compare to stronger patterns
- what should I test over the next few matches

## Product Direction

The current MVP direction is:

- coach-first UI, closer to ChatGPT than a dashboard
- dark, minimal, premium workspace feel
- root coaching agent with direct tools and light orchestration behind it
- evidence-backed responses instead of vague motivational chat
- local knowledge base plus imported Deadlock Wiki reference material
- portfolio-grade agent architecture, evals, and observability

Other surfaces such as Hero Lab, Builds, Pro Mirror, Reports, and Experiments still matter, but the main interaction model is the coaching thread.

## Current Architecture

There are two main runtime layers:

1. Backend API and data layer in [`src/deadlock_coach`](/Users/eanu/Documents/deadlock-coach/src/deadlock_coach)
2. ADK app and agent definitions in [`app`](/Users/eanu/Documents/deadlock-coach/app)

At a high level:

- the backend exposes local routes for chat, account search, summaries, recent matches, runtime settings, and telemetry
- the root `coach_agent` is the real conversation entrypoint and should answer most turns directly
- agent instructions are loaded from markdown files on disk
- local telemetry and imported knowledge files are accessible through tools
- the frontend is a local static shell in [`web`](/Users/eanu/Documents/deadlock-coach/web)

## Main Agent Shape

The current ADK stack is centered around:

- `coach_agent` as the user-facing root agent
- direct tools for telemetry, builds, reference lookup, and KB retrieval
- placeholder specialist files for player profile, hero pool, builds, comparison, matchups, reports, experiments, VOD review, and knowledge-base analysis while the root coach is the main focus

Relevant files:

- [`app/agent.py`](/Users/eanu/Documents/deadlock-coach/app/agent.py)
- [`app/instruction_loader.py`](/Users/eanu/Documents/deadlock-coach/app/instruction_loader.py)
- [`app/instructions`](/Users/eanu/Documents/deadlock-coach/app/instructions)
- [`app/tools.py`](/Users/eanu/Documents/deadlock-coach/app/tools.py)
- [`src/deadlock_coach/adk_chat.py`](/Users/eanu/Documents/deadlock-coach/src/deadlock_coach/adk_chat.py)
- [`src/deadlock_coach/agent_orchestration.py`](/Users/eanu/Documents/deadlock-coach/src/deadlock_coach/agent_orchestration.py)

## Knowledge Base

The coaching stack currently uses a file-based reference model:

- imported wiki material in [`docs/knowledge/_imports/wiki`](/Users/eanu/Documents/deadlock-coach/docs/knowledge/_imports/wiki)
- synced patch data in the local warehouse
- live reference lookup tools as a fallback when local files are thin

The intended pattern is:

1. keep the main game-knowledge layer file-based and local
2. import broad hero, item, and systems coverage from the wiki
3. let tools search local files and exact reference tables first
4. keep the root coach grounded in evidence instead of raw theory
5. add curated productized notes later only if they clearly improve answer quality

## Quickstart

### 1. Install dependencies

```bash
uv sync
```

### 2. Bootstrap local storage

```bash
PYTHONPATH=src .venv/bin/python -m deadlock_coach bootstrap
```

### 3. Start the backend

```bash
PYTHONPATH=src .venv/bin/python -m deadlock_coach serve --host 127.0.0.1 --port 3000
```

### 4. Start the frontend shell

```bash
python3 -m http.server 4173 -d web
```

Then open [http://127.0.0.1:4173/](http://127.0.0.1:4173/).

### Local env

Copy `.env.example` to `.env` and fill in the provider settings you want to use.

`.env` is local-only and should never be committed.

Use one runtime provider block at a time:

- LiteLLM proxy
- direct OpenAI
- direct Gemini API
- Vertex AI

For exact env examples, eval-judge setup, and pre-push safety steps, see [`docs/provider-setup.md`](/Users/eanu/Documents/deadlock-coach/docs/provider-setup.md).

## Useful Commands

Inspect the audited public data surface:

```bash
PYTHONPATH=src .venv/bin/python -m deadlock_coach inspect-data-surface
```

List first-class artifact types:

```bash
PYTHONPATH=src .venv/bin/python -m deadlock_coach list-artifacts
```

Sync a player locally:

```bash
PYTHONPATH=src .venv/bin/python -m deadlock_coach sync player --account-id 303017110 --hydrate-matches 4
```

Sync a leaderboard:

```bash
PYTHONPATH=src .venv/bin/python -m deadlock_coach sync leaderboard --region Europe
```

Sync official patch notes from Steam (grounds the coach in recent balance changes):

```bash
PYTHONPATH=src .venv/bin/python -m deadlock_coach sync steam-patches
```

See [`docs/patch-notes.md`](/Users/eanu/Documents/deadlock-coach/docs/patch-notes.md) for how patch grounding works.

Export all locally-stored patch notes to `patchnotes_export.md` (full cleaned bodies, newest first):

```bash
PYTHONPATH=src .venv/bin/python -c "import sys; sys.path.insert(0,'app'); from app.tools import _patch_body_text; from deadlock_coach.config import Settings; from deadlock_coach.storage import _connect; from contextlib import closing; s=Settings.from_env(); rows=list(_connect(s.warehouse_db_path).execute('SELECT source,title,published_at,link,content_full FROM patch_event ORDER BY published_at DESC')); open(s.project_root/'patchnotes_export.md','w',encoding='utf-8').write('\n\n'.join(f'## {r[1]}\n(source {r[0]} | {str(r[2])[:10]})\n\n'+_patch_body_text(r[4],max_chars=10**9)[0] for r in rows)); print('wrote', len(rows), 'to patchnotes_export.md')"
```

On Windows (PowerShell), use `.venv\Scripts\python.exe` and set `$env:PYTHONPATH = "src"` first. The output file is git-ignored.

Sync an analytics snapshot:

```bash
PYTHONPATH=src .venv/bin/python -m deadlock_coach sync analytics \
  --endpoint hero-stats \
  --param min_unix_timestamp=1778976000 \
  --param max_unix_timestamp=1781568000 \
  --json
```

Sync wiki reference files:

```bash
PYTHONPATH=src .venv/bin/python -m deadlock_coach knowledge sync-reference --json
PYTHONPATH=src .venv/bin/python -m deadlock_coach knowledge sync-reference --include-pages --json
```

## API Routes

Useful local routes:

```bash
curl -s http://127.0.0.1:3000/api/health
curl -s http://127.0.0.1:3000/api/accounts
curl -s "http://127.0.0.1:3000/api/account-search?q=EEE&limit=5"
curl -s "http://127.0.0.1:3000/api/summary?account_id=303017110&window_matches=10"
curl -s "http://127.0.0.1:3000/api/recent-matches?account_id=303017110&window_matches=10"
curl -s http://127.0.0.1:3000/api/dev/runtime-settings
```

Chat against the backend:

```bash
curl -s -X POST http://127.0.0.1:3000/api/adk/chat \
  -H "Content-Type: application/json" \
  -d '{"message":"What hero should I queue right now?","context":{"account_id":303017110,"window_matches":10}}'
```

## Testing

Run the test suite:

```bash
PYTHONPATH=src .venv/bin/python -m unittest discover -s tests -q
```

The repo also includes eval scaffolding under [`tests/eval`](/Users/eanu/Documents/deadlock-coach/tests/eval).

Before pushing to GitHub, run:

```bash
bash scripts/prepush_safety_check.sh
```

## Project Layout

```text
app/                    ADK agents, instructions, tool bindings
src/deadlock_coach/     backend API, data layer, chat orchestration, telemetry
web/                    frontend shell
docs/knowledge/         imported reference corpus and optional future local KB files
tests/                  unit, integration, API, and eval coverage
artifacts/telemetry/    local event traces
```

## Roadmap

Planned or in-progress improvements:

- stronger root coach instructions and better output formatting
- typed Pydantic contracts for specialist outputs
- evidence and provenance blocks per answer
- confidence and uncertainty handling
- experiment tracking workflows
- richer eval datasets and regression checks
- tracing and observability for each agent turn
- continued UI polish for chat, sidebar, and settings flows

## Extra Docs

- [`DEVELOPER.md`](/Users/eanu/Documents/deadlock-coach/DEVELOPER.md) for implementation details
- [`CONTRIBUTING.md`](/Users/eanu/Documents/deadlock-coach/CONTRIBUTING.md) for collaboration and PR workflow
- [`docs/review-guide.md`](/Users/eanu/Documents/deadlock-coach/docs/review-guide.md) for reviewer orientation and validation steps
- [`docs/architecture.md`](/Users/eanu/Documents/deadlock-coach/docs/architecture.md) for system shape
- [`docs/data-surface.md`](/Users/eanu/Documents/deadlock-coach/docs/data-surface.md) for upstream data constraints
- [`docs/patch-notes.md`](/Users/eanu/Documents/deadlock-coach/docs/patch-notes.md) for official Steam patch-note grounding
