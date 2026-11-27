# Vibe City: House Style and Conventions
Audience: developer
Keywords: conventions, house style, code style, compact code, comments, build tags, b538, Ryan, text rules, no semicolons, no dashes, no emoji, plain sentences, logo, wordmark, pink, blue, Kit, rival kid, Beerus, mod author, version 1.0.0, build bump, index.html, vanilla JS, use strict
Summary: The standing rules for working on Vibe City: how code and comments are written, the rules for any text a player reads, the brand and character rules, and the shipping rules (release stays 1.0.0, only the build bumps, and index.html always ships with a bump).

## Code style: compact vanilla JavaScript
Vibe City is vanilla JavaScript with no modules and no build step. Every file in js/ starts with "use strict", there is no import or export anywhere, and index.html loads each script with a plain script tag carrying ?v=<build>. Globals are shared between files on purpose, which is also what lets prof rigs call applyTool, setType and recountAll directly from page.evaluate. The game runs from file://, so there is no fetch, no XHR and no dynamic import; every asset is a plain img, audio or script src. Code is compact: short helpers, one-line guards, small arrow functions and dense tables over long ceremony. Ryan prefers compact code with minimal explanation. Keep files reasonably small and split them rather than letting one grow huge; rendering is already split into render-buildings.js, render-roads.js, render-props.js, render-structures.js and more. Constants live in js/constants.js; sprite tables in js/sprites.js.

## Comment style: say why, with a build tag
A Vibe City comment explains WHY the code is the way it is, usually the bug or request that caused it, and carries a build tag in brackets so the history can be traced. Real examples from the code:
- "(b538, Ryan)" style tags, such as "// b538: Ryan's third batch" in js/park.js.
- "Facing the street (1.0.0 b496, Ryan: "the doors never face the road")" in js/sprites.js.
- "(b544, Ryan)" on parks not being a player folder, "(b534)" on the lotMip speed fix.
- Older code uses version tags such as "(0.9.115, Ryan)" or "(0.78.50)".
Quote Ryan's own words when the change came from him. Describe the failure a line prevents, not what the line does, and keep history notes (what was tried and reverted) where they stop someone repeating a mistake. Rigs in prof/ open with the same kind of comment saying what they pin down and which build it came from.

## Player facing text rules
Any text a Vibe City player reads (toasts, tooltips, window text, newspaper stories, character lines, park lines) follows Ryan's rules against "AI-style" punctuation:
- no semicolons;
- no dashes of any kind, neither en or em dashes nor a spaced hyphen; the newspaper also allows no hyphenated words;
- no emoji anywhere in the game UI; icons are drawn art or Hugeicons, and the slot symbols are drawn rather than typed so no emoji font can swap in;
- plain short sentences.
Many rigs enforce this with a regex that rejects a semicolon, an em dash, an en dash or a spaced hyphen, plus `!/\p{Extended_Pictographic}/u.test(text)` for emoji, for example prof/roadover.js, prof/dealer.js, prof/tooltips.js and prof/newsstyle.js (two hundred printed editions). Park lines also avoid colons, stay plain ASCII and end with . ! or ?. Code comments are not player text and may use any punctuation.

## Brand and character rules
The Vibe City logo stays pink and blue. The wordmark is defined once in style.css for the HUD and the About window (.hud-brand, .about-brand): the lettering is pink #ff168d in the VC Sans font, uppercase at weight 900, and the mark before it is img/vibe-city-mark.svg, a skyline drawn in cyan blue #00e3d2. Do not recolour it to match a window theme; other windows went warm and serif while the logo kept its colours. img/vibe-city-mark.svg and img/vibe-city.ico belong to the app and must never be caught by tools/retired-assets.txt. Kit is the rival kid: the cocky cat boy at the arcade cabinet (ARCADE_RIVALS id "kit", colour #ff3d9a, ranks Rookie, Hotshot, Arcade King, Dethroned, portraits img/arcade/rival-*.png). Beating him all the way down unlocks his big brother Rue. Kit also turns up in park pictures and drops into Neon Brew for a hot chocolate. Keep his voice: boastful, never admitting a loss.

## Mod rules
Vibe City mods are a separate download and never part of the base game. In Neon Brew's mod.json keep `"author": "Beerus"`; Ryan set it in the installed copy, and every copy must match. Never change a published mod's id, because saves remember mod buildings by id. The mod API's compatibility promises started with release 1.0.0, so a change that breaks existing mods is a major version, not a patch. Mod pages run sealed with no network; do not loosen the sandbox, PAGE_CSP or the vcmod:// path rules to make a mod easier to write.

## Versioning rules: 1.0.0 stays, the build bumps
Vibe City's release is 1.0.0 (reached 10 Oct 2026 at build 492) and it stays 1.0.0; only GAME_BUILD moves, and it was b547 at the time of writing. Every ship runs `./tools/bump.sh` with NO argument, which bumps the build only. Do not run bump.sh patch, minor or major unless Ryan asks; moving the version is his call, and in the past a self-chosen version bump (0.9.62 to 0.10.0) read to him as a step backwards. prof/version.js holds the major at 1, so a major bump fails the suite on purpose.

## Shipping rules: always ship index.html with a bump
Because bump.sh rewrites every ?v= cache-buster in index.html, index.html changes on every Vibe City ship, and it must always ship together with js/constants.js and the changed files. Shipping the code without the new index.html leaves the browser loading old copies of files with nothing on screen to say so. Other standing rules:
- run ./tools/make-playlist.sh after changing music, effects, gallery, parks or clubs, and never hand-edit the generated lists;
- run ./tools/suite.sh before shipping, one suite at a time;
- never delete art directly; list it in tools/retired-assets.txt with a note and let ./tools/prune-assets.sh --yes remove it;
- never copy the game into release/; prof/version.js fails if release/index.html appears;
- keep contextIsolation, sandbox and nodeIntegration false as they are in release/main.js.

## Rules learned from bugs
A few Vibe City rules exist because breaking them shipped a bug:
- A save records what was built. If a value is baked into saved data, the data carries it; a constant like FOOTPRINT describes what to build next, never what was built before. FOOTPRINT is read only in placeFootprint.
- Every building sprite draw goes through lotSprite.
- A rig must never write a constant down; compute from footprintOf and friends.
- Saved counters are not trusted: loadCityText calls recountAll().
- If a bug only happens while the mouse moves, applyTool rigs cannot see it; drive a real pointer.

## Common questions
**Q: What punctuation is banned in game text?**
A: Semicolons and dashes of any kind, and emoji. Park lines also avoid colons. Use plain short sentences.

**Q: How should a code comment look?**
A: Explain why, name the bug or request, and tag the build, for example "(b538, Ryan)" or "(1.0.0 b496, Ryan: ...)".

**Q: What colours is the logo?**
A: Pink lettering (#ff168d) with a cyan blue skyline mark (#00e3d2). It stays pink and blue.

**Q: Who is Kit?**
A: The rival kid at the arcade, a cocky cat boy whose portraits are img/arcade/rival-*.png. Beating him unlocks his brother Rue.

**Q: What author goes in Neon Brew's mod.json?**
A: "Beerus". Keep it in every copy.

**Q: Should I bump the version for a fix?**
A: No. The release stays 1.0.0. Run ./tools/bump.sh with no argument, which bumps only the build.

**Q: Why must index.html ship with every bump?**
A: It holds the ?v= cache-busters that bump.sh rewrites. Without it the browser keeps serving stale files.

**Q: Does Vibe City use ES modules or a bundler?**
A: No. It is vanilla JavaScript with "use strict" in every file, loaded by plain script tags from file://.
