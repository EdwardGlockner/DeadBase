# Move Speed

Imported reference

- kind: pages
- source: Deadlock Wiki
- url: https://deadlock.wiki/Move_Speed
- imported_at: 2026-07-10T07:11:19+00:00

Reference extract:

Move Speed is a stat that heroes start with and can obtain more through items. Move speed dictates how many meters per second the hero will move.

See also: Movement Slow

Move Speed is an important stat in overall movement, as it affects how quickly one can reach their destination.

Some heroes have Spirit Scaling affecting their Move Speed and Sprint Speed. See "Base Move and Sprint Speed" table below.

### Sprint Speed

Sprint Speed is a related stat that is conditionally added to a hero's move speed when a hero is out of combat for five seconds, and persists until entering combat or zooming in. Zooming in while sprinting resets the player's speed back to base move speed.

If the hero has more than 2.5m/s Sprint Speed, the rest of the sprint speed will be added to the hero's movement at a rate of 0.6m/s as the player moves. While capped at the hero's Sprint Speed stat, sprinting will continue building up past its current max value, meaning bonuses applied while sprinting (e.g. Healing Rite) will instantly increase current Move Speed. Taking damage, getting Stunned, Immobilized, Displaced or Slept, using a Zipline, or stopping movement input will reset this counter.

### Slide

Heroes moving above 8.9 m/s can slide on a flat horizontal surface by crouching.

## Calculation

### Calculating Move Speed

While items often display movement speed bonuses as flat values (e.g., +2 m/s), multiple sources of move speed do not simply add together. Instead, they stack multiplicatively using a similar formula to resistance, meaning each additional source provides diminishing returns.

To find your effective move speed bonus, use the following formula:

Effective Move Bonus=12×(1−(1−B112)×(1−B212)…)

Where B₁, B₂, etc. are individual move speed bonuses.

Then calculate your total speed:

Total Speed=Base Move Speed+Effective Move Bonus+Base Sprint Speed+Sprint Bonus1+Sprint Bonus2…

Example: If you have two sources of move speed, one providing +2 m/s and another providing +3 m/s:

- Divide each bonus by 12: ≈0.167 and 0.25.

- Subtract from 1: (1 - 0.167) = 0.833 and (1 - 0.25) = 0.75.

- Multiply the remainders: 0.833 × 0.75 = 0.625.

- Subtract from 1: 1 - 0.625 = 0.375.

- Multiply by 12: 0.375 × 12 = 4.5 m/s (exact).

- Your Effective Move Bonus is 4.5 m/s (not 5 m/s).

If your hero has 6.5 base move speed, 1.6 base sprint speed, and no sprint bonuses: 6.5+4.5+1.6=𝟏𝟐.𝟔 m/s

### Sprint Speed Stacking

Unlike move speed, sprint speed stacks additively with no diminishing returns. If you have base 1.6 sprint speed and get items with +2 and +5 sprint speed, you simply have 8.6 sprint speed.

Total Sprint=Base Sprint+Bonus1+Bonus2…

### Combined Example

A hero with:

- 6.4 base move speed

- 1.6 base sprint speed

- +2 and +3 move speed bonuses

- +2 and +1.5 sprint speed bonuses

Step 1: Calculate Move Speed 12×(1−(1−212)×(1−312))=4.5 m/s effective 6.4+4.5=𝟏𝟎.𝟗 m/s

Step 2: Calculate Sprint Speed 1.6+2+1.5=𝟓.𝟏 m/s

Step 3: Add Together 10.9+5.1=𝟏𝟔.𝟎 m/s

## Base Move and Sprint Speed

Values referenced from Hero Comparison Table.

Total Speed is the sum of Move Speed and Sprint Speed.

### Base Move Speed Stats

| Hero | Move Speed (m/s) | Sprint Speed (m/s) | Total Speed (m/s) | MS Spirit Scaling | SS Spirit Scaling |

| --- | --- | --- | --- | --- | --- |

| Abrams | 6.4 | 1.6 | 8 | +0 | +0 |

| Apollo | 7.2 | 1.6 | 8.8 | +0 | +0 |

| Bebop | 6.45 | 4 | 10.45 | +0 | +0 |

| Billy | 7 | 1.6 | 8.6 | +0 | +0 |

| Calico | 6.8 | 1.6 | 8.4 | +0 | +0 |

| Celeste | 6.2 | 1.6 | 7.8 | +0 | +0 |

| The Doorman | 7.9 | 1.6 | 9.5 | +0 | +0 |

| Drifter | 6.9 | 1.6 | 8.5 | +0 | +0 |

| Dynamo | 6.7 | 1.6 | 8.3 | +0 | +0 |

| Graves | 7 | 2.2 | 9.2 | +0 | +0 |

| Grey Talon | 6.3 | 1.6 | 7.9 | +0.0084 | +0 |

| Haze | 8.2 | 1.6 | 9.8 | +0 | +0 |

| Holliday | 8.2 | 1.6 | 9.8 | +0 | +0 |

| Infernus | 6.7 | 1.6 | 8.3 | +0 | +0 |

| Ivy | 7.2 | 1.6 | 8.8 | +0 | +0 |

| Kelvin | 6.7 | 1.1 | 7.8 | +0 | +0 |

| Lady Geist | 6.3 | 2.4 | 8.7 | +0 | +0 |

| Lash | 7.2 | 2.1 | 9.3 | +0 | +0 |

| McGinnis | 6.7 | 1.6 | 8.3 | +0 | +0 |

| Mina | 6.5 | 1.6 | 8.1 | +0 | +0 |

| Mirage | 7 | 1.6 | 8.6 | +0 | +0 |

| Mo & Krill | 8 | 1.6 | 9.6 | +0 | +0 |

| Paige | 6.9 | 3.5 | 10.4 | +0 | +0 |

| Paradox | 6.7 | 1.6 | 8.3 | +0 | +0 |

| Pocket | 7.2 | 1.6 | 8.8 | +0 | +0 |

| Rem | 7.2 | 4 | 11.2 | +0 | +0 |

| Seven | 6.7 | 1.8 | 8.5 | +0 | +0 |

| Shiv | 6.5 | 1.6 | 8.1 | +0 | +0 |

| Silver | 6.7 | 1.5 | 8.2 | +0 | +0 |

| Silver (Transformed) | 6.7 | 1.5 | 8.2 | +0 | +0 |

| Sinclair | 7.2 | 1.6 | 8.8 | +0.0138 | +0 |

| Venator | 6.4 | 1.5 | 7.9 | +0 | +0 |

| Victor | 6.3 | 1.1 | 7.4 | +0 | +0 |

| Vindicta | 7.9 | 1.6 | 9.5 | +0 | +0 |

| Viscous | 7.2 | 1.6 | 8.8 | +0 | +0 |

| Vyper | 6.9 | 1.6 | 8.5 | +0.0138 | +0 |

| Warden | 6.3 | 1.6 | 7.9 | +0 | +0 |

| Wraith | 7.2 | 1.6 | 8.8 | +0 | +0.05 |

| Yamato | 8.2 | 1.6 | 9.8 | +0 | +0 |

## Sources

### Move Speed

| Name | Cost | Category | Stat change |

| --- | --- | --- | --- |

| Active Reload | 1,600 | Weapon | +0.75m/s Move Speed |

| Fleetfoot | 1,600 | Weapon | +3m/s Move Speed |

| Stalker | 1,600 | Weapon | +1.5m/s Move Speed |

| Blood Tribute | 3,200 | Weapon | +2m/s Move Speed |

| Burst Fire | 3,200 | Weapon | +1.25m/s Move Speed |

| Headhunter | 3,200 | Weapon | +1.75m/s Move Speed |

| Heroic Aura | 3,200 | Weapon | +2.25m/s Move Speed |

| Sharpshooter | 3,200 | Weapon | -0.7m/s Move Speed |

| Weighted Shots | 3,200 | Weapon | -0.5m/s Move Speed |

| Frenzy | 6,400 | Weapon | +4m/s Move Speed |

| Enduring Speed | 1,600 | Vitality | +2m/s Move Speed |

| Guardian Ward | 1,600 | Vitality | +2.75m/s Move Speed |

| Counterspell | 3,200 | Vitality | +1.75m/s Move Speed |

| Dispel Magic | 3,200 | Vitality | +2m/s Move Speed |

| Fortitude | 3,200 | Vitality | +1.5m/s Move Speed |

| Veil Walker | 3,200 | Vitality | +3.5m/s Move Speed |

| Divine Barrier | 6,400 | Vitality | +2.75m/s Move Speed |

| Healing Tempo | 6,400 | Vitality | +1.25m/s Move Speed |

| Juggernaut | 6,400 | Vitality | +2.5m/s Move Speed |

| Cloak of Opportunity | Legendary | Vitality | +3m/s Move Speed |

| Radiant Regeneration | 3,200 | Spirit | +1.75m/s Move Speed |

| Surge of Power | 3,200 | Spirit | +1.75m/s Move Speed |

| Ethereal Shift | 6,400 | Spirit | +3m/s Move Speed |

| Shrink Ray | Legendary | Spirit | +5m/s Move Speed |

| Unstable Concoction | Legendary | Spirit | +10m/s Move Speed |

- Metal Skin, when activated, provides -1.5 m/s Move Speed Penalty

### Sprint Speed

| Name | Cost | Category | Stat change |

| --- | --- | --- | --- |

| Long Range | 1,600 | Weapon | +0.75m/s Sprint Speed |

| Swift Striker | 1,600 | Weapon | +0.75m/s Sprint Speed |

| Heroic Aura | 3,200 | Weapon | +1.5m/s Sprint Speed |

| Hunter's Aura | 3,200 | Weapon | +0.75m/s Sprint Speed |

| Shadow Weave | 3,200 | Weapon | +1.5m/s Sprint Speed |

| +5m/s Sprint Speed |  |  |  |

| Sharpshooter | 3,200 | Weapon | +1m/s Sprint Speed |

| Healing Rite | 800 | Vitality | +2m/s Sprint Speed |

| Sprint Boots | 800 | Vitality | +2m/s Sprint Speed |

| Trophy Collector | 1,600 | Vitality | +2m/s Sprint Speed |

| Rescue Beam | 3,200 | Vitality | +0.75m/s Sprint Speed |

| Veil Walker | 3,200 | Vitality | +2m/s Sprint Speed |

| Golden Goose Egg | 800 | Spirit | +1m/s Sprint Speed |

| Rusted Barrel | 800 | Spirit | +0.5m/s Sprint Speed |

| Mystic Slow | 1,600 | Spirit | +0.75m/s Sprint Speed |

| Slowing Hex | 1,600 | Spirit | +0.5m/s Sprint Speed |

| Disarming Hex | 3,200 | Spirit | +0.75m/s Sprint Speed |

| Lightning Scroll | 6,400 | Spirit | +0.75m/s Sprint Speed |

| Vortex Web | 6,400 | Spirit | +0.75m/s Sprint Speed |

- Trophy Collector also grants 0.15m/s Sprint Speed for each stack.

### Map Spawns

- Powerup runes can provide a temporary Movement buff that provides +1.5m/s to +4m/s Sprint Speed for 160 seconds (scaling with game time from 5 to 40 minutes).

- After taking a teleporter, there is a temporary move speed buff.

- Vent tunnels provide a 70% boost to Move Speed. Sprint Speed is not multiplied by this boost.
