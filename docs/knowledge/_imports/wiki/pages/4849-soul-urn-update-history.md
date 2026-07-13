# Soul Urn/Update history

Imported reference

- kind: pages
- source: Deadlock Wiki
- url: https://deadlock.wiki/Soul_Urn/Update_history
- imported_at: 2026-07-10T07:13:12+00:00

Reference extract:

| Update | Changes |

| --- | --- |

| July 9, 2026 | Urn Runner sprint bonus reduced from +2m to 0 (trailing bonus reduced from +7m to +5m). Urn Runner move speed bonus reduced from +3.5m to +2m. Urn Runner Stamina Recovery increased from +15% to +25%. Urn talking frequency increased from every 8s to every 6s. Urn talking sound distance increased (easier to hear a nearby Urn Runner). |

| June 30, 2026 | Urn running is now its own objective. Spawns on either end of the map (where the previous neutral pickup locations were), and gets delivered to the opposite end. Spawns at 10/15/20/25/etc. Urn runner is no longer revealed and is not disarmed or silenced (going through a doorway or mirage teleport still drops it) Urn cannot be manually dropped. It gets dropped when you get hit with a light or heavy melee, are stunned or are killed. It stays where it drops and does not walk back home. Urn runner can no longer parry Urn bounty value starts decaying after 45s from being picked up. It drains gradually over another 45s and then the urn is removed when the bounty is empty. Urn is deposited immediately at the drop off point. Urn bounty when deposited is worth 250 + 70/min for just the urn runner. Still has the comeback bounty component. Upon deposit all of the souls are released as orbs into the air (if another ally secures the orbs, they share the bounty with the urn runner). Urn runner gets +4 permanent buffs on deposit Urn is now louder when it talks and is easier to hear by nearby enemies After 3 Minutes from spawn the Urn will start walking very slowly on his own towards the deposit location Urn runner's passive bonuses while holding it now scales based on how behind you are, rather than being on or off (same as the Unstable Rift 0%-15% NW linear scaling). Bonuses are the same as the previous urn runner bonuses. Debug command: citadel_force_spawn_idol - This spawns the Soul Urn. |

| June 11, 2026 | Urn give up time reduced from 75s to 60s Urn bounty reduced by 10% (unreduced for trailing team) (Undocumented) New voice lines for the Urn during depositing phase |

| June 4, 2026 | Urn mechanics have been reworked. Primary details: Delivering the urn now starts a king of the hill style capture point, rather than using melee to flip the urn back and forth. Both teams can progress at the same time, but the urn will only be fully claimed once there is only one team in the circle. The Urn runner now gets their normal 35% bonus bounty and stats immediately on initial deposit (rather than on deposit conclusion only if your team won it) Other Details: Urn overall bounty reduced by 20% (unreduced for trailing team) Progress radius is 20m Progress rate is fixed regardless the number of allies in the area Progress duration for favored/neutral/unfavored is 6/12/18s If Urn has been in progress for over 75s, it will give up and throw all the souls as orbs into the sky (they will float for a long time) Increased time allowed to run the urn before taking damage by 10s Trailing team sprint speed bonus from +4m to +5m Urn comeback resistance now also grants +35% Debuff Resistance ontop of the 35% Bullet and Spirit Resistance Urn comeback resistance aura reduced from 60m to match the 20m progress radius Drop off location is above the bridges on the side lanes, rather than below. |

| May 28, 2026 | Urn spawn time and interval changed from 10/15/20/25/etc to 12/18/24/30/etc Urn timer now gets frozen with Frozen Shelter Urn no longer provides the +35% Bullet and Spirit Resist aura for the behind team when it is being carried or dropped. The aura is now only active when it is being deposited. Urn runner when behind now gains +35% Bullet and Spirit Resist for themselves only Fixed the trailing team Urn runner's extra sprint bonus not working properly Urn will do damage to the runner after a team has held it for 30s (was 50s before), however, this timer will freeze while there are enemies within a 40m radius of the urn runner. Urn will now always add at least 2s to the team 30s held timer limit anytime it is picked up, even if it is instantly dropped You are no longer prevented from picking up the Urn for 12s after it is dropped after the previous 50s team held timer The conditions for when the Urn decides to run back home have been reworked. The Urn will now stay in place on the ground as long as there are enemies in a 40m radius (enemies of the last person to have dropped or fumbled the Urn). If there are no enemies, then the Urn will wait up to 13s if there is a friendly player in a 40m radius. If the Urn held timer is over 45s (keeping in mind this timer is frozen if there are nearby enemies), the next time it is dropped it will immediately run back home if there are no nearby enemies. |

| May 25, 2026 | Urn drop off point moved from the above bridge in the mid lane to under the bridge in the side lane. Urn timer extension when contested increased from 1.25s to 3s. Urn deposit timers for favored/neutral/unfavored increased from 3/5/10s to 5/10/15s. Urn comeback bullet and spirit resist auras reduced from 50% to 35%. Urn pickup spot is now where the old comeback drop off spots were for when your team is behind. Urn runner no longer has sprint disabled. Urn runner now has max sprint acceleration. Urn runner now gains +2m Sprint, +1 Stamina, +10% Dash Distance and +15% Stamina Regen. Urn runner for the team that is behind now gains an extra +4m Sprint. Urn collision radius increased by 20%. Various smaller urn holding timers and variables adjusted to account for the new location. |

| May 22, 2026 | We are experimenting with an alternate set of Urn mechanics. Please give us your thoughts on this after you've played with it some. Primary Rules: To pickup the Urn, rather than standing in place to channel, you now light or heavy melee the Urn to pick it up. The Urn is now always dropped off on top of the bridge on the middle of the map. Once dropped off, the Urn will go into a "Depositing" phase for a set amount of time, depending on which team the urn favors (3s/5s/10s for Favored/Neutral/Unfavored). While in the Depositing phase, the enemy team can Heavy Melee the urn to have their team claim it and cause it to switch sides. This adds +1.25s to that team's timer. If the urn is Favored or Unfavored (in a comeback state), then the Favored team will get +50% Bullet and Spirit Resist in a 60m radius around the urn while it is being carried, dropped or deposited. Other Details: After 35s (aggregate time held per team), the carrier will start taking 5% Max HP damage per second (previously was 45s and 1.5% Max HP damage). Urn damage is lethal Like before, when the Urn is fumbled, it will wait 13s if there is a player within 25m. However afterwards, with this new version, it can no longer be picked up anymore and will very quickly run back to its spawn position. No longer silences you while carrying. You are still disarmed and movement silenced. No longer grants +30% Bullet and Spirit Resist while carrying it Area around deposting the urn is revealed (urn runner is also revealed as usual) The rules for Favored/Unfavored remain the same (+15% soul difference for the first urn at 10:00, +10% for all future urns) Souls are all instant after the deposit is complete All rewards are the same. The last person to contest the urn gets the +3 Golden Idol buffs, falling back to the original carrier if nobody contested it. |

| March 6, 2026 | Minimap now indicates if the Urn is a favored, neutral or unfavored |

| January 20, 2026 | Urn no longer requires a drop off channel time Urn is now knocked out of your hands with a light melee (instead of only with a heavy melee) Urn pickup channel time is reset if you get hit with a light or heavy melee Can no longer parry while channeling to pickup the urn Urn carrier resist reduced from 50% to 30% Urn now drops if it travels through doorman portals |

| December 16, 2025 | Urn: Bounty increased from 700 + 230/min to 1300 + 230/min Urn: Comeback bounty now gives more souls Urn: Bullet and Spirit resist for carrier increased from 30% to 50% Urn: Bonus bounty for carrier increased from 25% to 35% |

| November 21, 2025 | Dropping / Throwing the Urn now causes Parry to go on CD Soul Urn no longer grants +1 AP to the person dropping it off Soul Urn now provides 4 Permanent Buffs to the person dropping it off |

| October 2, 2025 | Carriers now have +30% bullet and +30% spirit Resist Movespeed bonus reduced from +7m to +3.5m Damage taken when holding too long increased from 1% to 1.5% Max Health per second |

| June 17, 2025 | Time holding Urn before taking damage reduced from 90s to 45s (1% max health damage per second) Time Urn will Autorun back to Home regardless of nearby players reduced from 75s to 45s Time an Urn will wait for a nearby player to pick it up reduced from 20s to 12s |

| May 27, 2025 | Fixed a bug where Urn can be invisibly carried on the hero by throwing it in certain areas like the air vents. |

| April 17, 2025 | Urn now reveals you immediately. First urn is now considered for comeback mechanics (15% NW delta). Urn now has a visual indication on the model to indicate if its a side favored pickup. Urn will no longer wait indefinitely for someone nearby to pick him up. He'll ignore loiterers after 20 seconds in aggregate and start running back home. Fixed Debuff Resistance affecting Urn pickup time. |

| April 4, 2025 | Fixed Ivy, Viscous and Magic Carpet moving faster than desired when holding the soul urn. Urn reveal time reduced from 25s to 15s. Urn speed limit increased from 13 m/s to 15 m/s. |

| December 6, 2024 | Carrying Urn now sets and limits your movespeed to a fixed 13 (this includes things like Ivy Air Drop). It no longer provides sprint. The speed cannot be reduced or increased. Urn spawn point now alternates left and right starting with left, rather than being random. |

| November 21, 2024 | Urn time to reveal increased from 20s to 25s. Initial Urn bounty reduced from 4050 to 3000 (changed from 1750 + 230*Min to 700 + 230*Min). Adding an alternate Urn mechanic as an experiment for 2 days. This will be enabled this weekend only and Monday will be back to normal. Urn pickup location is the same, but drop-off location is now always at the top of mid temple. The bonus souls the team gets is reduced by 60% (the delivering player reward is unchanged). The reveal time is now 40s. |

| November 13, 2024 | First Urn is now always neutral regardless of NW lead. |

| November 7, 2024 | Biased Urn delivery locations moved slightly closer to neutral positions. Moved the stairs from the warehouse interior to the underground tunnel further from the Urn delivery location. |

| October 27, 2024 | NW lead requirement increased from 8% to 10%. |

| October 24, 2024 | Urn comeback properties now require an 8% net worth lead to kick in. If one team has a soul lead by at least 8%, the urn drop-off location will be closer to the losing team's side. If the Urn hasn't been delivered within 90 seconds (teamwide timer) of pickup time, it now drains the runner's health for 1% of Max HP per second. Regen is disabled during this. When the Urn is dropped after 90 seconds of pickup time, it starts moving back to its spawn point immediately and cannot be picked up by the same team for 12 seconds. Increased Urn walking speed. |

| October 10, 2024 | Increased the time you need to carry the urn before the urn nags about not being delivered. Urn now causes the runner to be revealed on the minimap. Heavy Melee against the urn runner now causes them to drop the urn. Urn delivery now gives each player on your team a Golden Statue permanent buff. Urn bounty increased by 15%. Urn now falls down from the sky a little bit faster. |

| September 29, 2024 | Urn now drops when teleporting with Mirage's Traveler. |

| September 12, 2024 | Added little spirit frog legs to the Soul Urn. Soul Jar return location effects will change color based on the captured state of the Soul Jar. |

| July 18, 2024 | Removed voice lines / fixed text that referenced the urn being delivered to the temple. Can no longer use the Teleporter while carrying the Urn. |
