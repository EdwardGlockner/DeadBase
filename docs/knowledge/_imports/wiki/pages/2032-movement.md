# Movement

Imported reference

- kind: pages
- source: Deadlock Wiki
- url: https://deadlock.wiki/Movement
- imported_at: 2026-07-10T07:11:19+00:00

Reference extract:

In Deadlock, there are a variety of methods for traversing the map.

Pressing Space next to a wall will cause the character to perform a Wall Jump, which does not consume stamina. You can Wall Jump multiple times per jump, but each Wall Jump after the first one costs 0.5 stamina and incurs a fatigue that reduces the height of successive jumps. This fatigue recovers non-linearly[Citation needed] over the course of 1.25 seconds and recovers completely upon landing. Using a heavy melee while airborne will also incur fatigue.

### Air Dash

Dashing midair can be done similarly to a grounded dash. A dash performed in the air is called an Air Dash, and consumes the same amount of stamina as a grounded dash. You can Air Dash only once per jump, but this limit can be expanded to two with the Vitality Item Stamina Mastery.

### Dash Jump

A Dash jump is a fast long jump, which can be performed as an additive input during a dash during a set timing window and which costs 1 stamina, for a total of 2 stamina. The timing of a dash jump is visualized by the stamina bars under your crosshair turning blue while dashing. While the crosshair is blue, the player can press jump to dash jump.

### Down Dash

Double tapping crouch midair performs a down dash, allowing the player to return to the ground quickly. This consumes 0.51] stamina. You can Down Dash only once per jump. This can be expanded to two with the Vitality Item Stamina Mastery.

### Mantle

Mantling is the act of climbing a nearby ledge. If a player holds the crouch key (default: Ctrl) while mantling, they will slide after climbing up, which is called a Mantle Glide.

If the player is hit by a melee attack while mantling, they will get an 80% Movement Slow, which will taper down to 20% over 2s.

### Stamina

Stamina management is an important aspect of player movement.

## Map features

There are multiple elements on the map that let players move uniquely.

### Jump Pads

Jump Pads are small vents that push heroes through the air after standing on them.

### Ropes

Ropes dangle from the roofs of buildings or inside buildings, allowing heroes to access rooftops or additional floors, and facilitate vertical traversal.

### Teleporter

There are multiple pairs of teleporters throughout the map that can be entered to quickly traverse left and right across the map.

### Ziplines

Ziplines are the most prominent method of traversal, as the heroes spawn riding the lines. They connect the opposing bases together and facilitate fights.

## Advanced Movement

As a physics based game, several principles in the real world are also modeled in-game. However, quirks with the game engine allow unique movement options that are not readily apparent.

### Melee Jump

Melee jumping is the technique of using a heavy melee timed with a Wall Jump to go up without double jumping, thus saving a Stamina bar.

### Corner Boost

Corner boosting is a technique that exploits the game's wall jump mechanics to achieve greater vertical velocity than a standard wall jump. The effect is believed to occur due to the following implementation behavior:

- Velocity Reset on Wall Jump Initiation – When a wall jump is performed, the game first sets the character's velocity to a fixed absolute value.

- Collision Normal Calculation – The game determines the direction of the jump by using the normal vector of the character's collision capsule at the nearest point of contact with the wall.

- Upward-Angled Normals on Corners – Because the collision capsule is rounded, the normal vector near a corner can point diagonally upward or downward rather than purely sideways. When the normal is angled upward, the resulting velocity is applied at a steeper angle, leading to increased upward momentum.

#### Visual Comparison

- Normal Wall Jump – Final velocity is directed primarily sideways, following a standard wall jump.

- Corner Boost – Final velocity is angled higher due to the upward-tilting normal, resulting in a stronger ascent.

| Column 1 | Column 2 |

| --- | --- |

| Corner Boost Normal Wall Jump | Key ■ Light Blue: Collision capsule ■ Red: Absolute velocity ■ Green: Sideways velocity ■ Orange: Wall push ■ Purple: Final velocity |

### Dropdown Corner Boost

Same as Corner Boost, Dropdown Corner Boost can be done on any edge in the game. To perform it, drop down from an edge and wall jump to gain extra height without using stamina.

### Friction

### Dash Jump Cancel

Dash Jump Canceling is a technique that allows for Jumping immediately after a Dash without performing a Dash Jump. After performing a Dash for a short duration it is possible to spend 1 Stamina to perform a Dash Jump. Casting an ability during the Dash Jump window will immediately cancel it. This can then be followed up with a normal Jump. When done correctly a Dash Jump Cancel can be used to travel further than a Dash.

Only some abilities provide a benefit when used to Dash Jump Cancel. Abilities with long cast time or abilities that slow movement during cast provide almost no benefit.

### Abilities that can be used to Dash Jump Cancel

| Hero | Ability | Notes | Billy | Calico | Doorman | Drifter | Dynamo | Grey Talon | Haze | Holliday | Infernus | Ivy | Kelvin | Lady Geist | Lash | McGinnis | Mina | Mirage | Mo & Krill | Paige | Paradox | Pocket | Seven | Shiv | Sinclair | Vindicta | Viscous | Vyper | Warden | Wraith |

| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |

| Billy | Blasted |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |

| Chain Gang |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |

| Calico | Gloom Bombs |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |

| Doorman | Doorway | Only works when placing the doors. |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |

| Luggage Cart |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |

| Drifter | Stalker's Mark |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |

| Dynamo | Rejuvenating Aurora | Requires Rejuvenating Aurora to be upgraded to T3. |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |

| Grey Talon | Spirit Snare |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |

| Haze | Sleep Dagger |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |

| Smoke Bomb |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |

| Holliday | Powder Keg |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |

| Bounce Pad | Provides a significant increase in velocity. |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |

| Infernus | Napalm |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |

| Ivy | Entangling Thorns |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |

| Kudzu Connection |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |

| Kelvin | Frost Grenade |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |

| Frozen Shelter | It is possible to cancel the Frozen Shelter before hitting the wall. |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |

| Lady Geist | Essence Bomb |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |

| Malice | Casting Malice requires the caster to wait before they can jump, which makes the Dash Jump Cancel significantly harder. Malice Dash Jump Cancel cannot be followed up with a slide without items that increase move speed. |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |

| Lash | Flog |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |

| McGinnis | Mini Turret |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |

| Medicinal Specter |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |

| Spectral Wall |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |

| Heavy Barrage | Due to the slow Heavy Barrage Dash Jump Cancel cannot be followed up with a slide without items that increase move speed. |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |

| Mina | Rake |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |

| Mirage | Fire Scarabs | Each separate cast can be Dash Jump Canceled. |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |

| Djinn's Mark |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |

| Mo & Krill | Scorn |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |

| Sand Blast |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |

| Paige | Conjure Dragon |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |

| Captivating Read |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |

| Paradox | Pulse Grenade |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |

| Kinetic Carbine |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |

| Paradoxical Swap |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |

| Pocket | Flying Cloak |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |

| Seven | Lightning Ball |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |

| Static Charge |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |

| Power Surge |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |

| Shiv | Serrated Knives | Casting Serrated Knives requires the caster to wait before they can jump, which makes the Dash Jump Cancel significantly harder. Serrated Knives Dash Jump Cancel cannot be followed up with a slide without items that increase move speed. |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |

| Bloodletting |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |

| Sinclair | Vexing Bolt | Casting Vexing Bolt requires the caster to wait before they can jump, which makes the Dash Jump Cancel significantly harder. Vexing Bolt Dash Jump Cancel cannot be followed up with a slide without items that increase move speed. |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |

| Spectral Assistant |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |

| Rabbit Hex |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |

| Vindicta | Stake |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |

| Crow Familiar | Crow Familiar Dash Jump Cancel cannot be followed up with a slide without items that increase move speed. |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |

| Assassinate | Requires the ability to be fully cast and unscoped before jumping to be able to be followed up with a slide. |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |

| Viscous | Splatter | Splatter Dash Jump Cancel cannot be followed up with a slide without items that increase move speed. |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |

| Puddle Punch |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |

| Vyper | Screwjab Dagger |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |

| Lethal Venom |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |

| Petrifying Bola |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |

| Warden | Alchemical Flask |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |

| Willpower | Willpower Dash Jump Cancel cannot be followed up with a slide without items that increase move speed. |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |

| Binding Word |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |

| Wraith | Card Trick | Card Trick Dash Jump Cancel cannot be followed up with a slide without items that increase move speed. |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |

| Full Auto |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |

| Telekinesis |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |

## Movement abilities

Certain abilities are classified in-game as Movement Abilties. These abilities are disabled by the Spirit Item Slowing Hex.

| Hero | Ability | Description |

| --- | --- | --- |

| Abrams | Shoulder Charge | Charge forward, pulling enemies you hit. Pushing a hero into a wall applies stun.If you collide with a hero you move faster during your charge. |

| Seismic Impact | Leap high into the air and choose a ground location to crash into. When you hit the ground, all enemies in the radius are damaged and stunned. |  |

| Calico | Leaping Slash | Dash forward before slashing all enemies in a circle, dealing Light Melee Damage. |

| Ava | Turn to shadows and possess Ava. You gain Movement Speed and become Hidden on the Minimap, but cannot attack or cast abilities. |  |

| Return to Shadows | Instantly turn to shadows, becoming Untargetable, gaining Movement Speed, and dealing Damage. |  |

| Dynamo | Quantum Entanglement | Dynamo briefly disappears into the void and then reappears a short distance away. On reappearing, your weapon is reloaded and has a fire rate bonus for the next clip (Max 8s). |

| Grey Talon | Rain of Arrows | Launches you high in the air, allowing you to glide slowly. While airborne, you gain Weapon Damage and multishot on your weapon. Alt-Cast for reduced jump height. Press Space to cancel the glide. |

| Haze | Smoke Bomb | Fade out of sight, becoming invisible and gaining sprint speed. Attacking removes invisibility. Close enemies can see through your invisibility. |

| Holliday | Bounce Pad | Drop a bounce pad in the world that launches any hero. |

| Infernus | Flame Dash | Move forward at high speed and leave a flame trail that burns enemies. Infernus gains 50% slow resistance for the duration. |

| Ivy | Air Drop | Take flight with an ally or a bomb. Drop your ally or bomb to cause a large explosion that causes movement slow. Ivy and ally gain a bullet shield when flying ends. While lifted, your ally gains bullet resist but cannot attack and deals -50% damage. Air Drop has faster cast time when targeting an ally. |

| Kelvin | Ice Path | Kelvin creates a floating trail of ice and snow that gives movement bonuses to him and his allies. Kelvin gains 60% slow resistance for the duration. Enemies can also walk on the floating trail. Press Shift / Ctrl to travel up or down while in Ice Path. |

| Lash | Grapple | Pull yourself through the air toward a target. Using Grapple also resets your limit of air jumps and dashes. |

| Mirage | Tornado | Transform yourself into a tornado that travels forward, damaging enemies and lifting them up in the air. After emerging from the tornado you gain bullet evasion. |

| Traveler | Channeled. Target an ally or visible enemy hero on the minimap, then teleport to where they were when your channel started. After teleporting, you gain movement speed as well as fire rate until your next reload. |  |

| Mo & Krill | Burrow | Burrow underground, moving faster, and gaining spirit and bullet armor. Damage from enemy heroes will reduce the speed bonus. When you jump out, knock enemies into the air and perform a spin attack that damages and slows. Cooldown starts when Burrow ends. |

| Paradox | Paradoxical Swap | Fire a projectile that swaps your position with the target enemy hero. While the effect occurs, you gain spirit lifesteal and the enemy takes damage over time. |

| Pocket | Flying Cloak | Launch a sentient cloak that travels forward and damages enemies. You can press 2 to teleport to its location. |

| Shiv | Slice and Dice | Perform a dash forward, damaging enemies along the path. Ultimate Unlock: While rage is full an echo of Shiv retraces the dash path after a short delay, damaging enemies again. |

| Sinclair | Spectral Assistant | While the Assistant is out, you can press [2] to swap positions with your Assistant. |

| Vindicta | Flight | Leap into the air and fly. While in flight your weapon deals bonus spirit damage. |

| Viscous | Goo Ball | Morph into a large goo ball that deals damage and stuns enemies on impact. The ball grants large amounts of Bullet and Spirit resist, bounces off walls and can double jump. |

| Vyper | Slither | You have increased Slide Distance, can Slide up hills, and can turn faster while Sliding. |

| Warden | Willpower | Gain a spirit shield and bonus movement speed. |

| Wraith | Project Mind | Teleport to the targeted location. |

| Yamato | Flying Strike | Throw a grappling hook to reel yourself towards an enemy, damaging and slowing the target when you arrive. |

## Trivia

Prior to the April 17, 2025 update, players could use Heavy Melee Cancel to maintain momentum from a Heavy Melee attack. However, the update significantly reduced the momentum preservation, making the technique nearly ineffective for movement purposes.

## References

## Navigation
