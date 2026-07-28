# Item recommendations use pick-share lift, not win rate

Item win rate is the obvious signal for "is this item good against X", and it is
unusable. Measured on 2026-07-28 against `/v1/analytics/item-stats`, every anti-heal
item with a meaningful sample performed *worse* in lane against Abrams — the
archetypal sustain bruiser — than at baseline: Toxic Bullets −1.2pp, Weakening
Headshot −2.6pp, Crippling Headshot −2.8pp, Inhibitor −1.5pp. A recommender built on
win rate would advise players not to buy anti-heal into a healer.

The cause is selection bias: situational counter-buys correlate with already being
behind, and the highest-win-rate items are simply the expensive ones you survive long
enough to afford (Frenzy, Silencer, Spiritual Overflow topped every list).

We therefore rank items by **pick-share lift** — how much more often an item is bought
under a condition than in a matched baseline. On the same query, high-badge Haze
players facing Abrams in lane bought Weakening Headshot +3.5pp, Toxic Bullets +2.1pp
and Crippling Headshot +1.4pp more often, while Healing Tempo (a *self*-heal
amplifier that superficially matches an anti-heal property filter) moved −0.1pp.
Revealed preference encodes the direction of an effect that item properties alone do
not.

## Consequences

- Every empirical claim needs a **matched** baseline. Comparing a filtered sample to
  an unfiltered one reintroduces the confound; this has already produced three false
  signals (match duration masquerading as "enemy is fed", late-game items
  masquerading as counterplay).
- Pick-share lift is correlational. It ranks and prunes candidates; it never
  establishes that an item counters something. The mechanical layer supplies that,
  and a recommendation requires both.
- Win rate is still worth storing for display, but must not drive ranking.
