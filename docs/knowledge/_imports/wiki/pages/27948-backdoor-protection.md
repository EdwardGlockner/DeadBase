# Backdoor Protection

Imported reference

- kind: pages
- source: Deadlock Wiki
- url: https://deadlock.wiki/Backdoor_Protection
- imported_at: 2026-07-10T07:06:17+00:00

Reference extract:

Backdoor Protection is a type of Damage Resistance applied to Structures when they have no enemy Troopers nearby.

## Overview

Backdoor Protection is indicated by a green circle effect surrounding the structure and the text "Protected" with a green heart icon under its health bar.

Every structure except for Lane Guardians has backdoor protection. Lane Guardians only have protection in the Street Brawl mode.

Backdoor Protection can be removed by pushing the trooper wave up to the structure. For base structures, having any zipline pushed up to the base will remove protection. Once protection has been removed, it has a 14s buffer before it's applied again.

Destroying a structure with backdoor protection will instantly push the team's zipline up to the destroyed structure, regardless of it's original progress.

The Backdoor health regen only heals the Structure up to the HP it had before it was attacked under protection. The only structure that can heal up to 100% health out of combat is the Patron, who has 120 HP/s out of combat regen.

### Backdoor Protection stats

| Structure | Damage Resist (%) | Health Regen (HP/s) |

| --- | --- | --- |

| Walker | 65 | 65 |

| Base Guardian | 65 | 65 |

| Shrine | 65 | 65 |

| Patron | 65 | 75 |

Additionally, Shrines are invulnerable to damage until a pair of Base Guardians has been destroyed.

Base Guardians and Shrines also have a separate Bullet Resist stat that starts at 40% for Base Guardians and 60% for Shrines, decaying by 20% for each enemy hero nearby, up to 0% minimum.

## DPS calculation

The DPS dealt to a structure with backdoor protection can be calculated as follows:

Final DPS=[Base DPS×(1−Backdoor Resist)×(1−Additional Resists)]−Health Regen

So for example, in a scenario where the player is attacking a backdoor Walker with no additional resists, they need to deal a minimum of 189 DPS (rounded up) to damage it:

1=[188,57×(1−0,65)]−65

## Navigation
