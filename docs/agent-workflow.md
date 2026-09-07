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

## References

- [mattpocock/skills](https://github.com/mattpocock/skills)
- [wayfinder.md](https://github.com/mattpocock/skills/blob/main/docs/engineering/wayfinder.md)
- [The intended flow, mapped](https://skillselion.com/guides/matt-pocock-skills-map)
- [The /setup-matt-pocock-skills skill](https://www.aihero.dev/skills-setup-matt-pocock-skills)
