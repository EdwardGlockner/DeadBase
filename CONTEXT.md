# Deadbase

A chat-first Deadlock coaching workspace. The coach answers questions about a player's
hero pool, builds, and item decisions, grounding every claim in game mechanics and
public match telemetry rather than opinion.

## Language

### Item recommendation

**Mechanics**:
The structured, machine-readable properties of an item or hero ability — what it
actually does, in numbers. Distinct from the prose description of the same thing.
_Avoid_: stats, facts, item data

**Threat axis**:
A named category of pressure a hero can apply, such as sustain, burst, mobility, or
crowd control. Both hero abilities and items are classified onto the same axes so the
two sides can be matched.
_Avoid_: category, tag, archetype

**Counter**:
An item whose mechanics oppose a specific threat axis a hero or item applies. A counter
must have both a mechanical basis and empirical support; a purely statistical
association is not a counter.
_Avoid_: answer, tech, response

**Reaction**:
A counter to a specific enemy *item* rather than to a hero. Reactions are discovered
from co-purchase behaviour across opposing teams, not authored.
_Avoid_: counter-item, counter-build

**Hero signature**:
The set of items a hero buys far more often than the global average, independent of any
enemy. Describes how the hero is built, not who it is played against.
_Avoid_: core build, standard build, meta build

**Pick-share lift**:
The difference in how often an item is bought under a condition versus a matched
baseline, in percentage points. The canonical measure of item preference.
_Avoid_: win rate delta, item win rate, performance delta

**Lane duel**:
The scope in which a player is measured only against the enemy they share an assigned
lane with. Distinct from an enemy being merely present in the match.
_Avoid_: matchup, laning, 1v1

**Patch window**:
The time range a set of telemetry covers, expressed in patch boundaries rather than
raw dates. Every empirical claim carries the window it was drawn from.
_Avoid_: time range, date range, period

### Evidence

**Grounding**:
Attaching a verifiable source to a claim — a mechanic, a measured sample, or a patch
note. An answer without grounding is not shippable.
_Avoid_: citation, sourcing, backing

**Confound**:
A variable that produces a real statistical association without a causal relationship,
such as match duration inflating the apparent value of late-game items. Named
explicitly because several have already been found and mistaken for signal.
_Avoid_: bias, noise, artifact
