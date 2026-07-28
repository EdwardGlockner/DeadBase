# Coaching does not depend on live match telemetry

Deadbase gives in-match advice, so reaching for live match data is the obvious move. The
public surface does not support it, and this is recorded because the question will keep
coming back.

`/v1/matches/active` returns only `account_id`, `hero_id` and `team` per player. Sampled
on 2026-07-28 it held 150 live matches, and `duration_s` was null on every one — so
there are no items, no net worth, no levels, and no game clock. The pool is the in-game
watch tab, capped at the top 200 matches, which is a small fraction of concurrent games.

Genuine in-match state requires `/v1/matches/{match_id}/live/url` plus a Source 2
broadcast parser (demofile-net, Haste). That endpoint is rate-limited to **2 requests
per hour per IP**. It is not a viable product path.

The feature does not need it. Counter advice depends on the enemy lineup, which is known
at draft, and on situational context — objective timing, who is fed, what the enemy just
bought — which the player states in chat. Live telemetry would supply convenience, not
capability.

## Consequences

- The enemy lineup is an input the player provides, not something the system detects.
- `/v1/matches/active` remains usable as optional autofill when the player happens to be
  in the watch-tab pool, but nothing may depend on it.
- If Valve or deadlock-api later exposes per-player live items or a match clock, this
  decision should be revisited — the rest of the design does not assume its absence.
