# Vibe City: Art and Sprite Pipeline
Audience: developer
Keywords: sprite, sprite strip, sprite sheet, 1x4 strip, template, check-strip, slice-houses, install-strip, fit-slab, square-plot, base plate, span, nudge, facing, FACING_STD, variants, lotSprite, transparency, alpha, img folder, art, PNG, camera views, rotation
Summary: How building art gets into Vibe City, from a generated 1x4 strip to a sliced, fitted and installed sprite. Covers the templates, the screening and slicing tools, the span and nudge numbers the renderer hangs a sprite by, the facing tables, the variant tables in js/sprites.js, and the img/ folder layout.

## The sprite strip: one building, four camera views
In Vibe City a building sprite arrives as a 1x4 strip: one row of four pictures of the same building, and each column is one camera view. The game has four camera rotations (Q and E turn the world), so a strip supplies one picture per rotation. Older sheets were 4x4: each row a variant or growth tier, each column a rotation. The four columns must be four quarter turns of ONE building on a turntable, not four different buildings and not a repeated view. Generated sheets get this wrong often enough that tools/check-strip.py exists to catch it before anything is sliced. The tile in Vibe City is TW x TH = 32 x 18 (js/constants.js), so a plot's lower edges slope 0.5625, nine pixels down for every sixteen across, and every template is drawn at that shape.

## Templates: tools/make-*-template.py
Vibe City ships one PIL template script per kind of strip. Each draws grey plots at the game's exact 16:9 ground shape plus markers the image model must keep in place:
- tools/make-house-template.py: a 2172x724 strip of 500px one-tile plots with a street bar and a blue door dot walking front-left, back-left, back-right, front-right (the FACING_STD order).
- tools/make-park-template.py: 4x4 and 1x4, plot 473x266, a 16:9 ellipse for the round feature and a red dot walking N, W, S, E.
- make-power, make-port (2x2), make-prison and make-track (3x3) templates split plots into tiles; make-pump, make-tower and make-ufo cover the rest.
The canvas aspect matters: the renderer takes a sprite's height from the image's own height to width ratio, so the template's frame decides how tall the building stands on the map.

## Screening a strip with tools/check-strip.py
Run `python3 tools/check-strip.py <strip.png>` on every generated 1x4 strip before slicing. In Vibe City this script prints PASS, or FAIL with reasons, and exits 1 on failure. It checks:
- a real alpha channel. An RGBA image whose minimum alpha is above 10 fails with "no real transparency (checkerboard or JPEG?)".
- exactly four pictures, split at the emptiest column near each quarter line. A view under 8 percent of the ink is "missing or tiny", and views whose split column carries over 25 percent of the peak are "running into each other".
- each plot's lower edge slope, fitted out from the bottom vertex. Accepted art measures 0.47 to 0.72 here (about 0.64 is ideal), because the slab bottom reads a little steeper than the grid's 0.5625.
- the four plot widths agree within 8 percent.
- no two views are the same picture (a mean difference under 0.3 of the spread).

## Slicing: tools/slice-houses.py and the base plate
`python3 tools/slice-houses.py <sheet.png> <out-dir> [ROWSxCOLS]` slices a sheet into <out>/L{row}_R{col}.png; the grid defaults to 4x4 and a strip is 1x4. In Vibe City it isolates cells by thresholding alpha at 64 and labelling connected components (scipy ndimage), never by a fixed grid, and drops anything under 200 pixels. Components are grouped by the cell their centroid falls in, and two touching buildings are split at the thinnest scanline near the grid line. The base plate is found by walking UP from the bottom of the smoothed width profile to the first sustained peak, not the widest row. The slice is then padded so the plate centre is the image centre, and the script prints JSON with span = imgW / plateW and nudge = 1 - plateRow / imgH. The check value short_by compares the slice bottom with predicted_bottom = plateRow + plateW * (18/32) / 2. Civic slabs that are not true diamonds are fitted from their two lower edges by tools/fit-slab.py instead, and 2x2 or 3x3 lots by tools/fit-power.py or tools/fit-block.py.

## How span and nudge hang a sprite
The Vibe City renderer places a sprite by its base plate, not its bounding box. In js/sprites.js the draw is:
- dw = span * TW * camera.scale (times n tiles for a multi-tile lot)
- dh = dw * img.height / img.width
- drawImage at (anchor.x - dw/2, anchor.y - dh + dh * nudge)
So span is how much wider the picture is than the tile (shipped values sit near 1.01 to 1.06) and nudge is how far up from the picture's bottom, as a fraction of its height, the tile centre sits (shipped values about 0.29 to 0.48). A horizontal stretch by tools/square-plot.py (k = slope / 0.5625) fixes a plot drawn too steep and leaves span and nudge unchanged. Every ctx.drawImage of a building sprite must go through lotSprite(img, dw, nudge, tiles), which trims the art to its tile diamond once, caches the result per geometry in a WeakMap, and since b534 keeps halved mip copies via lotMip so zoomed-out maps stay fast.

## Installing a strip with tools/install-strip.py
`python3 tools/install-strip.py <strip.png> <dir> <tier 0-3>` is the one-step install for zoned buildings in Vibe City. It runs slice-houses.py on the strip as 1x4 in a temp folder, copies the four slices to img/<dir>/L{tier}_R{0..3}.png, and rewrites js/sprites.js in place: the span and nudge rows for that tier in the set whose `dir:` matches (RES_SETS, COM_SETS or IND_SETS), and the set's `facing:` flag for that tier, set to true with the comment "tiers resheeted for 1.0.0, door to the street (FACING_STD)". It prints the dir, tier, span, nudge and facing flags. The strip's columns must therefore be in FACING_STD order. A one-building strip for another type is sliced by hand with slice-houses.py or a fit tool and wired into its own table.

## Facing tables: FACING_STD and friends
Since 1.0.0 b496 a civic building or venue in Vibe City turns its front door to the adjoining road instead of turning with the camera. In js/sprites.js, `FACING_STD = [0, 1, 2, 3]` names the frame showing the door down-left, up-left, up-right and down-right on screen (DL, UL, UR, DR). The FACING table maps types to these lists: police, fire, hospital, school, gallery and club use FACING_STD; the arcade is [2, 1, 0, 3] and the nightclub [3, 2, 2, 1]. facingDir(x, y) picks the widest adjoining road (ties broken in a fixed world order, +y with no road), and facingFrameMap(map, x, y, dir) converts that to a frame for the current rotation. Zoned sets carry per-tier `facing` flags: all four RES_SETS tiers are true, COM_SETS has only tier 0 true. The pump uses facingFrameMap with its water direction, and mods can declare `facing` in mod.json.

## Variant tables in js/sprites.js
Each sprited building type in Vibe City has a block in js/sprites.js: a <NAME>_VARIANTS count, <NAME>_SPRITE_SPAN and <NAME>_SPRITE_Y_NUDGE tables (per variant, per rotation), an Image table, get<Name>Sprite and draw<Name>Sprite. Counts today: PARK, STATION, STATUE, PLAZA, TOWER, PUMP, UNIVERSITY, SOLAR, LIBRARY, WIND, GALLERY and CLUB are 4; TREE_VARIANTS is 16; UFO_VIEWS is { blue: 4, amber: 4, purple: 4 }. Zoned art lives in RES_SETS, COM_SETS and IND_SETS (four sets each, 4 tiers x 4 rotations, span[tier][rot]); the set a lot uses is a position hash (resSetFor, comSetFor, indSetFor). Civic art is CIVIC_SPRITES with per-rotation span and nudge. The variant is rolled at placement in applyTool (js/economy.js) and stored as variant+1 in levels[], so 0 means built before the art and falls back to a hash. A number means variants 0..n-1; an array such as CLUB_IN_USE = [0, 1, 2, 3] limits which are used without renumbering files.

## Transparency rules
Every Vibe City sprite is an RGBA PNG with real transparency. A painted checkerboard or a JPEG background is rejected by check-strip.py. The slicers treat alpha above 64 as solid; tools/fit-block.py also hardens a generated halo (alpha under 96 becomes 0, 236 and over becomes 255). Keep the whole building inside its ground slab: anything that spills past the tile diamond on the near side is trimmed by lotSprite. A sprited type should also lose its PALETTE entry in js/colors.js so dark ground shows round the art.

## Sprite widths and the img/ folder layout
Several one-tile sets in Vibe City ship about 300px wide (img/ind L0 slices are 297 to 300px, img/pump and img/tower 300px, img/station about 292 to 309px), and around 300px is the recommended target for a one-tile building. The house, shop and civic sets are larger, about 510 to 560px, and lotMip shrinks them at draw time. Bigger lots scale up: img/power about 555 to 577px, img/prison and img/port about 680 to 727px, img/track about 1410 to 1468px. Folder naming:
- V{v}_R{r}.png: variant sets (park, station, club, statue, plaza, tower, pump, university, solar, library, wind, gallery).
- L{tier}_R{r}.png: zoned sets img/res..res4, com..com4, ind..ind4.
- R{r}.png: single buildings (police, fire, hospital, school, condo, condo2, arcade, nightclub, power, prison, port, track).
- img/trees/V0..V15.png, img/ufo/<colour>_R{n}.png, img/vehicles/<colour>_A..C.png, img/ground, img/news.
- Portraits: img/arcade/<id>-<face>.png, img/dealer/<name>_<face>.png, plus img/advisor, archivist, bookie, teacher.
Retired art goes on tools/retired-assets.txt for tools/prune-assets.sh.

## Common questions
**Q: What order do the four columns of a strip go in?**
A: One column per camera view. For street-facing art they follow FACING_STD: front door down-left, up-left, up-right, down-right, which is the order the house, pump and prison templates walk.

**Q: How do I check a generated strip before using it?**
A: Run python3 tools/check-strip.py <strip.png>. It needs real alpha, four separate views, plot slopes between 0.47 and 0.72, widths within 8 percent and no repeated view.

**Q: What do span and nudge mean?**
A: span = image width / plate width, and nudge = 1 - plate row / image height. The renderer draws dw = span * TW * scale wide and hangs the picture so the plate centre lands on the tile centre.

**Q: Which tool installs a house, shop or factory tier?**
A: python3 tools/install-strip.py <strip.png> <dir> <tier>. It slices, copies to img/<dir>/L<tier>_R*.png and writes span, nudge and the facing flag into js/sprites.js.

**Q: Why does my new building show a dark rim?**
A: Its draw function is not going through lotSprite, or its PALETTE entry in js/colors.js is still there.

**Q: How wide should a one-tile sprite be?**
A: About 300px wide is the target, matching img/ind, img/pump and img/tower. Larger art works because lotMip downsizes it.

**Q: How is a variant picked?**
A: applyTool in js/economy.js rolls it at placement and stores variant+1 in levels[]. A 0 falls back to a position hash.
