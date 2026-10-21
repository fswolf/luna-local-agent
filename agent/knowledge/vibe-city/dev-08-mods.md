# Vibe City: The Mod System
Audience: developer
Keywords: mods, modding, mod.json, vcmod, vcmod protocol, js/mods.js, release/mods.js, Documents/Vibe City/mods, custom building, mod window, iframe, sandbox, postMessage, Neon Brew, Barista Rush, MODDING.md, MOD_TYPE_BASE, modClean, modFitImage, facing, per_month
Summary: Vibe City mods are folders in Documents/Vibe City/mods that each add one building with its own sprites and, optionally, a mini game window. The desktop shell lists them and serves their files over vcmod://, and js/mods.js turns each into a real tile type. Neon Brew, a cafe with the Barista Rush game, is the example mod.

## What a mod is
A Vibe City mod is one folder inside Documents/Vibe City/mods (on Linux ~/Documents/Vibe City/mods). Each folder holds a mod.json, its building pictures (R0.png to R3.png, or one picture for all angles), an optional icon.png for the menu button, and an optional HTML page for a window that opens when the building is clicked with the pan tool. A mod adds exactly one building: it gets a tile type of its own, a button in one of the build menu drawers, a price and upkeep, and can draw power and water, add jobs, boost growth around it, and pay money into the city from its window. Mods are a separate download, never part of the base game, and they work only in the desktop client, because a browser tab cannot list a folder. The modders' guide is mods-dist/MODDING.md in Ryan's working tree, which is also copied into the mods folder.

## The shell side: release/mods.js
In the Vibe City desktop shell, release/mods.js handles everything that touches the disk. modsFolder(app) is Documents/Vibe City/mods, created at start in dev and packaged builds alike. listMods reads each subfolder whose name matches SAFE_PART (a word character, then up to 63 of word characters, space, dot, dash and brackets), parses its mod.json (64 KB at most) and returns at most 64 mods in name order. That list reaches the page through the assets bridge (release/assets.js) as `mods`, before any game script runs. Files are served over the custom vcmod:// scheme, registered as privileged (standard, secure, fetch, CORS, stream) before the app is ready. serveMod allows only plain names inside the mod's own folder, at most one sub folder deep, resolves symlinks with realpath and refuses any that lead outside, refuses files over 64 MB, and answers with access-control-allow-origin * so the game can read sprite pixels.

## The vcmod:// protocol and the page CSP
A Vibe City mod file is addressed as vcmod://<folder>/<file>, or vcmod://<folder>/<sub>/<file> for one level of sub folder (Neon Brew keeps its customer faces in customers/). Anything else, including .. segments or a missing file, is a 404. Every HTML file served this way carries its own Content-Security-Policy (PAGE_CSP in release/mods.js): default, script, style, image, media, font, connect and worker sources are limited to vcmod:, data: and blob:, inline script and style are allowed, WebAssembly is allowed ('wasm-unsafe-eval'), and form-action and base-uri are 'none'. In practice a mod page has no network access at all: it cannot load from a CDN or a web font service or send anything out, so everything it needs must sit in its own folder. index.html's own CSP allows img-src vcmod: and frame-src 'self' vcmod:.

## mod.json fields
Vibe City checks every mod.json field in modClean (js/mods.js) and pulls out of range values back into range:
- id: lower case letters, digits, - and _, up to 32 characters. Saves remember mods by it, so never change it. Without one, a cleaned folder name is used.
- name (28 characters), label (12, the word under the menu button), author (40), version (16), desc (220).
- group: transport, utilities, civic or decor (default decor), which picks the menu drawer.
- price: 0 to 200000, default 1000. upkeep: 0 to 5000 a month, default 10.
- power and water: 0 to 200 each. Give both or neither; if either is set both become at least 1.
- jobs: 0 to 500 commercial jobs while open. reach: 0 to 12 tiles of growth boost.
- sprites: exactly 1 or 4 plain file names, png, webp or jpg. icon: optional, defaults to the first sprite.
- facing: optional, "standard" for [0, 1, 2, 3] or four sprite numbers for the front down-left, up-left, up-right, down-right.
- fit: optional { span: [4], nudge: [4] } override (span 0.5 to 2, nudge 0 to 1).
- window: { page, title, width 320 to 1200 (default 860), height 240 to 800 (default 540) }.
- money.per_month: 0 to 100000, the most the page may pay into the city per game month.

## The game side: js/mods.js
js/mods.js loads after simulation.js and runs modsStart() once. Each clean mod, sorted by id, gets a tile type from MOD_TYPE_BASE, which is the highest built-in T value plus 1, so it follows any built-in type added later. Ids that differ only by - and _ share a tool name ("mod_" plus the id with - turned to _), so the second is skipped. At most 64 mods register (MOD_MAX). modRegister fills the same tables every Vibe City building uses: NAMES, COST, TOOL_TYPE, COUNT_KEY, counts and BUILDABLE_ONLY_GRASS, plus CIVIC_POWER_MW, CIVIC_WATER and POWER_USER when it draws power, and AMENITY_REACH when it has reach. MOD_TYPES maps a type number to its mod. A building that draws power and water is closed without them, like the casino. Problems go to the console through modWarn and the first one shows in a toast 2.5 seconds after start, "Mod trouble: ...".

## Mod art and auto fit
A Vibe City mod picture is loaded with crossOrigin and fitted by modFitImage, a JavaScript port of the slab fit in tools/fit-slab.py: it finds the lowest solid pixel (alpha above 64) in each column, fits a line to each lower edge out from the bottom vertex, pads the picture so the slab is centred, and sets span = width / slab width and nudge from the two corners' mean row. A fit given in mod.json overrides it. Draw each building on its own square ground slab in the game's isometric view on a transparent background, and keep everything inside the slab because lotSprite trims anything past the tile edge. A picture that fails to load borrows another angle; with none at all the building is a purple placeholder box (modPlaceholder) with a question mark, so it can still be found and bulldozed. With `facing` set, modFacing turns the front toward the nearest road like built-in civic buildings.

## The mod window and its messages
Clicking a Vibe City mod building with the pan tool opens #mod-panel with an iframe created per open, sandbox="allow-scripts" and no same-origin, removed on close. The frame gets keyboard focus on load. Only messages from that frame's own window are accepted. From the page:
- { vc: "ready" }: the game answers with init { api: 1, mod, data, city, money: { perMonth, left }, settings: { volume } }.
- { vc: "save", data }: any JSON up to 32 KB, kept in the city save.
- { vc: "pay", amount }: whole dollars, capped by money.per_month this game month; a closed building pays nothing. The game answers paid { amount, left, open }.
- { vc: "toast", text }: 120 characters, at most one a second.
- { vc: "city" }: a fresh city { open, name, year, month, pop, jobs, funds, demand, taxRate, built }.
- { vc: "close" }.
The window closes if its building disappears (checked every second and on every message) or a city is loaded. The city never hears Escape while the page has focus, so a page should send close on Escape itself.

## Mods in save files
A Vibe City save stores mods as { types, data, paid, missing }: which type number was which mod id, each mod page's saved data, what was paid this month, and the lots of mods that are not installed. On load modsRemap runs before the tile check and goes by the save's own table, never by MOD_TYPE_BASE, so a new built-in type that takes a number a mod used to have does not corrupt old cities. A number in the table becomes this run's type for that mod, or grass if the mod is missing; a number at or above the base that is not in the table becomes grass. Lots of a missing mod are kept in modMissing and come back when the mod is installed again, unless something was built there, and a toast lists the missing mods. modData and modPaid keep every id, installed or not.

## Neon Brew, the example mod
Neon Brew is Ryan's example Vibe City mod, kept in mods-dist/neon-brew in his tree and installed in Documents/Vibe City/mods. Its mod.json: id neon-brew, name Neon Brew, label Cafe, author Beerus, version 1.4, group decor, price 3500, upkeep 25, power 6, water 6, jobs 8, reach 5, sprites R0.png to R3.png, icon icon.png, facing [0, 3, 2, 1], window game.html titled Neon Brew at 900 x 560, money.per_month 1500. The window is Barista Rush, one HTML file plus a customers/ folder of 260x260 webp faces: build drinks from 7 stations (keys 1 to 7), Space serves, Escape pauses then closes. Shifts last 150 seconds, and at closing the city takes 10 times the takings through pay, capped at 1500 a month. Keep "author": "Beerus" in every copy of its mod.json.

## Common questions
**Q: Where do mods go?**
A: In Documents/Vibe City/mods, one folder per mod, in the desktop client. The folder is created when the game starts.

**Q: Do mods work in the browser version?**
A: No. A browser tab cannot list a folder, so mods are desktop only.

**Q: Can a mod page reach the internet?**
A: No. Its CSP limits every source to vcmod:, data: and blob:, so all files must be inside the mod folder.

**Q: How many sprites does a mod need?**
A: Exactly 4 (one per camera angle) or 1 used for all angles, as png, webp or jpg.

**Q: How does a mod give the city money?**
A: Its page posts { vc: "pay", amount }. The game pays up to money.per_month per game month, nothing while the building lacks power or water, and answers with paid.

**Q: What happens to a save if a mod is removed?**
A: Its buildings turn to grass with a toast, but the lots and the mod's data are remembered and come back when the mod is reinstalled.

**Q: Why does my mod building not appear?**
A: Check the console and the "Mod trouble" toast. Common causes are a bad id, a sprite count other than 1 or 4, or an id clashing with another mod.

**Q: What author does Neon Brew use?**
A: "Beerus". Keep that in every copy of its mod.json.
