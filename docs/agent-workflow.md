# Agent Skills Workflow

How to use the skills in `.claude/skills/` (Matt Pocock's set) on this repo.

You type these yourself. Every one is marked `disable-model-invocation`, so the
agent cannot start them on its own.

**Last checked against the tracker: 2026-09-12.**

---

## Do this next

**Nothing blocks anything any more.** Every open ticket is takeable, so these can
all run at the same time in separate sessions. Order is by value, not by
dependency.

```
/wayfinder 11 #23
```

Start here. Four closed tickets (`#12`, `#17`, `#19`, `#25`) each deferred a
number to it — claim floors, frequency bands, retrieval thresholds, how often a
failed grounding check is too often. It is where the deferred tuning has piled up.

Then, in any order:

```
/wayfinder 11 #22    # authoring instructions — #19 gave it a contract to test against
/wayfinder 11 #24    # observability — #19 made it one record, three reads, two lifetimes
/wayfinder 11 #18    # item recommendations (independent)
/wayfinder 11 #26    # what the coach remembers (independent)
```

One is already assigned to you from an earlier session and unfinished:

```
/wayfinder 11 #27    # research; can run in the background
```

If you don't want to track any of this, just run `/wayfinder 11` with no ticket
number. It picks the first one that is unclaimed and unblocked.

---

## The five stages

| Stage | Command | How many times |
|---|---|---|
| 0 | `/setup-matt-pocock-skills` | once ever — **done** |
| 1 | `/wayfinder` | once to chart the map — **done** |
| 2 | `/wayfinder 11` | **once per ticket** — 10 of 16 done |
| 3 | `/to-spec` | once |
| 4 | `/to-tickets` | once |
| 5 | `/implement <n>` | once per build ticket |
| 6 | `/code-review` | per branch |

The repeating happens at stage 2 and stage 5. Everything else runs once.

You are in **stage 2**.

---

## What is left, one session each

Six tickets are open. Each line is a separate session, and **none of them blocks
another** — the ordering below is what to do first, not what has to come first.

```
/wayfinder 11 #23    The eval harness and golden datasets         <- start here
/wayfinder 11 #22    How agent instructions are authored/tested
/wayfinder 11 #24    Observability, tracing and monitoring
/wayfinder 11 #18    How item recommendations are derived
/wayfinder 11 #26    What the coach remembers between sessions
/wayfinder 11 #27    How fresh is deadlock-api's match history    (research; assigned)
```

**Expect more than six.** Resolving a ticket can create new ones. The dashboards,
the free-vs-paid boundary, the legal work and patch notifications are all still
vague and will become tickets later. Stage 2 is over when this returns nothing:

```bash
gh api repos/EdwardGlockner/DeadBase/issues/11/sub_issues \
  --jq '[.[] | select(.state=="open")] | length'
```

### Already done

`#12` what the coach owes · `#13` data sources · `#14` player-data audit ·
`#15` retrieval approaches · `#16` where knowledge lives · `#25` the eval set ·
`#17` how the agent finds knowledge · `#20` one agent or several ·
`#21` is ADK the framework we keep · `#19` what grounded means

---

## Rules

- **One ticket per session.** Research tickets are the only exception.
- **Claim before working.** Assign it to yourself first, so a session running in
  parallel skips it. An open ticket with no assignee is free.
- **No code during stage 2.** Wayfinder produces decisions and documents. If a
  ticket seems to need a script to resolve it, the ticket is written wrong — say
  so and stop. Code starts at stage 5.
- **Fog is on purpose.** The map's "Not yet specified" section holds questions
  you can see coming but can't phrase sharply yet. Only make it a ticket when the
  question is sharp — even if you can't answer it yet.

---

## The gotcha between stage 2 and stage 3

`/to-spec` reads **the current conversation**, not the tracker. After a long
wayfinder run every decision sits in a comment on a closed issue, and a fresh
session knows none of it.

So load the decisions into the session first, then run the command in that same
session:

```bash
gh issue view 11
gh api repos/EdwardGlockner/DeadBase/issues/11/sub_issues \
  --jq '.[] | select(.state=="closed") | .number' \
  | xargs -I{} gh issue view {} --comments
```

```
/to-spec
```

---

## Wayfinder tickets vs build tickets

Both are GitHub issues, which is the usual confusion.

- **Wayfinder tickets are questions.** Answering one is a decision. They carry a
  `wayfinder:` label and live as children of map issue #11.
- **Build tickets are work.** Slices of the actual product, made at stage 4 and
  handed to `/implement`.

The map ends where the spec begins. It's finished when there is nothing left to
decide.

---

## Where things are

The map: https://github.com/EdwardGlockner/DeadBase/issues/11

Findings from finished tickets are on branches, not on `main`:

```bash
git show research/deadlock-data-sources:docs/research/deadlock-data-sources.md
git show research/retrieval-approaches:docs/research/retrieval-approaches.md
git show research/player-data-audit:docs/research/player-data-audit.md
git show task/retrieval-eval-set:docs/eval/README.md
```

---

## Not part of the map

The player-data audit (`#14`) found 24 defects, 21 of them observed. The worst:
`won` is never filled in, so every stored match looks unresolved, and the coach
reports losing streaks that did not happen.

That is a bug, not a decision. It doesn't need the map, and fixing it early makes
every later decision easier to judge, because the numbers stop lying.

```
/diagnosing-bugs
```

---

## Other skills

Used inside the stages above, or on their own when you need them:

`/grilling` · `/domain-modeling` · `/research` · `/prototype` · `/tdd` ·
`/diagnosing-bugs` · `/triage` · `/codebase-design` · `/handoff` ·
`/resolving-merge-conflicts` · `/ask-matt` (tells you which skill fits)

`/handoff` is the useful one mid-map: it compacts a long session into a document
the next session can pick up.

## References

- [mattpocock/skills](https://github.com/mattpocock/skills)
- [wayfinder.md](https://github.com/mattpocock/skills/blob/main/docs/engineering/wayfinder.md)
