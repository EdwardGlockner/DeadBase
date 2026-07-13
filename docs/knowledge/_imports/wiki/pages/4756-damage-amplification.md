# Damage Amplification

Imported reference

- kind: pages
- source: Deadlock Wiki
- url: https://deadlock.wiki/Damage_Amplification
- imported_at: 2026-07-10T07:07:38+00:00

Reference extract:

Damage Amplification or Damage Amp is a stat that multiplies the damage caused by the player to affected enemies and NPCs.

Continue Dismiss

- The hero now deals 138 bullet damage (100 x 1.15 x 1.20 = 138).

### Calculating Damage Reduction

Current formula: Damage Reduction from multiple sources adds together before being applied to the base damage.

Total Damage Reduction (Decimal)=DR1+DR2+...

Example:

- A hero deals a base bullet damage of 100.

- Mirage casts base Fire Scarabs on the hero, reducing their damage by 20%, decreasing their bullet damage from 100 to 80 (100 x 0.8 = 80).

- Mirage now afflicts the hero with Inhibitor, reducing their damage by another 30%.

- The hero now deals 50 bullet damage (100 x 0.5 = 50).

Self-inflicted Damage Reduction, such as Golden Goose Egg, Cursed Relic, or Cheat Death (active portion), is added into this same pool alongside any Damage Reduction debuffs applied by enemies.

Intended formula (not currently active): Should Damage Reduction be changed to stack multiplicatively, the formula for the damage multiplier would be:

Damage Multiplier=(1−DR1)×(1−DR2)×...

Example (hypothetical, not reflective of current gameplay):

- A hero deals a base bullet damage of 100.

- Mirage casts base Fire Scarabs on the hero, reducing their damage by 20%, decreasing their bullet damage from 100 to 80 (100 x 0.8 = 80).

- Mirage now afflicts the hero with Inhibitor, reducing their damage by another 30%.

- Under this formula, the hero would deal 56 bullet damage (100 x 0.56 = 56), rather than the 50 produced by the current additive formula.

### Calculating Combined Amplification and Reduction

Damage Amplification and Damage Reduction that apply to the attacker's own damage output, whether from self-inflicted items, ally buffs (such as Air Drop), or enemy debuffs (such as Fire Scarabs and Inhibitor), are collectively referred to here as outgoing modifiers. In the current game version, all outgoing modifiers combine using the following process:

- Compute the Total Amplification Multiplier by multiplying all outgoing amplification sources as shown in the Amplification section.

- Compute the Total Damage Reduction (Decimal) by adding all outgoing reduction sources as shown in the Damage Reduction section.

- The Outgoing Multiplier is then:

Outgoing Multiplier=Total Amplification Multiplier−Total Damage Reduction (Decimal)

Some sources of amplification instead apply to a specific target rather than the attacker, increasing the damage that target takes from the attacker's hits. These are referred to here as target modifiers and include effects such as Bloodscent's bonus against isolated heroes. Target modifiers apply as a separate multiplier on top of the outgoing multiplier:

Damage=Base Damage×Outgoing Multiplier×(1+Target Modifier)

Example:

- A hero deals a base bullet damage of 100.

- The hero is attacking an isolated target and has Bloodscent active (a target modifier of +15%).

- Ivy casts Air Drop on the hero (an outgoing amplification of +20%, so Total Amplification Multiplier = 1.20).

- Mirage afflicts the hero with Fire Scarabs (-20%) and Inhibitor (-30%), giving Total Damage Reduction (Decimal) = 0.20 + 0.30 = 0.50.

- Outgoing Multiplier = 1.20 - 0.50 = 0.70.

- The hero deals 81 bullet damage (100 x 0.70 x 1.15 = 80.5, rounded up in game).

## Sources of Damage Amplification

### Weapon and Spirit Amp

### List of heroes

| Hero | Ability | Tier | Stat change |

| --- | --- | --- | --- |

| Calico | Ava | 3 | +20% Ramping Damage Amp |

| Drifter | Bloodscent | 0 | +15% Damage Amp on Isolated Heroes |

| 3 | +11% Damage Amp on Isolated Heroes |  |  |

| Infernus | Napalm | 0 | +16% Damage Amp |

| 3 | +17% Damage Amp |  |  |

| Ivy | Air Drop | 0 | +20% Damage Amp on Ivy and carried ally |

| Lady Geist | Malice | 0 | +8% Damage Amp per Stack |

| 3 | +7% Damage Amp per Stack |  |  |

| McGinnis | Spectral Wall | 1 | +20% Damage Amp |

| Mo & Krill | Scorn | 3 | +15% Damage Amp per Stack |

| Paradox | Pulse Grenade | 0 | +4% Damage Amp per Stack |

| Pocket | Barrage | 0 | +6% Damage Amp per Stack |

| 3 | +4% Damage Amp per Stack |  |  |

| Shiv | Killing Blow | 0 | +8% Damage Amp |

| 2 | +16% Damage Amp |  |  |

| Sinclair | Rabbit Hex | 0 | +15% Damage Amp |

| 3 | +7% Damage Amp |  |  |

| Victor | Aura of Suffering | 3 | +15% Damage Amp |

### Spirit Amp

| Name | Cost | Category | Stat change |

| --- | --- | --- | --- |

| Escalating Exposure | 6,400 | Spirit | +4.5% Spirit Amp |

## Sources of Damage Reduction

### Weapon and Spirit Reduction

### List of heroes

| Hero | Ability | Tier | Stat change |

| --- | --- | --- | --- |

| Mirage | Fire Scarabs | 0 | -20% Damage Reduction |

| 3 | -15% Damage Reduction |  |  |

| Name | Cost | Category | Stat change |

| --- | --- | --- | --- |

| Haunting Shot | Legendary | Weapon | -40% Damage Reduction |

| Cheat Death | 6,400 | Vitality | -60% Damage Reduction |

| Inhibitor | 6,400 | Vitality | -30% Damage Reduction |

| Golden Goose Egg | 800 | Spirit | -10% Damage Reduction |

| Cursed Relic | 6,400 | Spirit | -14% Damage Reduction |

- Cheat Death, Golden Goose Egg and Cursed Relic reduce damage dealt by its user.

### Spirit Reduction

### List of heroes

| Hero | Ability | Tier | Stat change |

| --- | --- | --- | --- |

| Infernus | Afterburn | 2 | -35% Spirit Damage Reduction |

| Name | Cost | Category | Stat change |

| --- | --- | --- | --- |

| Silencer | 6,400 | Weapon | -25% Spirit Damage Reduction |
