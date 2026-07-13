# Console commands/ru

Imported reference

- kind: pages
- source: Deadlock Wiki
- url: https://deadlock.wiki/Console_commands/ru
- imported_at: 2026-07-10T07:07:26+00:00

Reference extract:

Console commands allow you to modify gameplay settings. Pressing F7 will open the developer console, which allows you to run commands.

- In the <installation path>\steamapps\common\Deadlock\game\citadel\cfg folder create a text file name it autoexec.cfg

- Put the console commands that you want to run on startup of Deadlock in the autoexec.cfg file, one console command on each line and save it

- In the Steam app right-click Deadlock in your list of games on the Library tab and select Properties...

- In the "LAUNCH OPTIONS" field enter -console -exec autoexec

## Hosting Custom Games

- You may want to pause the game immediately after joining by pressing P to give other players time to join the match.

- Find a green line in the console that looks like this: [Client] steamid : [A:1:XXXXXXXXXX:XXXXX] (XXXXXXXXXXXXXXXXX) (the Xs will be replace with numbers)

- Select the part after steamid that looks like this, including the square brackets: [A:1:XXXXXXXXXX:XXXXX]

- Right click and choose "Copy Selected Text"

- The host sends players the ID they just copied. Players can now connect to the game by opening their console and running connect [A:1:XXXXXXXXXX:XXXXX] (replace the part after connect with the ID they got from the host).

- Upon joining, players will be able to select their team and hero. To bring up this menu again, players can run changeteam 0.

- If you ever want to restart the game, the host can run changelevel street_test .

### Adding Bots

- If you're already in a game, you can perform these steps then run changelevel dl_midtown to restart the game instead of starting a new one.

- Run citadel_spawn_practice_bots false so that bots won't spawn immediately when the game starts.

- Run citadel_spawn_practice_bots_count 12 to ensure that bots fill all remaining slots (they'll be added until both teams have 6 players).

- You can use citadel_pregame_duration before starting the game to increase the duration of the pregame if you want.

- The team/hero menu can be a bit glitchy. Players can use the changeteam command instead (see table above for command description).

- Remember to choose your (the host's) own team and hero as well. This may automatically unpause the game - press P after selecting a team to pause again.

- After all human players have joined teams and selected heroes, the host runs citadel_spawn_practice_bots true, then presses P again to unpause the game. Bots should fill the remaining slots on each team.
