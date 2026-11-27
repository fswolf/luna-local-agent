# Vibe City: Codebase architecture
Audience: developer
Keywords: architecture, codebase, source layout, vanilla JS, no bundler, globals, script order, index.html, state.js, constants.js, tile types, T enum, main loop, boot, requestAnimationFrame, simTick, file map, js folder, Electron, release folder, prof rigs, GAME_BUILD
Summary: Vibe City is a browser city builder written in plain JavaScript with no bundler, no modules and no framework. Every file in js/ is a classic script loaded in a fixed order from index.html, so every top-level function and variable is a global. This file maps the source tree, the core state in js/state.js, the tile types and the two loops (render frame and monthly sim tick).

## What the codebase is

Vibe City is an isometric city builder in the SimCity 2000 tradition, version 1.0.0 (GAME_VERSION in js/constants.js), build 547 (GAME_BUILD). The game is vanilla JavaScript drawn onto one HTML canvas (`<canvas id="view">`). There is no bundler, no npm step for the game itself, no ES modules and no framework. Every file starts with `"use strict";` and is loaded by a plain `<script src="js/NAME.js?v=547">` tag in index.html, where `?v=` is the build number used as a cache buster.

Because nothing is a module, every top-level `function`, `let` and `const` in any file is visible to every other file. Load order only matters for top-level code that runs at load time. index.html also carries a strict Content-Security-Policy (`script-src 'self'`, `connect-src 'none'`), so no inline script runs and the page cannot fetch from the network.

The rest of the tree in Vibe City: `release/` is the Electron desktop shell (main.js, preload.js, saves.js, mods.js, mcp.js and friends; `npm install` then `npm start` from release/), `tools/` holds build and art scripts (bump.sh, suite.sh, make-playlist.sh, slice and template Python scripts), `prof/` holds headless test rigs, `img/` the sprite art, `saves/` the default saves folder, and `compile.sh` builds packaged clients into dist/.

## Script load order

In Vibe City the order in index.html is: splash, constants, state, terrain, canvas, footprint, sprites, smoke, economy, simulation, mods, plumbing, tunnels, rail, pollution, crime, vehicles, trains, ships, prison, colors, render-utils, render-buildings, poles, render-stamps, cursor-badge, render-props, render-roads, render-rail, render-ramps, render-portals, water-tiles, render-ground, render-structures, render-void, render-wire, render-fps, render, hud, input, plan, neighbours, save, prefs, playlist, gallerylist, parklist, clublist, sfxlist, audio, sfx, menu, discord, drag, worldgen, events, disasters, milestones, news, cityname, gallery, park, casino, slots, poker, clubs, arcade, trails, courier, races, station, school, cabview, radio, region, overlay-scrollbars, tooltip, ai, main.

Rules that follow from this order:
- constants.js loads before state.js because state.js sizes its arrays from `W*H`.
- state.js declares `previewing` and `worldChanged()` early because almost every later file reads them.
- main.js is last; it is the boot script.
- Files that call into something loaded later guard with `typeof fn === "function"` (for example `portDemand`, `prisonShort`, `cityNameTick`).

Two files sit in js/ but are not in index.html: `js/water.js` (superseded by plumbing.js and listed in tools/retired-assets.txt) and `js/vehicleSprites.js`. Do not edit them expecting a change in game.

## File map: core, world and simulation

- constants.js: every tuning number, GAME_VERSION, GAME_BUILD, W/H, TW/TH, the T tile enum, NAMES, COST, SAVE_FORMAT, view constants.
- state.js: the tile arrays, funds, date, camera, rotation, worldVersion, SPEED_MS.
- terrain.js: genWorld/genTerrain, elevation to height (terrainTopZ, groundTopZ), buildingHeight.
- worldgen.js: the New City window feeding genWorld.
- footprint.js: buildings bigger than one tile (FOOTPRINT, anchorAt, blockN, blockT).
- economy.js: spend, setType, recountAll and placement helpers.
- simulation.js: power grid, coverage, demand, growth, budget, mood, simTick, setSpeed.
- plumbing.js: the water utility (pipes, pumps, towers, reservoir).
- water-tiles.js: water as terrain and its drawing.
- tunnels.js, rail.js: bores, rail lines, depot catchment.
- pollution.js, crime.js, prison.js: the two fields and the prison.
- neighbours.js, region.js: the four edge towns and their UI.
- events.js, disasters.js, milestones.js, news.js: random events, disasters, milestones, the newspaper.
- vehicles.js, trains.js, ships.js, smoke.js: moving scenery.
- mods.js: mod buildings (types from MOD_TYPE_BASE up).

## File map: rendering, input, UI and minigames

- Rendering: canvas.js (projection, rotation, picking, draw orders), render.js (the frame and ground cache), render-ground.js, render-structures.js, render-roads.js, render-rail.js, render-ramps.js, render-portals.js, render-props.js, render-stamps.js, render-buildings.js, render-utils.js, render-void.js, render-wire.js, render-fps.js, poles.js, cursor-badge.js, sprites.js, colors.js.
- Input and tools: input.js (keys, wheel zoom, tools, views), plan.js (drag preview and pricing), drag.js (draggable windows).
- Interface: hud.js, menu.js, prefs.js (localStorage settings), tooltip.js, overlay-scrollbars.js, splash.js, cityname.js, save.js.
- Audio: audio.js, sfx.js, radio.js, plus the generated lists playlist.js, sfxlist.js (from tools/make-playlist.sh).
- Buildings you can enter: gallery.js and gallerylist.js, park.js and parklist.js, casino.js, slots.js, poker.js, clubs.js and clublist.js, arcade.js (with trails.js and courier.js), races.js, station.js and cabview.js, school.js.
- Desktop and AI: discord.js (desktop-only Discord presence), ai.js (page side of the AI player driven by release/mcp.js).

## Core state in js/state.js

Vibe City keeps the map as flat typed arrays of length `W*H`, indexed `i = y*W + x` (helper `idx(x,y)`; `inBounds(x,y)`, `clamp(v,a,b)`). W and H are both 128 since 1.0.0 b532.

- `types` (Uint8Array): the tile type, a value of T.
- `levels` (Uint8Array): growth level for zoned lots (0 to 4); for parks, trees, statues, plazas, pumps, towers, universities and other variant art it stores the sprite variant as variant+1.
- `roadTier`: 0 street, 1 avenue, 2 highway.
- `wireOverlay`, `railOverlay`: a power line or a level crossing over a road tile.
- `isTunnel`: a bore under the tile. `pipes`: a buried water main.
- `hasWater`: water as an overlay, separate from types because a bridge is a ROAD tile with water under it. `waterDepth` (Float32Array) is for drawing only.
- `elev` (Float32Array): raw elevation 0..1. `powered`, `serviceCov`, `amenityCov`, `nightlifeCov`: derived maps.
- `counts`: building tallies used for upkeep; rebuilt by `recountAll()`.
- Scalars: `funds` (20000 at start), `taxRate` (8), `month`, `year`, `pop`, `jobsC`, `jobsI`, `demand {r,c,i}`, `stats` (monthly readouts), `waterStored`, `trafficScale`, `tool`, `speed`, `simTimer`.
- View: `camera {x, y, scale}`, `rotation` (0..3, 90 degree steps), `viewMode`, `hoverTile`, `waterTime`.
- `worldVersion` and `groundAllVersion`, bumped by `worldChanged(tilesOnly)`; the ground cache keys on them. `worldChanged` does nothing while `previewing` is true.

## Tile types (T)

The T enum in js/constants.js: GRASS 0, ROAD 1, RES 2, COM 3, IND 4, POWER 5, PARK 6, WATER 7, TREE 8, PLAZA 9, STATUE 10, POLICE 11, FIRE 12, SCHOOL 13, HOSPITAL 14, POWERLINE 15, RAIL 16, DEPOT 17, PUMP 18, TOWER 19, UNIVERSITY 20, SOLAR 21, LIBRARY 22, WIND 23, GALLERY 24, CLUB 25, NIGHTCLUB 26, TRACK 27, ARCADE 28, PORT 29, PRISON 30.

Naming traps in Vibe City: T.CLUB (25) is the Casino since 0.78.50 and T.NIGHTCLUB (26) is the building players call the Club; NAMES maps the numbers to display names. Mod buildings get type numbers from `MOD_TYPE_BASE` (max of T plus 1) upward, held in `MOD_TYPES`. Multi-tile buildings use FOOTPRINT in js/footprint.js: POWER 2, TRACK 3, PORT 2, PRISON 3; every tile of the block carries the same type.

## Boot and the two loops

js/main.js boots Vibe City: `genTerrain()`, `buildDrawOrders()`, `recomputeRail()`, `recomputeCoverages()`, `computeTotals()`, `newNeighbours()`, `calcDemand()`, `recomputePollution()`, `recomputeCrime()`, `computeBudgetStats()`, `computePowerStats()`, `updateHUD()`, `setSpeed(1)`, then `requestAnimationFrame(render)` and the splash is hidden two frames later. It also preloads the game fonts and calls `worldChanged()` when they arrive.

There are two independent loops. The render loop is `render(now)` in js/render.js, re-armed with requestAnimationFrame every frame; it advances real-time things (vehicles, trains, ships, smoke, events, the newspaper clock, fallout) only while `speed > 0`, and water animation always. The simulation loop is `simTick()` in js/simulation.js, run by `setInterval(simTick, SPEED_MS[speed])` from `setSpeed(s)`. One tick is one in-game month. SPEED_MS is `[0, 4000, 1556]` by default; menu.js `applyPace` sets normal speed from the pace setting (default 4.0 s) and fast to that divided by 1800/700.

## Common questions

**Q: Does Vibe City use modules or a bundler?**
A: No. Every js/ file is a classic script loaded by index.html in a fixed order, so all top-level names are globals.

**Q: Where do I add a new tuning constant?**
A: js/constants.js. It loads before everything except splash.js, so any file can read it.

**Q: How is a tile addressed?**
A: By index `i = y*W + x` via `idx(x,y)`. W = H = 128.

**Q: What does levels[] hold for a park or a tree?**
A: The sprite variant stored as variant+1, so 0 means no stored roll and the code falls back to a position hash.

**Q: Which type number is the Casino?**
A: T.CLUB, 25. The Club with the dancers is T.NIGHTCLUB, 26.

**Q: What runs every frame and what runs every month?**
A: `render()` runs every animation frame; `simTick()` runs once per month on a setInterval of SPEED_MS[speed] milliseconds.

**Q: Why is js/water.js not doing anything?**
A: It is not loaded by index.html. The water utility lives in js/plumbing.js and water terrain in js/water-tiles.js.

**Q: How do I bump the build number?**
A: Run `tools/bump.sh` (build only) or `tools/bump.sh patch|minor|major`; it updates every `?v=` and GAME_BUILD together.

**Q: What must I call after changing tile data?**
A: `worldChanged()` (or `worldChanged(true)` for pure tile data changes from recomputes) so the ground cache redraws.
