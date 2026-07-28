# Agent Skills

This repo ships a set of AI-coding **skills** — Matt Pocock's engineering workflow, vendored from
[`github.com/mattpocock/skills`](https://github.com/mattpocock/skills) into `.claude/skills/`. They
turn a rough idea into scoped GitHub issues and then into implemented, tested code, using a
repeatable flow instead of ad-hoc prompting.

The skills themselves live in the repo, so everyone gets them on `git pull`. Each developer still
does a small one-time local setup (Claude Code + the `gh` CLI + login) — that part is per-machine
and covered below.

## The main flow

For a large piece of work, run these in order **in one Claude Code session** (don't `/clear` or
compact between them — each step builds on the last):

```
/wayfinder  →  /grill-with-docs  →  /to-spec  →  /to-tickets  →  /implement
```

| Step | Skill | What it does |
| ---- | ----- | ------------ |
| 1 | `/wayfinder` | Maps work too big for one session as a shared `wayfinder:map` issue with child decision tickets, resolved one at a time until the route is clear. |
| 2 | `/grill-with-docs` | A relentless interview that sharpens the plan and writes domain docs (ADRs + glossary) as it goes. Expect 40–80 questions — dictation is faster than typing. |
| 3 | `/to-spec` | Synthesises the conversation so far into a spec (PRD) and publishes it as a GitHub issue. No new interview. |
| 4 | `/to-tickets` | Breaks the spec into tracer-bullet tickets — one GitHub issue each, with native `blocked_by` dependency links. |
| 5 | `/implement` | Builds the work against a spec or tickets, using `/tdd` at agreed seams. |

**Smaller work?** Skip straight to `/grill-with-docs` → `/implement`, or just implement directly.

**Not sure which skill fits?** Run `/ask-matt` — it's a router over all the installed skills.

Other installed skills you can call directly: `/triage`, `/code-review`, `/tdd`,
`/domain-modeling`, `/prototype`, `/research`, `/diagnosing-bugs`, `/handoff`,
`/resolving-merge-conflicts`, `/improve-codebase-architecture`, and more. See `.claude/skills/` for
the full set (22 skills).

## Where tickets and specs go

Configured to use **GitHub Issues** on this repo. The skills call the `gh` CLI:

- Specs and tickets become issues via `gh issue create`.
- `/to-tickets` links dependencies using GitHub's native issue dependencies (`blocked_by`).
- `/wayfinder` uses a `wayfinder:map` issue plus child tickets.

The label vocabulary (already created on the repo) is:

- Triage: `needs-triage`, `needs-info`, `ready-for-agent`, `ready-for-human`, `wontfix`
- Wayfinder: `wayfinder:map`, `wayfinder:research`, `wayfinder:prototype`, `wayfinder:grilling`, `wayfinder:task`

The full tracker/label/domain configuration lives in this folder:
[`issue-tracker.md`](./issue-tracker.md), [`triage-labels.md`](./triage-labels.md),
[`domain.md`](./domain.md). To switch the tracker (e.g. back to local markdown files under
`.scratch/`), re-run `/setup-matt-pocock-skills` or edit `issue-tracker.md` directly.

---

## Per-developer setup (one time)

You need two tools locally: **Claude Code** and the **GitHub CLI (`gh`)**.

### 1. Claude Code

Install from [claude.com/claude-code](https://claude.com/claude-code) (or your team's usual channel),
then open it in the repo root. The skills are discovered automatically from `.claude/skills/`.

### 2. GitHub CLI (`gh`)

**macOS** (Homebrew):

```bash
brew install gh
```

**Windows** (winget):

```powershell
winget install --id GitHub.cli
```

**Linux** (Debian/Ubuntu) — see [cli.github.com](https://cli.github.com) for other distros:

```bash
sudo apt install gh
```

### 3. Authenticate `gh`

```bash
gh auth login
```

Choose **GitHub.com → HTTPS → Login with a web browser**, and use an account that has access to
`EdwardGlockner/DeadBase`. The `repo` scope is required (issues + labels); `gist` is used by
`/wayfinder` for context pointers.

Prefer a token instead of the browser flow? Create a classic PAT at
[github.com/settings/tokens](https://github.com/settings/tokens) with `repo`, `read:org`, `workflow`,
and `gist` scopes, then:

```bash
echo "ghp_YOURTOKEN" | gh auth login --hostname github.com --with-token
```

Verify:

```bash
gh auth status        # → Logged in to github.com
gh issue list         # → reads this repo's issues (empty is fine)
```

### 4. Restart Claude Code

If Claude Code was already open when you installed `gh`, restart it so `gh` is on its `PATH` and the
skills are registered. Then type `/` — you should see `/wayfinder`, `/to-tickets`, `/implement`, etc.

---

## Running the skills

Inside Claude Code, invoke any skill by typing its slash command, e.g.:

```
/wayfinder
```

Then follow its prompts. A typical big-feature session:

1. `/wayfinder` — answer the decision tickets it creates until the route is clear.
2. `/grill-with-docs` — get interrogated; answer honestly, let it write the ADRs.
3. `/to-spec` — review the spec issue it publishes.
4. `/to-tickets` — review the ticket issues and their blocking order.
5. `/implement` — hand off the build (works well as an AFK / background agent run).

Keep steps 1–4 in a single session so the grilling, spec, and tickets share the same context.

## Updating the skills

These skills are **vendored** (copied into the repo), not installed from a package — so they don't
auto-update. To pull newer versions from upstream:

```bash
git clone --depth 1 https://github.com/mattpocock/skills.git /tmp/mp-skills
# copy the updated engineering/ + productivity/ skill folders into .claude/skills/<name>/,
# omitting each skill's agents/ (OpenAI/Codex metadata Claude Code doesn't use)
```

Then commit the refreshed `.claude/skills/`. Local customisations you've made to a skill will be
overwritten, so review the diff before committing.

## Troubleshooting

- **`gh: command not found`** — `gh` isn't installed, or Claude Code / your terminal was open before
  you installed it. Restart the terminal (and Claude Code).
- **`/to-tickets` fails talking to GitHub** — run `gh auth status`; you're probably not logged in, or
  your token lacks the `repo` scope. Re-run `gh auth login`.
- **Slash commands don't appear** — restart Claude Code so it re-scans `.claude/skills/`.
- **Labels missing on the repo** — they were created once already; if a fresh fork lacks them, ask a
  maintainer to re-run `/setup-matt-pocock-skills`, or create them with `gh label create`.
