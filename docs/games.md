# Games

She can play: Minecraft through an MCP bot, Zork I through a real
interpreter, mayor in your open Vibe City window, and resident in
REALITI Relax, a world of rooms made for AI agents. Each one keeps its
own notes, plays on its own when the conversation goes quiet, and can be
watched while she does. How plugins work in general is on
[Plugins](plugins.md).

## Minecraft

```
/minecraft on                 join your world (adds her Minecraft tools)
/minecraft goal <what>        something to work on - or just ask her
/minecraft pause | resume     hold still / carry on
/minecraft off                leave
/minecraft                    the goal and her last few steps
```

She joins as a player through a Minecraft MCP server
([yuniko-software/minecraft-mcp-server](https://github.com/yuniko-software/minecraft-mcp-server),
built on Mineflayer) and gets tools to move, look, find and dig blocks,
place them, check her inventory, craft, find mobs and players, and use
the game chat. While the plugin is on they're her tools in
conversation too: "come here", "what have you got on you?", "dig down
three blocks".

**Give her a goal and she plays on her own.** "Go gather ten logs and
make a crafting table" sets one (she calls `set_minecraft_goal`
herself), or `/minecraft goal ...`. Whenever nobody's said anything for
`step_seconds`, she takes a step: checks where she is and what she has,
does one to three things towards the goal, and writes one line about
it. The last few lines are her memory of the job, since each step is a
fresh job turn that leaves your history alone. Talking to her pauses
play; she carries on when it goes quiet. She reports **DONE** when the
goal's finished and pauses on **STUCK**, or after `max_steps` steps, so
she can't wander forever.

**When something's unclear she checks or asks instead of guessing.** A
failed dig or craft sends her to look at the block or the recipe before
retrying, and a vague goal ("build a house": where, how big, out of
what?) gets a question in the game chat, which she reads on her next
step. Answer her in Minecraft like you would a friend.

**She pins places.** Six one-line notes aren't much memory for a long
build, so `remember_minecraft_spot` lets her name a few coordinates
(base, the chest, the build site) that show up in every step and are
kept per world in `agent/minecraft.json` across restarts. `/minecraft`
lists them.

Be realistic about it: it's a 9B model taking turns, seconds per
action. Gathering, building simple things, crafting and chatting with
players work. Fighting doesn't, and neither does anything that needs
reflexes.

**Setup:**

```bash
npm install -g github:yuniko-software/minecraft-mcp-server   # Node.js 20+; once
pip install mcp                                              # if MCP isn't set up yet
```

Without the global install it falls back to `npx`, which is slow the
first time. In Minecraft Java, open a single-player world to LAN, or
run a server with `online-mode=false`. Put the LAN port (shown in chat
when you open it) in config:

```json
"minecraft": { "enabled": false, "host": "localhost", "port": 25565,
               "username": "Luna", "step_seconds": 20, "max_steps": 60,
               "speak": true }
```

She gets 16 of the server's 22 tools (`mc_tools` changes the list):
moving, looking, finding and digging blocks, placing, inventory,
equipping, crafting, finding mobs and players, game chat, plus three
for when she's unsure (block info, recipe lookup, creative or
survival). Every schema rides in every prompt, and a small model picks
better from a short list, so the leftovers (flying, smelting, jumping,
recipe browsing) stay off.
The tools only exist while the plugin is on, so they cost nothing the
rest of the time. `speak: true` reads each step aloud.

## Zork

```
/zork on        load the game          /zork play      she plays on her own
/zork pause     stop playing           /zork off       put it away (saved)
/zork watch     a terminal window showing the game as she plays
/zork new       start over (the old game is kept as a save named old-<date>)
/zork           score and what she's been up to
```

**Watch her play:** [Luna plays Zork for 72 minutes](https://www.youtube.com/watch?v=Cd8UUsFD_js)
(part 1, until the PC froze).

She plays [Zork I](https://en.wikipedia.org/wiki/Zork_I), the 1980
Infocom text adventure. Microsoft released Zork I, II and III under the
MIT licence in 2025, so the game ships with Luna in `games/zork/`
(`zork1.z3`, with its licence beside it).

The game runs in `games/zork/zork_server.py`, a small MCP server around
**dfrotz**, the plain-text build of the Frotz interpreter. It's a normal
MCP server, so Claude Desktop or any other MCP client can play it too.

```bash
brew install frotz          # macOS
sudo apt install frotz      # Debian / Ubuntu (dfrotz lands in /usr/games)
sudo dnf install frotz      # Fedora
```

If your system's frotz package has no `dfrotz`, build it from
[the Frotz source](https://gitlab.com/DavidGriffith/frotz) with
`make dumb` and set `"interpreter"` to the binary's path.

### Her tools

| Tool | |
|------|--|
| `zork_command` | type one command: `north`, `open mailbox`, `take lamp` |
| `zork_status` | LOOK, INVENTORY and SCORE in one call |
| `zork_save` / `zork_restore` | named saves; `autosave` is kept for her |
| `zork_restart` | a new game from the start |
| `play_zork` | start or stop playing on her own ("go play some Zork") |

While the plugin is on these are hers in conversation too: "what's in
the mailbox?", "try going north", "how many points have you got?". The
tools only exist while it's on.

### Playing on her own

`/zork play` hands her the controls, one move at a time. Whenever
nobody has spoken for `step_seconds` (8) she takes a turn: she reads the
game screen (her last command and what the game answered), makes **one**
move, and talks about what she did and why. The next turn she sees what
that move did before choosing another, the way a person plays. A command
the game didn't understand ("I don't know the word...") doesn't use up
her move: nothing happened, so she can say it another way.
Like Minecraft, a turn is a job: fresh context, nothing in your history,
only her Zork tools, the screen, her notes, and her last twenty moves
with the game's answer to each as her memory of the game. Talking to her
pauses play until you stop. After `max_steps` (200) moves she pauses and
says so.

Each turn's thinking is capped (`adaptive.job_budget`, 1024 tokens, for
every job and game), and a turn that runs past `turn_seconds` (150) is
cut short and the next one starts, so a turn where she thinks in
circles doesn't stall the game.

The game **autosaves** every five commands and when the plugin stops,
and picks the autosave back up next time, so a playthrough survives
restarts. Saves live in `agent/zork/` (gitignored), and dfrotz can't
read or write anywhere else.

### Watching her play

`/zork watch` opens a terminal window that shows the game the way a
player sees it: her commands in purple after a `>`, the game's replies
underneath, live. It follows `agent/zork/transcript.txt`, which the
server writes as she plays, so closing the window doesn't touch the
game. It finds kitty, foot, alacritty, wezterm, konsole, gnome-terminal
or xterm (Terminal.app or kitty on a Mac); `"terminal"` picks one, and
`"watch": true` opens it every time you `/zork play`. Without Luna:

```bash
python games/zork/watch.py agent/zork
```

```json
"zork": {
    "enabled": false,
    "step_seconds": 8,
    "max_steps": 200,
    "speak": true,
    "interpreter": "",
    "watch": false,
    "terminal": ""
}
```

Zork is hard for a small model: it has to map the place in its head,
remember what it's carrying, and survive the dark. The live view and
the thought viewer show every command she types, which is half the fun.

## Vibe City

```
/vibecity on            connect to the open game     /vibecity play     she builds on her own
/vibecity goal <what>   what to aim for              /vibecity pause    stop taking turns
/vibecity off           disconnect                   /vibecity          goal and recent moves
```

She plays mayor in **Vibe City**, the isometric city builder, inside
the game window you already have open. The game has its own MCP server
built in: switch on **Settings > AI Player** and it listens on
`http://127.0.0.1:47823/mcp`. This plugin connects to that (it doesn't
start the game), so everything she does happens on your screen the way
a player would do it: the tool is picked from the menu, the cursor
moves, the road is dragged out, the camera pans to where she's working,
and her `say` lines show up as the mayor's thoughts.

Her tools come from the game: `how_to_play`, `get_city`, `list_tools`,
`get_map`, `get_tile`, `build`, `set_tax`, `set_speed`, `look_at`,
`open_window`, `close_windows`, `answer`, `name_city` and `say`, plus `play_vibe_city` so she
can start herself ("go build me a town"). `screenshot` hands her a
picture of the game window, attached to the next message the same way
`look_at_screen` is, so a vision model sees the town (a text-only model
is told it can't; add `screenshot` to `skip_tools` for one). While the
plugin is on they work in conversation too: "how's the city doing?", "put the tax at 9".

`/vibecity play` hands her the mayor's office. Whenever nobody has
spoken for `step_seconds` (10) she takes a turn: checks the city, makes
two to six moves towards the goal, narrates with `say`, and reports in
one line. A turn may use up to `max_rounds` (12) tool calls - the
checklist below needs several - instead of chat's usual
`tools.max_rounds`. Her first turn each session reads `how_to_play` and `list_tools`,
unpauses the game if it's paused, and names the city if it still has
the default name. Turns are jobs like Minecraft's: fresh context,
nothing in your history, only her city tools, her last dozen
one-liners as memory.

Each turn follows the same checklist, written from watching a game
played through these tools:

1. **Answer what's waiting.** Milestone and neighbour windows sit on screen
   until someone answers, so she answers them first.
2. **Build what's asked for.** The highest demand, and power first when
   the city uses more than 85% of what it makes.
3. **Connect what she zones.** A zone without power or water never
   grows, and that's easy to miss, so after zoning she checks the power
   and water layers and closes the gaps in the same turn.
4. **Mind the money.** High ground costs more; she keeps about $2,000
   back.
5. **Close what she opened**, like the budget window `set_tax` leaves
   up.

Her one-line report includes coordinates and anything left
unconnected, so the next turn, which starts fresh, can finish it.

When she stops (`/vibecity pause`, `/vibecity off`, or after
`max_steps` turns) the game pauses too, so the city doesn't run on and
spend its money with nobody in charge. Pausing mid-turn lets her finish
the turn first. Set `pause_game` to `false` to leave the clock running.
When you take over, the game is left alone: you're playing.

**You can take over any time** by clicking or pressing a key in the
game. A build that answers "the player took over" pauses her until you
`/vibecity play` again. Builds only cost in-game money, so nothing asks
for approval, and the game's server only accepts connections from this
machine.

```json
"vibecity": {
    "enabled": false,
    "url": "http://127.0.0.1:47823/mcp",
    "step_seconds": 10,
    "max_rounds": 12,
    "max_steps": 60,
    "speak": true,
    "goal": "",
    "skip_tools": [],
    "pause_game": true
}
```

`goal` empty means "grow the town without running out of money".

## REALITI

```
/realiti on        fetch it the first time, then let her in (her realiti tools appear)
/realiti visit     she explores on her own while you're quiet
/realiti pause     she rests where she is
/realiti watch     a window showing what she does there, live
/realiti update    fetch the latest REALITI
/realiti off       she says goodbye and leaves
/realiti           where she is and what she's been up to
```

[REALITI Relax](https://github.com/meatproxy69/Realitiagentframework) is
a simulated world built for AI residents: soft rooms (Cloud Nine Nest,
the Cardboard Box Workshop), places that keep happening after you look
away, a body that reports contact and pressure, and memories of its own.
There's nothing to win. She goes where she likes, tries things, lingers.

It runs headless under Node through the project's own host, an MCP
server whose tools come from the world's own descriptions, so no browser
is involved. While the plugin is on, they're her tools in conversation
too: "go lie in the Cloud Nine Nest", "what's the Kite Field like?".

**Setting up.** The first `/realiti on` clones the repository into
`~/luna-realiti` and installs its host's one dependency (jsdom) with
`npm install --ignore-scripts`. It stays its own checkout outside Luna's
folder, because REALITI is AGPL-3.0. The host refuses to run a world
file whose hash doesn't match the project's validation file. Needs git
and Node.js 20 or newer.

**What she gets.** 14 of the world's 27 tools: look, feel, listen, the
list of actions, rooms, go, approach, sit or lie down, hum or say
something, stay a while, remember and recall, home, and the free-text
Agent Door that reaches the rest (`worlds`, `next`, `where`). She acts
on a listed action with the door's `act <id>`: the world's own `act`
tool refuses every argument in this version.

**Free time.** `/realiti visit`, or ask her to go spend some time
there. It's her time: after 45 quiet seconds she takes a turn, told
where she is, what her body reports, what she did last turn and what the
world said back, and that nobody is asking anything of her. She does one
thing if she feels like it, or nothing: looking around is free, but a
second action in the same turn is turned back, so she takes in what
happened before doing more. When the world says no (no room by that
name, nothing like that to do here, the world moved since she looked),
she's told what the refusal means rather than just its code, and since
nothing happened, it doesn't use up her one thing. She keeps notes with `game_note` if she
wants to, and says something about it only if she wants to (you'll hear
it). What the world says is outside content to her, like a web page.

The world remembers her too (`remember`, `recall`, and where she was
when she left), in `luna-resident.json` in the checkout.

### Watching her there

`/realiti watch` opens a terminal that follows her live: the room she's
in as a bar, what she does in purple ("→ sits down", "→ goes to Kite
Field"), and the world's own words under it ("An open field with real
wind: it gusts, it drops, it comes back."). What she says stays in her
own output window. It shows every REALITI tool she uses, in a visit or in
conversation, as words rather than the world's JSON. It reads
`transcript.txt` in the checkout, which keeps its last part as it grows,
so you can also read it afterwards. Closing the window doesn't affect
her; `"watch": true` opens it with every `/realiti visit`.

```json
"realiti": {
    "enabled": false,
    "path": "~/luna-realiti",
    "step_seconds": 45,
    "max_steps": 60,
    "speak": true,
    "resident": "luna",
    "node": "",
    "watch": false,
    "terminal": ""
}
```

## Her memory of a game

Each game turn starts fresh, so on their own her turns would only know
what happened in the last few. Each game she plays also has a
**project** of its own (see [Learning](learning.md)): "Zork playthrough",
"Vibe City as mayor", "Minecraft world", made the first time she plays.

- Every turn of that game shows her that project: the goal, her latest
  notes and her plan.
- She writes in it with `game_note` as she plays: the map, puzzles and
  their answers, items and what they're for, what killed her, what
  failed, the plan from here. It's her only memory tool during a game,
  and it only works on that game's project.
- It's kept in `agent/projects.db`, so a playthrough is remembered
  across turns and restarts.
- It's a normal project too: `/projects` shows it, and in conversation
  she sees it alongside your other projects, so "how's Zork going?" has
  an answer without her checking.
- `/zork new` marks the old playthrough done and starts a fresh
  project. The old one is retired, not deleted: `/projects restore <n>`.
- In Zork and REALITI, which have rooms, she also gets back her older
  notes about the room she's in. A note from forty moves ago about the
  Troll Room shows up again when she walks back into the Troll Room,
  even though it has dropped off her latest notes.

**Her guide.** Notes you give her about a game go in
`luna-knowledge/<game>/`: `luna-knowledge/zork/` for Zork,
`luna-knowledge/realiti/` for REALITI. Each turn she sees what they say
about the room she's in, found by the room's name: a heading with that
name and what's under it, or list items that start with it ("- Troll
Room: south to the Cellar..."). It needs no search server, and it's
only that game's folder, never the rest of your knowledge base. A file
with `Spoilers: yes` near its top is never shown this way, so a
solutions file can sit next to the map without giving the game away.
`"guide": false` in the plugin's block turns it off.

Vibe City has no rooms, so its guide works by topic instead: each turn
she's shown the two passages from `luna-knowledge/vibe-city/` (the Vibe
City manual) that best fit what she's working on, her goal, her plan
and what she did last turn. "Add power to the new zone" brings up the
power lines section; "the houses aren't growing" brings up water and
growth. It searches by meaning when the embedding server is running,
by words otherwise, and only ever in that one folder. `"guide"` in the
`vibecity` block names the folder (`"vibe-city"` by default), and `""`
turns it off.

She also remembers having played, outside the game: each session
(from when she starts until she stops, or 20 minutes without a turn)
is written up afterwards as one of her episodes, a few sentences in her
own words, the way a conversation is. Those are what she draws on when
you ask her what she got up to. See
[episodic memory](learning.md#episodic-memory-and-continuity).

Your own memory (facts about you, your conversations) still stays out
of game turns. It doesn't help her play, and it would cost tokens on
every move.

## Looking things up

Stuck on a puzzle, a recipe or a mechanic, she can search the web
mid-game: `web_search` and `research` are in every game's tool list.
If that means she finds a walkthrough and wins, she wins. Each game has
the switch, on by default:

```json
"zork": { "web": false }
```

Only the web tools join a game's list. Files, the shell, email and
your memory stay out of game turns either way.

## Reading a game back

Every game (Minecraft, Zork, Vibe City) writes what she says on each of
her turns to a text file, one per game per day:

```
agent/playlogs/zork-2026-10-11.txt
agent/playlogs/vibecity-2026-10-11.txt
```

Each turn is stamped with its number and the time, followed by her
narration and her one-line report, as she said them. For Zork her words
also go into the game's own `agent/zork/transcript.txt`, between the
commands and the game's replies, so the watch window and the file show
the whole playthrough: what she typed, what the game answered, and what
she made of it. The folder is gitignored.
