# Coach tools are compositional primitives, not answer-shaped

Item advice has to cover an open-ended set of situations: countering an enemy's sustain,
patching your own kit's vulnerability, judging whether a build archetype still works,
reacting to an objective timer, answering an item the enemy just bought. The obvious
tool — something like `get_counter_items(my_hero, enemy_hero)` — expresses exactly one
of these and has nowhere to put the rest. "Midboss in 90 seconds" has no parameter to
land in.

The coach is therefore given primitives it composes per situation:
`get_hero_mechanics`, `get_item_mechanics`, `find_items_by_effect`, and
`get_hero_item_stats`. The situation arrives in the conversation; the agent decides
which lookups it implies.

A convenience tool sitting alongside the primitives was also rejected. Returning a
ready-ranked answer makes it the cheapest call available to the model, so it gets
invoked for situations it does not fit and silently discards the context that made the
question worth asking — producing confident lane advice for an objective-timing
question.

## Consequences

- Answer quality moves out of the data layer and into
  `app/instructions/coach_agent.md`. A wrong recommendation becomes a prompt problem
  rather than a query problem, which is harder to isolate and regress.
- Eval cases under `tests/eval` must cover several scenario classes, not only the lane
  matchup, or that shift goes unmeasured.
- New scenarios should require no new tools. If one does, the primitive set is missing
  something — that is the signal to add a primitive, not a scenario-specific tool.
