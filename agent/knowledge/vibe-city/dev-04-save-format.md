# Vibe City: Save format and loading
Audience: developer
Keywords: save, load, save file, JSON, save.js, cityJSON, loadCityText, SAVE_FORMAT, fmt, versioning, migration, fitSaveToWorld, map size, 128x128, 96x96, old saves, saves folder, desktop, Electron, vibeShell, footprints, look grid, recountAll, newCity
Summary: A Vibe City save is one JSON file written by cityJSON in js/save.js, holding every tile array plus blocks for events, neighbours, milestones, footprints, the city name, the arcade and mods. Loading goes through fitSaveToWorld, which sets a save from a smaller map into the current 128x128 world, then rebuilds all derived state from the tiles. On the desktop app saves go to a saves folder chosen by release/saves.js.

## Where save code lives

In Vibe City all save and load logic is in js/save.js:
- `cityJSON()` serialises the city once; every save route uses it.
- `saveFilename()` builds `<slug>-y<year>m<month>.json` from the city name via `saveSlug` (lowercase letters, digits and dashes, up to 40 characters, "vibecity" if nothing is left).
- The `#btn-save` and `#btn-load` handlers pick a route.
- `loadCityText(text)` parses, migrates and installs a save.
- `fitSaveToWorld(data)` embeds a smaller map into the current world.
- `newCity(opts)` starts a fresh city from the New City window (js/worldgen.js).

Subsystems own their own blocks through paired functions: `eventsSaveData`/`eventsLoadData` (js/events.js), `neighboursSaveData`/`neighboursLoadData` (js/neighbours.js), `milestonesSaveData`/`milestonesLoadData`, `footprintSaveData`/`footprintLoadData` (js/footprint.js), `cityNameSaveData`/`cityNameLoadData`, `arcadeSaveData`/`arcadeLoadData`, `modsSaveData`/`modsLoadData`, and `lookSaveData`/`lookLoadData` (js/sprites.js). Settings are not in saves; they live in localStorage through js/prefs.js.

## What is in a save

A Vibe City save is a JSON object with these fields:
- Tile arrays, each `W*H` long (16384 for 128x128), written as plain arrays: `types`, `levels`, `roadTier`, `wireOverlay`, `railOverlay`, `isTunnel`, `pipes`, `hasWater`, `elev`.
- Scalars: `waterStored`, `funds`, `taxRate`, `month`, `year`.
- `counts`: written but ignored on load.
- `events`: `fired` (special events already used), `lastRobberyAt`, and when present `shocks` (mood shocks), `school`, `fallout`, `casino`, `scorch`. Events in progress are not saved, except fallout and scorch.
- `neighbours`: `towns` (edge, name, pop, cap, asking), `gateways` as `[tile, edge, kind, at]`, `lastAskAt`.
- `milestones`: `{ done }`.
- `footprints`: `anchors` as `[tile, anchor]` pairs and `blocks` as `[anchor, n, type]`.
- `city`: `{ name, named }`. `arcade`: the arcade rival record. `mods`: `types` (type number to mod id), `data`, `paid`, `missing`.
- `look`: only when the city came from a smaller map (see below).
- `resStyle`: per tile 0 house, 1 condo, 2 apartments, written for outside programs such as Vibecopter and ignored on load.
- Stamps: `fmt` (SAVE_FORMAT), `version` (GAME_VERSION), `w`, `h`.

## Save format versions

`SAVE_FORMAT` in js/constants.js is 6. The history recorded in the code:
- 1: never written; saves with no `fmt` are treated as the oldest.
- 2: bores may run under roads and railways. Loading a save with `fmt` below 2 clears `isTunnel` on ROAD tiles, because in those saves a flagged road was the old kind of tunnel.
- 3: the save carries its own `w` and `h`.
- 4: the city's milestones. A missing `milestones` block means an old city, so load calls `milestonesTick(true)` to record already-passed marks silently, with no windows and no money.
- 5: buildings bigger than one tile, and which tiles each covers.
- 6: how big each of those buildings actually is (`blocks`). A fmt 5 save has anchors but no blocks, so the block size is derived by counting tiles per anchor (a square block of n by n claims n squared tiles).

Most migrations key on whether a field is present rather than on `fmt`: no `pipes` loads as a city on wells, no `hasWater` rebuilds water from `elev < WATER_LEVEL` (0.33), no `elev` generates terrain, no `footprints` means every tile is its own building.

## Loading and validation

In Vibe City `loadCityText` runs these steps inside a try block; any exception shows the toast "Could not read save file":
1. `fitSaveToWorld(JSON.parse(text))`.
2. Copy tile arrays into fresh typed arrays, creating empty ones for missing fields.
3. Validate numbers with `saveNum`: funds -1e15..1e15, taxRate 0..25, month 1..12, year 1..1e6, waterStored 0..1e9.
4. `modsRemap(types, data.mods)` maps saved mod type numbers to this run's numbers, or to grass.
5. Any type with no entry in `NAMES` becomes grass; levels above 4 are clamped to 4.
6. `lookLoadData`, `footprintLoadData`, then `recountAll()`; saved counts are never trusted.
7. Rebuild derived state: `recomputeTunnels`, `recomputeRail`, `recomputeCoverages`, `computeTotals`, `recomputePollution`, `recomputeCrime`.
8. Load neighbours, events, milestones, city name, arcade and mods; then demand, budget and power stats and the HUD.

Text from a save that ends up in HTML goes through `escHTML`, after a 0.9.13 save put markup into a town name.

## Map sizes and fitSaveToWorld

The Vibe City map is `W = H = 128` since 1.0.0 b532. Earlier sizes were 48x32 at first (`OLD_W`, `OLD_H`, assumed for a save with no `w`/`h` whose arrays are not W*H long), 96x64 from 0.7.52, and 96x96 from 0.8.19 to b531. A save larger than the world throws "save is from a bigger world", so an older build cannot open a 128x128 save.

`fitSaveToWorld(data)` returns the data unchanged if it already matches. Otherwise:
- Placement: a save as wide as the world sits on the south edge; anything narrower is centred, so a 96x96 city sits 16 tiles in from every edge. Test rigs set `saveEmbedAtOrigin` to put it in the corner.
- New country: `genWorld()` generates terrain around it; elevation blends from the old edge into the new land over `SAVE_BLEND` (6) tiles. New land gets its own trees and water.
- Water that touched the old edge is carried straight out to the new edge at its own height, so coasts stay open sea and rivers keep running off the map.
- Tile numbers are remapped: footprint anchors and blocks, events fallout and scorch, `mods.missing`, and gateways.
- Gateways whose edge is now inland have their road (same tier) or plain track extended straight out to the new edge, and the gateway moves there.
- Looks: `look` is set to `{ w: oldWidth, x: offsetX, y: offsetY }` (added to any existing `look`), so `lookKey(i)` hashes in the old grid and every lot keeps the same house, shop, factory and condo art.
- `resStyle` is dropped.

Note that `fitSaveToWorld` calls generation code, so the country around a migrated save differs on every load.

## Where saves go

There are three save routes in Vibe City, all writing the same `cityJSON()` text:
- Desktop shell: if `window.vibeShell.saves` exists, `vibeShell.saves.write(filename, json)` and `vibeShell.saves.read()` go over IPC to release/saves.js, which opens native dialogs in the saves folder with the filename pre-filled.
- Chromium tab: `showSaveFilePicker`.
- Other browsers (Firefox): a plain download of a Blob. Loading in a browser uses the hidden `#file-load` input.

`saveDir(app, gameRoot)` in release/saves.js picks the folder: when unpackaged, `saves/` beside the game (the game tree has one, with files such as brooks-y262m9.json); when packaged, `Documents/Vibe City/saves`, because the AppImage is read-only. The folder is created on first use. The bridge only accepts filenames matching `/^[\w .\-()]{1,120}\.json$/` with no `..`.

## newCity

`newCity(opts)` merges `WORLDGEN_DEFAULT` with the New City window choices, clears levels, roads, overlays, tunnels, pipes, reservoir and vehicles before calling `genTerrain(o)` (so tree variants survive), runs `recountAll()`, sets funds from the options, tax 8 and date month 1 year 1, recomputes everything, resets every subsystem with a null load, and calls `worldChanged()`. The null loads clear neighbours, events, milestones, footprints, the look grid (back to plain 128 at 0, 0), the city name (Vibe City, not yet asked), the arcade and mods, so nothing from the previous city carries over.

## Common questions

**Q: What format is a Vibe City save?**
A: A single JSON file produced by `cityJSON()` in js/save.js.

**Q: What is the current save format number?**
A: `SAVE_FORMAT` is 6, stored in each save as `fmt`.

**Q: Can I open a 96x96 save in the 128x128 game?**
A: Yes. `fitSaveToWorld` centres it with 16 tiles of newly generated land on every side.

**Q: Can an older build open a 128x128 save?**
A: No. It throws "save is from a bigger world"; b532 or later is needed.

**Q: Are the saved counts used?**
A: No. `recountAll()` rebuilds counts from the map on every load.

**Q: Where does the desktop app put saves?**
A: In `saves/` beside the game when run unpackaged, or `Documents/Vibe City/saves` for a packaged build.

**Q: Are settings stored in the save?**
A: No. Settings are per machine in localStorage via js/prefs.js.

**Q: Is a running fire saved?**
A: No. In-progress events are dropped; only fallout, scorch, mood shocks, fired specials and a few records are kept.

**Q: How do I add a new block to the save?**
A: Write a `xxxSaveData`/`xxxLoadData` pair, add it to `cityJSON()` and `loadCityText()`, reset it in `newCity()`, and remap any tile numbers in `fitSaveToWorld`.

**Q: What is the look field?**
A: The grid a migrated city was built on, so building art hashed from tile numbers stays the same after the map grew.
