# Recommendations come from high badge; the player's bracket is the comparison

The intuitive choice is to coach a player with data from their own rank, and it is
wrong. Rank-matched data describes what is *normal* in a bracket, not what is *correct*,
so ranking on it hands the bracket's blind spots back as advice.

Measured on 2026-07-28 for Haze into Abrams in lane, current patch, pick-share lift over
a matched baseline:

| band | denom | Weakening Headshot | Crippling Headshot | Toxic Bullets |
| --- | --- | --- | --- | --- |
| badge 55–75 | 3,692 | **−0.6** | +0.0 | +2.6 |
| badge 90+ | 2,897 | **+2.0** | +0.5 | +2.4 |

Players below high badge largely do not adapt their anti-heal buys into a sustain
bruiser. A recommender ranking on badge 55–75 would conclude Weakening Headshot is not a
counter to Abrams and would never suggest it.

Recommendations are therefore sourced from **badge 90+**, and the player's own bracket is
used only as the comparison. The gap between the two is the coaching content, which is
also the question the README sets out to answer: *"how do my item timings compare to
stronger patterns."*

## Consequences

- Sample size is not a reason to prefer either band. The lower bracket has *more* data
  (3,692 vs 2,897), so this is not a power trade-off.
- Every statistic must carry its bracket. The normal case is a recommendation drawn from
  a bracket the player does not play in, so unattributed figures state something other
  than what was measured.
- If the two bands agree on a recommendation, the comparison adds nothing and should be
  omitted rather than padded in.
