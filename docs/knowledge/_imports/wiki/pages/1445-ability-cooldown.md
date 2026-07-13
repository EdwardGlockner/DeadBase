# Ability Cooldown

Imported reference

- kind: pages
- source: Deadlock Wiki
- url: https://deadlock.wiki/Ability_Cooldown
- imported_at: 2026-07-10T07:05:52+00:00

Reference extract:

Ability Cooldown is the time it takes for an Ability to be usable again.

### Charged Abilities

Some abilities can acquire multiple charges. In those cases, the ability cooldown represents the time for a charge to become available again after being used. This should not be confused with the time between charges, which describes the delay after using a charge that a different charge can be used.

## Calculation

### Calculating Cooldown Reduction

Despite being presented in-game as +X% Cooldown Reduction, multiple sources stack multiplicatively, not additively:

Total Cooldown Reduction=1−(1−CR1)×(1−CR2)…

Example: With 12% Cooldown Reduction from Diviner's Kevlar and 16% from Superior Cooldown:

- Convert percentages to decimals: 0.12 and 0.16.

- Subtract from 1: (1 - 0.12) = 0.88 and (1 - 0.16) = 0.84.

- Multiply the remainders: 0.88 × 0.84 = 0.7392.

- Subtract from 1: 1 - 0.7392 = 0.2608.

- Total Cooldown Reduction is approximately 26%, not 28%.

## Sources of Ability Cooldown Reduction

| Name | Cost | Category | Stat change |

| --- | --- | --- | --- |

| Spellslinger | 6,400 | Weapon | +5% Ability Cooldown Reduction |

| Enchanter's Emblem | 1,600 | Vitality | +5% Ability Cooldown Reduction |

| Compress Cooldown | 1,600 | Spirit | +18% Ability Cooldown Reduction |

| Superior Cooldown | 3,200 | Spirit | +20% Ability Cooldown Reduction |

| Transcendent Cooldown | 6,400 | Spirit | +25% Ability Cooldown Reduction |

| Frostbite Charm | Legendary | Spirit | +50% Ability Cooldown Reduction |

| Mystic Conduit | Legendary | Spirit | +40% Ability Cooldown Reduction |

- Witchmail has a passive that reduces the cooldown of a random ability as the player takes Spirit Damage.

### Map Spawns

- Golden Statues have a chance to drop a permanent Cooldown Reduction buff.

- Powerup runes can provide a temporary Casting buff that provides +12% to +20% Cooldown Reduction for 160 seconds (scaling with game time from 5 to 40 minutes).

## Item Cooldown

Item Cooldown is the time it takes for an Item to be usable again. This includes both Active and Passive items.

Charge-Up items such as Tankbuster and Mercurial Magnum are not affected by Item Cooldown Reduction.

### Sources of Item Cooldown Reduction

| Name | Cost | Category | Stat change |

| --- | --- | --- | --- |

| Transcendent Cooldown | 6,400 | Spirit | +25% Item Cooldown Reduction |
