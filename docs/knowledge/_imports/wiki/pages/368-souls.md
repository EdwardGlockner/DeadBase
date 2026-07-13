# Souls

Imported reference

- kind: pages
- source: Deadlock Wiki
- url: https://deadlock.wiki/Souls
- imported_at: 2026-07-10T07:13:12+00:00

Reference extract:

— Graves

Souls are a crucial element in Deadlock, serving both as currency and experience points (XP) for heroes. Players collect souls by various means, including shooting Soul Orbs released when Troopers die, taking Guardians/Walkers, killing enemy players, and finding Unsecured Souls in boxes or crates. The amount of souls earned from a kill is a Bounty. Unsecured souls are added to your total immediately but can drop upon death for other players to collect.

Every player starts the game with 600.

### First Blood bonus

- A player gets 125 bonus souls when they get the first kill in a match.

### Comeback Mechanics

When a team is behind on souls, there are some "comeback mechanics" that come into play to allow the losing team to quickly catch up.

- Killing an enemy hero will award up to 126.8% more souls if that hero is stronger than the killer team's average networth, regardless of which team is leading in souls.

- The Soul Urn will give additional souls to the team that is behind based on game duration and total soul deficit. (see Soul Urn for details)

- The losing team gains up to 26% more souls from Troopers, Denizens, Sinner's Sacrifices and Objectives, based on how behind they are (peaks at 20% max net worth difference). The first 3k in net worth difference is ignored. (This means that the first 3k souls should be subtracted when calculating comeback values, e.g. 100k to 105k is calculated as a 2k difference)

- After 10 minutes in a match, killing a player whose net worth is above 15% higher than the killer team's average net worth increases that player's respawn time. The increase varies based on the net worth difference and match duration, from +6s for 15% net worth at 10 minutes to +22s for 30% net worth at 25 minutes.

### Catch up Mechanics

Catch up mechanics allow for players with low net worth to catch up to the other players on their team.

- For example, if a team gathered 200 souls in the last second, the lowest player earns 5 extra souls.

## Gathering Souls

- Teams with fewer souls will gain more souls from all sources (see Comeback Mechanics).

### Soul Distribution

Hero kill souls are distributed between nearby players with the following rate:

- To count as an assister for a player kill, you have to have damaged them in the last 10 seconds.

### Hero Kill Soul Distribution

| Players | % share to each player | Total % |

| --- | --- | --- |

| 1 | 125% | 125% |

| 2 | 57% | 114% |

| 3 | 28% | 84% |

| 4 | 17% | 68% |

| 5 | 11% | 55% |

| 6 | 8% | 48% |

Additionally, for kills with two or more players, the player who got the kill receives bonus souls.

Trooper souls are distributed between nearby players with the following rate:

### Trooper Kill Soul Distribution

| Players | % share to each player | Total % |

| --- | --- | --- |

| 1 | 100% | 100% |

| 2 | 54% | 108% |

| 3 | 36% | 108% |

| 4 | 25% | 100% |

| 5 | 20% | 100% |

| 6 | 16% | 96% |

Soul distribution is the same regardless if the Trooper drops a Soul Orb or if it is killed by a melee attack.

### Denizens (Jungle Creeps)

- In order for Denizens to give souls to both players, both players must deal damage to the Denizen.

- Souls from Denizens are split between all allied players who dealt damage to said Denizens. Unlike Hero and Trooper souls, Denizen souls are always shared equally.

- Souls from Denizens are unsecured souls.

### Sinner's Sacrifices

- Some jungle camps contain one or two Sinner's Sacrifice machines, which grants souls to the player by hitting them with melee attacks. Those souls are unsecured.

### Breakables

- Chance for any given crate to drop souls when broken is approximately 60%

- [Souls Dropped] = 23 + 2.0*[Game Time in Minutes]

- For example: At 30:00 game time, a broken crate will drop 83 souls.

### Other

- Trophy Collector and Golden Goose Egg give the player passive souls per minute.

- Killing cockroaches in underground tunnels grants the player 1 soul each.

## Soul Orbs

Troopers release souls in Soul Orbs, unless they are killed by a Melee Attack. They drop two orbs on death, one that floats and one that falls on the ground. Each orb has 50% of the kill bounty. The ground orb cannot be denied (they appear as white to enemies) and remains for 18 seconds before disappearing (scaling to 40 seconds after 10 minutes).

The floating orbs spawn dark-colored, and can be shot and confirmed (or denied) once they light up. Ally orbs are green and enemy orbs are orange. Hitting an enemy orb will deny their souls and grant them to the player who hit it and nearby allies. The ally team has a "grace period" of roughly 80ms to confirm their orbs. If the orb "pops" without being claimed after roughly 1 second, it's automatically rewarded to nearby allies, and if there are no allies nearby the souls are lost.

The floating orbs may be shot or hit with a Melee Attack to claim the souls. Orbs can be claimed by a single bullet or pellet, regardless of damage. The bullet that hit the orb is refunded to the player's magazine. Certain abilities like Serrated Knives or Malice can also confirm or deny orbs.

Soul confirmation accounts for latency, which in some situations can cause the player to lose the orb even if they visually seem to have hit it first.

### Local Soul Sharing

When souls are to be shared, the game checks two distances to add allied heroes to the "pool" of heroes to split the received souls:

- 45m from the soul orb itself when it is broken

- 30m from the hero that killed the Trooper

If an allied hero is within either of these distances, souls are shared between the killer and those allied heroes.

### Soul Well

After 3 minutes of game time pass, a soul well that releases orbs worth 10 souls each appears in each team's base. Unlike regular orbs, these orbs only grant souls if they are confirmed, and they can be either green or orange-colored.

## Unsecured Souls

— The Hidden King's herald

Souls earned from killing Denizens and destroying Sinner's Sacrifice machines are unsecured and are lost on death. If a player dies with at least 50 + 5/minute unsecured souls they will be dropped in a Soul Container, which can be claimed by any player by hitting it with a Heavy Melee. Soul Containers will despawn after 3 minutes. These containers are marked with a circle icon on the Minimap and have a green glow effect. If a player dies with fewer than 50 + 5/minute unsecured souls, no Soul Container will drop—they are permanently lost.

Unsecured souls are converted into secured souls over time, meaning they will no longer be dropped on death. This conversion rate is dynamic:

- Percentage Drain: Each second, 0.5% of the player's current unsecured souls are converted. This means larger amounts of unsecured souls secure faster initially.

- Example at 10 Minutes: A player carrying 1,000 unsecured souls will secure them at a rate of roughly 7.9 souls/second (5 from percentage + ~2.9 base).

- Example at 20 Minutes: That same player carrying 1,000 unsecured souls will secure them faster, at a rate of roughly 9.2 souls/second (5 from percentage + ~4.2 base), due to the base rate scaling over time.

Unsecured souls may be spent in the shop, but are spent after secured souls. They are indicated by the silver-green ball on the Hero's hip known internally as a Soul Container, as well as in the number on the HUD with a red icon.

Unsecured souls count towards leveling up. However, if the player dies and loses those souls, they will remain at the last unlocked level but lose progress to the next level equivalent to their dropped souls.

On the character UI, the large souls number is the total number of secured and unsecured souls added together.

## Leveling Up

Gathering souls will gradually "level up" your hero, granting a variety of benefits. See boons for detailed information.

## Update history

View the full update history: Souls/Update history

| Update | Changes |

| --- | --- |

| July 9, 2026 | Objectives bounty split for nearby heroes reduced from 40% to 30% (this means slightly more portion of the bounty is split team wide rather than towards an individual player) |

| June 30, 2026 | First blood bounty reduced from 150 to 125 Base kill bounty reduced from 250 to 200 (max is still 2200 at 40m) Trooper bounty ratio in the deniable flying orb increased from 40% to 50% Minimum unsecured souls allowed to drop reduced from 150 to 50 + 5/min |

| June 11, 2026 | Kill comeback bounty values increased by 8% |

## References

## Navigation
