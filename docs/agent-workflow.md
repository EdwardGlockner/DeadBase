# Agent Skills Workflow

How to use the engineering skills installed in `.claude/skills/` (Matt Pocock's set).

Every skill below is marked `disable-model-invocation`, which means **you type it at the
prompt**. The agent cannot launch these on its own.

## The order

| # | Command | Sessions | What it does |
| --- | --- | --- | --- |
| 0 | `/setup-matt-pocock-skills` | once, ever | Configures the issue tracker, triage labels, and domain-doc layout. Writes `docs/agents/*.md` and an "Agent skills" block in `AGENTS.md`. |
| 1 | `/wayfinder` | one | Charts the map. Names the destination, grills breadth-first, creates decision tickets, fires research subagents, then stops. |
| 2 | `/wayfinder <map>` | **one per decision ticket** | Resolves one ticket: claim, answer, close, record on the map. Repeat until no tickets remain. |
| 3 | `/to-spec` | one | Synthesizes the decisions into a spec (PRD) issue, labelled `ready-for-agent`. |
| 4 | `/to-tickets` | one | Breaks the spec into tracer-bullet build tickets with blocking edges. |
| 5 | `/implement` | one per build ticket | Builds a ticket. Drives `/tdd` at agreed seams. |
| 6 | `/code-review` | per branch or PR | Reviews the change against repo standards and the originating spec. |

The repetition happens at **step 2** and **step 5**, not at step 4. `/to-tickets` runs a
single time.

## The map

Step 1 creates a single issue labelled `wayfinder:map`. That issue *is* the map, and its
URL is what you pass to every later session. It does not exist until step 1 has run.

    /wayfinder 11
    /wayfinder https://github.com/EdwardGlockner/DeadBase/issues/11

Either form works. The decision tickets are child issues of the map; the map body stays a
low-resolution index that links to them rather than restating them.

The GitHub labels (`wayfinder:map`, `wayfinder:research`, `wayfinder:prototype`,
`wayfinder:grilling`, `wayfinder:task`, plus the five triage labels) already exist on this
repo and survive any local cleanup, since labels live server-side.

## Wayfinder vs to-tickets

Both publish issues, which is the usual source of confusion. They are different animals.

- **Wayfinder tickets are decisions.** Each is a *question* whose resolution is a decision,
  sized to one agent session. They carry a `wayfinder:<type>` label: `research`, `prototype`,
  `grilling`, or `task`. Wayfinder's own posture is "Plan, don't do" — it produces decisions,
  not deliverables.
- **to-tickets tickets are work.** Vertical slices of implementation, each demoable on its own,
  handed to `/implement`.

The map ends where `/to-tickets` begins. A map is finished when nothing is left to decide.

One exception: a wayfinder **task** ticket does rather than decides (provisioning API access,
moving data). It earns its place only by unblocking a decision.

## Rules worth remembering

- **Never resolve more than one wayfinder ticket per session.** Research tickets are the only
  exception.
- **Claim before working.** Assign the ticket to yourself first so concurrent sessions skip it.
- **`/to-spec` reads the current conversation.** After a multi-session wayfinder run, the
  decisions live in resolution comments on closed issues. Load the map and its
  Decisions-so-far into the session *before* invoking `/to-spec`, or it synthesizes from
  nothing.
- **`/handoff`** compacts a long session into a document the next one picks up. Useful mid-map.
- **Fog is deliberate.** The map's "Not yet specified" section holds questions you can see
  coming but cannot phrase sharply yet. Ticket it only when the question is sharp, even if you
  cannot answer it yet.

## When to skip wayfinder

Wayfinder is for work too big for one session, where the route is not yet visible. For a single
feature you can reason about in one sitting, start at `/grill-with-docs` instead. It interviews
you and writes ADRs and glossary entries as decisions land, then continues into `/to-spec`.

If wayfinder's breadth-first grill surfaces no fog, the skill itself tells you to stop: you do
not need a map.

## Supporting skills

`/grilling`, `/domain-modeling`, `/research`, `/prototype`, `/tdd`, `/diagnosing-bugs`,
`/triage`, `/codebase-design`, `/resolving-merge-conflicts`. Wayfinder invokes several of these
itself while resolving tickets.

## Continuing the Deadbase map (#11)

The map is charted. This is the exact sequence from here.

**Map:** https://github.com/EdwardGlockner/DeadBase/issues/11

### Step 1 — resolve the decision tickets, one per session

Repeat until the map has no open tickets. **One ticket per session**; the ticket is sized for it.

```bash
# a fresh session each time, then:
/wayfinder 11
```

That loads the map, takes the first ticket on the frontier, assigns it to you, resolves it, closes it, and records it on the map. To choose a specific ticket instead of the frontier's first:

```bash
/wayfinder 11 #19
```

Unblocked tickets may run **in parallel** in separate sessions — claiming assigns the ticket, so a concurrent session skips it.

Start with **#12 (the answer catalog)**. Six tickets block on it, and it is the only one whose resolution unblocks a whole layer. **#25** is independent of it and can run at the same time.

Check what is takeable without opening the map:

```bash
gh issue list --state open --label "wayfinder:grilling" --label "wayfinder:task" --json number,title,assignees
```

A ticket with an assignee is claimed. GitHub renders open blockers on the issue itself.

#### The exact order, one session each

Eleven tickets are open. Blocking edges admit this order — each command is its own fresh session:

```bash
/wayfinder 11 #16    # Where game knowledge lives and how it is stored   <- start here
/wayfinder 11 #25    # A retrieval eval set for coaching questions  (independent; can run in parallel)
/wayfinder 11 #19    # What grounded means operationally
/wayfinder 11 #18    # How item recommendations are derived
/wayfinder 11 #23    # The eval harness and golden datasets
/wayfinder 11 #17    # How the agent finds the right knowledge
/wayfinder 11 #20    # One agent or several
/wayfinder 11 #21    # Is ADK plus Gemini the framework we keep
/wayfinder 11 #22    # How agent instructions are authored and tested
/wayfinder 11 #24    # Observability, tracing and monitoring
/wayfinder 11 #26    # What the coach remembers between sessions  (deferred with its v2 class)
```

Only #16, #18, #19, #25 and #26 are takeable right now; the rest unblock as their blockers close, in the order above.

**Expect more than eleven.** Resolving a ticket can spawn new tickets and graduate fog from "Not yet specified" into real ones — the dashboards, the free-vs-paid boundary and the legal work are all still fog and will become tickets on this map. Do not treat the list above as the full count. The map is finished when this returns nothing:

```bash
gh issue list --state open --json number --jq 'length'   # scoped to #11's sub-issues
```

Or just run `/wayfinder 11` with no ticket and let it pick — it takes the first unclaimed, unblocked ticket every time, which reproduces the order above without you tracking it.

### Step 2 — synthesize the spec, once

Only when no tickets remain.

**`/to-spec` reads the current conversation, not the tracker.** After a multi-session map run every decision lives in a resolution comment on a closed issue, and a fresh session knows none of it. Load the map first, in the same session:

```bash
gh issue view 11
gh issue list --state closed --json number,title,comments --jq '.[] | {number, title, comments: [.comments[].body]}'
```

Then, in that same session:

```bash
/to-spec
```

Produces a PRD issue labelled `ready-for-agent`.

### Step 3 — break the spec into build tickets, once

```bash
/to-tickets
```

Runs a **single** time. Produces vertical build slices with blocking edges — work, not decisions.

### Step 4 — build, one ticket per session

```bash
/implement <ticket-number>
```

Repeat per build ticket. It drives `/tdd` at agreed seams.

### Step 5 — review

```bash
/code-review
```

### Research findings

Three research tickets were resolved during charting. Their findings are on branches, not on main:

```bash
git show research/deadlock-data-sources:docs/research/deadlock-data-sources.md
git show research/retrieval-approaches:docs/research/retrieval-approaches.md
git show research/player-data-audit:docs/research/player-data-audit.md
```

### Outside the map

The player-data audit found 24 defects, 21 observed — starting with `won` never being populated, so 100% of match history is stored unresolved and the coach reports fabricated loss streaks. That is a bug, not a decision, and it does not need the map. Fixing it early makes every downstream decision easier to evaluate, because the telemetry stops lying.

## References

- [mattpocock/skills](https://github.com/mattpocock/skills)
- [wayfinder.md](https://github.com/mattpocock/skills/blob/main/docs/engineering/wayfinder.md)
- [The intended flow, mapped](https://skillselion.com/guides/matt-pocock-skills-map)
- [The /setup-matt-pocock-skills skill](https://www.aihero.dev/skills-setup-matt-pocock-skills)
