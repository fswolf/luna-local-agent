# Vibe City: Testing with prof Rigs and the Suite
Audience: developer
Keywords: test, testing, rig, prof, suite, suite.sh, failing, 0 failing, playwright, chromium, headless, screenshot, allow-file-access-from-files, node, regression, exit code, version.js, electron test, xvfb, flaky, assertions
Summary: Vibe City is tested by node scripts in prof/, called rigs, that drive the real game in headless Chromium through Playwright and print "N failing". tools/suite.sh runs every rig, checks exit codes as well as output, and takes about 17 minutes. This file covers running the suite, writing a rig, and taking headless screenshots.

## What a prof rig is
A Vibe City test rig is a plain node script in prof/ (prof/defaults.js, prof/roadover.js, prof/version.js and about 150 scripts in all). There is no test framework. A typical rig launches headless Chromium with Playwright, opens the game from file:// on index.html, drives it with page.evaluate (calling the game's own globals such as applyTool, setSpeed, recountAll), and checks results with a tiny ok() helper that prints "ok" or "FAIL name - detail". It ends by printing a blank line and "N failing", where N is the number of failed checks, then calls process.exit(fail ? 1 : 0). Some rigs need no browser at all: prof/version.js reads index.html and js/constants.js straight from disk, and prof/client.js and prof/asar.js inspect the packaging. The prof/ folder also holds one-off probes and screenshot scripts that never print "failing"; those are not part of the suite and several are stale.

## Running the suite: tools/suite.sh
`./tools/suite.sh` runs every Vibe City rig whose file contains the word "failing" (128 files in prof/ at b547), one after another with node, in name order. `./tools/suite.sh water` runs only rigs whose names contain "water". A rig counts as clean only if it exits 0 AND printed "0 failing". For anything else the script prints "--- name (exit code)", the first four FAIL lines, the first two error lines, and "(no count printed - it did not reach the end)" when a rig crashed before its count. The last line is "N suites clean" or "N clean, M NOT CLEAN: names", and the script exits 1 if anything failed. The exit code check exists because an older grep-only one-liner reported crashed rigs as clean. A full run takes about 17 minutes. Never run two suites at once: rigs share the machine's browser, write screenshots into prof/, and prof/client.js rebuilds dist/stage, so two runs collide and produce false failures.

## The minimal rig
Every Vibe City browser rig follows the same shape:
- `const { chromium } = require('playwright');`
- `let fail = 0; const ok = (name, cond, info) => { console.log((cond ? 'ok  ' : 'FAIL') + ' ' + name + (cond ? '' : ' - ' + info)); if (!cond) fail++; };`
- launch: `chromium.launch({ executablePath: '/opt/pw-browsers/chromium', args: ['--allow-file-access-from-files'] })`
- `const page = await browser.newPage({ viewport: { width: 1200, height: 800 } });`
- collect errors: `page.on('pageerror', e => errors.push(String(e)))`
- `await page.goto('file://' + path.resolve(__dirname, '../index.html'));` then `await page.waitForTimeout(1200)` or so for start up.
- one or more `page.evaluate(() => { ... })` blocks that set up a scene and return plain data.
- ok() checks, ending with `ok('no page errors', errors.length === 0, errors.join(' | '))`.
- `console.log('\n' + (fail ? fail + ' failing' : '0 failing')); await browser.close(); process.exit(fail ? 1 : 0);`
Start the file with a comment saying what the rig pins down and why, with the build tag of the bug or feature.

## Chromium and file access
Vibe City rigs use the Chromium build at /opt/pw-browsers/chromium, passed to Playwright as executablePath. The game is opened from file://, and the flag --allow-file-access-from-files is passed so the page can read its own local files the way it does in Firefox from a folder. Nearly every browser rig launches with that flag. Rigs that need a real web origin (prof/mods.js serves the game over local http because a sandboxed frame will not load file://) start their own server. Desktop shell rigs use Playwright's Electron driver, `const { _electron: electron } = require('playwright')`, launched with --no-sandbox, under xvfb when there is no display; Chromium refuses to start sandboxed as root, which is how the rigs run.

## Headless screenshots
To look at Vibe City without a display, write a short Playwright script that loads the page, sets the camera and takes a screenshot. The pattern used in prof/:
- set up state in page.evaluate: `setSpeed(0); setView(VIEW_NORMAL); rotation = 0; camera.scale = 2.4;`
- centre a tile: `const q = isoRaw(x + 0.5, y + 0.5); camera.x = canvas.width/2 - q.x*camera.scale; camera.y = canvas.height/2 - q.y*camera.scale; hoverTile = null;`
- wait a few hundred milliseconds for a frame, then `await page.screenshot({ path: 'prof/name.png', clip: { x, y, width, height } })`.
A save can be loaded with `page.setInputFiles('#file-load', '<path to save.json>')`. Screenshot scripts usually print page errors rather than "N failing", so they stay out of the suite. Read the PNG afterwards to check the result by eye.

## Building a scene: clear the whole map
Most Vibe City rigs start by wiping the generated map, and the wipe must clear every per-tile array, not just the type. The loop used in prof/roadover.js is: `for (let i = 0; i < W*H; i++){ hasWater[i]=0; elev[i]=elevForLand(0); setType(i,T.GRASS,0); roadTier[i]=0; wireOverlay[i]=0; railOverlay[i]=0; isTunnel[i]=0; pipes[i]=0; anchorAt[i]=-1; } recountAll();`. Ten rigs once left out hasWater[i] = 0; the map looked empty but the terrain's lakes were still there, so building failed about one run in three with "Part of that square is under water". Clear and then call recountAll() (and computeTotals() where population matters) so counters match the empty map. Set funds = 1e6 and setSpeed(0) so the simulation does not move under the test.

## Rules for writing rigs
Lessons from Vibe City's history, each of which cost a shipped bug or a lost afternoon:
- Never write a constant down. Compute positions from the code: `const n = footprintOf(T.POWER); applyTool('power', 4 - n, cy - (n - 1));` instead of hard-coded coordinates for a 4x4 plant.
- State the relationship you need, not the setup. When a building gains a prerequisite (rail depots began needing power and water at 0.9.10), a rig that restated the old setup breaks silently, so share the setup in one place.
- When a test passes alone and fails in the suite, dump the state at the moment of failure before touching a timeout.
- Pin Math.random for statistical rigs with a seeded generator, as prof/evpace.js does (`Math.random = seeded(20260920)`), so bands do not fail one run in six.
- Bugs that only happen while the mouse moves are invisible to applyTool. prof/planstate.js drives a real pointer for that.
- Check text rules too: many rigs assert no semicolons, dashes or emoji in what a window says.

## Rigs worth knowing
A few Vibe City rigs cover the tooling rather than gameplay:
- prof/version.js: GAME_VERSION is semver with major 1, every ?v= in index.html equals GAME_BUILD, nothing untagged. bump.sh runs it.
- prof/about.js: the About window shows both numbers from the constants.
- prof/client.js: build-client.js --stage-only works, the stage has the shell and game, no prof, tools, saves, retired or wav files, and versions agree.
- prof/asar.js: the release is packed with asar and the Documents lookups cannot escape their folders.
- prof/assetlist.js: release/assets.js lists exactly what make-playlist.sh writes.
- prof/mods.js: the whole mod system, shell and game halves.
- prof/ufo.js, prof/houses.js, prof/comsets.js: sprite tables match the art on disk.

## Common questions
**Q: How do I run all the tests?**
A: ./tools/suite.sh from the game folder. It runs every prof rig that prints "failing" and takes about 17 minutes.

**Q: How do I run only some rigs?**
A: Pass a substring: ./tools/suite.sh water runs only rigs with "water" in the name. Or run one directly with node prof/<name>.js.

**Q: Can I run two suites at the same time?**
A: No. Runs share screenshots in prof/ and the dist/stage folder, and they collide. Run one at a time.

**Q: What makes a rig count as clean?**
A: Exit code 0 and the line "0 failing". A crash or a missing count line is reported as not clean.

**Q: Which browser do the rigs use?**
A: Playwright's chromium at /opt/pw-browsers/chromium, launched headless with --allow-file-access-from-files, opening index.html over file://.

**Q: Why does my rig fail only sometimes?**
A: Usually leftover terrain state, such as hasWater not cleared, or an unpinned Math.random. Dump the state when it fails.

**Q: How do I take a screenshot of the game headless?**
A: Load the page with Playwright, set camera.scale, camera.x and camera.y in page.evaluate, wait briefly, then page.screenshot with a clip.

**Q: How do I test the desktop app?**
A: Use Playwright's _electron driver with --no-sandbox, under xvfb when there is no display, as prof/client.js, prof/asar.js and prof/mods.js do.
