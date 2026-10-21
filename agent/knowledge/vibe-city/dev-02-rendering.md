# Vibe City: Rendering pipeline
Audience: developer
Keywords: rendering, render.js, canvas, isometric, isoPoint, TW, TH, projection, ground cache, worldChanged, groundPatch, draw order, drawOrders, depthFor, layers, sprites.js, lotSprite, span, nudge, facingFrame, FACING, variants, rotation, view modes, Utilities view, stamps, culling, zoom levels
Summary: Vibe City draws its isometric map onto one 2D canvas, back to front, in two passes: a cached ground layer and a live pass for buildings, vehicles and effects. This file explains the projection, the ground cache and how worldChanged invalidates it, the draw order, the sprite tables in js/sprites.js, rotation and the four view modes.

## Files that make up the renderer

In Vibe City, js/render.js owns the frame loop, the ground cache and the per-tile call order, and draws almost nothing itself. The work is handed to:
- render-ground.js: tile top colour (`tileTopColor`), the two visible cliff walls, ramps, and the road/track surface dispatch.
- render-structures.js: what stands on a tile (`drawTileStructure`): a sprite, else the older modelled block, else an icon; plus `drawUtilityBadges` and cars over the tile.
- render-roads.js, render-rail.js, render-ramps.js, render-portals.js: asphalt and lane marks, track and sleepers, sloped wedges, tunnel mouths.
- render-props.js: poles, wires, generator taps, fire, the saucer, `drawSkyTint`.
- render-stamps.js: the stamp cache (`drawStamped`, `drawTileStamped`, `drawTileTop`).
- render-buildings.js: `cornersAt`, diamonds, wall fills and `WALL_PLAN`.
- render-void.js: `coverVoid()`, which paints over overspill outside the map.
- render-wire.js: the whole Utilities view (`drawWireframeView`).
- render-fps.js: the "N fps, N ms draw" readout from Settings.
- water-tiles.js: water surface, shoreline and ripples. poles.js: where poles stand (a decision, not drawing).

## Isometric projection: isoPoint, TW and TH

Vibe City projects tiles with constants from js/constants.js: `TW = 32`, `TH = 18`. TH is not the textbook half of TW; it matches the roughly 1.787:1 ratio baked into the sprite art. Height uses `HILL_RISE = 46` over four hill tiers, so one land step `LAND_STEP` is 11.5 units.

js/canvas.js holds the maths:
- `rotateXY(x,y)` turns map coordinates for the current `rotation` (0..3); `invRotateXY` undoes it.
- `isoRaw(x,y)` returns `{x:(rx-ry)*TW/2, y:(rx+ry)*TH/2}` with no camera.
- `isoPoint(x,y,z)` adds height and camera: screen x = `camera.x + (rx-ry)*TW/2*camera.scale`, screen y = `camera.y + ((rx+ry)*TH/2 - z)*camera.scale`. Tile centres are `isoPoint(x+0.5, y+0.5, groundTopZ(i))`.
- `screenToTileF` solves the flat z = 0 plane; `pickTile(px,py)` is terrain-aware, testing the top diamond and visible walls of tiles within PICK_RADIUS 8, nearest the camera first. Picking is not building-aware, so clicking a tall sprite can land on a tile behind it.
- `fitCamera()` frames the whole map, clamping scale to 0.25..2.5. Wheel zoom steps through `ZOOM_LEVELS` in js/input.js: 0.25, 0.35, 0.5, 0.75, 1, 1.25, 1.5, 2, 2.5, 3, 4, 5, 6, 8.

## Draw order and rotation

Vibe City paints back to front. `buildDrawOrders()` in js/canvas.js precomputes `drawOrders[0..3]`, one array of tile indices per rotation, sorted by `depthFor(x,y,r)`: `x+y` at rotation 0, `(W-x)+y` at 1, `(W-x)+(H-y)` at 2 and `(H-y)+x` at 3.

`rotateView(dir)` (keys Q and E, or the rotate buttons) changes `rotation` and moves the camera so the point under the screen centre stays put; zoom is untouched. Multi-tile buildings are drawn once at `frontTileOf(i, rot)`, the block tile with the greatest depth, hung on `footprintCentre(i)`; the other tiles of the block draw nothing.

Vehicles, trains and ships are bucketed to tiles each frame (`bucketVehicles`, `bucketTrains`, `bucketShips`) so they draw in the same order as buildings and are hidden behind them correctly. A car goes with whichever tile under its tail, centre or nose draws last, with a ramp rule on top.

Culling: a tile is skipped unless its anchor is inside the canvas grown by `CULL_PAD_X` 40, `CULL_PAD_UP` 100 and `CULL_PAD_DN` (HILL_RISE + WATER_DIP + 40), all times camera.scale.

## The frame: ground pass then live pass

Each Vibe City frame in `render(now)`:
1. Advance clocks (`waterTime` always; vehicles, trains, ships, smoke, events, news and fallout only if `speed > 0`), apply key panning, round camera.x/y to whole pixels.
2. If `viewMode === VIEW_WIREFRAME`, call `drawWireframeView()` and stop.
3. Fill with VOID_COLOR, apply quake shake, build the visible list from `drawOrders[rotation]`.
4. `drawGround(dataView)` blits the cached ground. Then ripples (`drawAllRipples`) and ship wakes.
5. The live pass, per visible tile in order: restore cached ground over live things behind a cliff (`restoreGroundHere`), `drawTileStructure`, festival, power pole, `drawUtilityBadges`, tunnel marker, fire, flood, fallout or scorch, the hover diamond, ships, vehicles, trains, then wires or generator taps.
6. After the tiles: smoke, the UFO, disasters (`drawDisasters`), the footprint cursor outline and tool badge, fire hoses, the build plan, then `coverVoid()`, `drawSkyTint()` and `fpsSample()`.

The cached ground holds everything that stands still: tile tops, walls, ramps, tunnel mouths, water surface without ripples, roads and track. Poles are in the live pass so they stay above buildings behind them.

## The ground cache and worldChanged

The ground cache in js/render.js is an offscreen canvas the size of the viewport plus `GROUND_PAD` (320 px) on every side. Its signature `groundSig()` is canvas size, camera.scale, rotation, viewMode and `worldVersion`.

- Panning within `GROUND_STEP` (96 px) is a plain blit. Past it, `scrollGround` copies the cache across by whole pixels and paints only the uncovered strip (`paintGroundRect`).
- During a wheel zoom (`zoomInFlight`) the old cache is drawn scaled while it still covers the screen (`groundCovers`).
- When the world changed, `groundPatch` compares a per-tile fingerprint (`groundPrint`: types, levels, roadTier, rail overlay, tunnel, water, wire, pipe, powered, elevation and a hash of the top colour) and repaints only changed tiles plus a one-tile ring, grouped in 8x8 blocks (`GROUND_PATCH_BLOCK`), via `paintGroundRects`. Past `GROUND_PATCH_MAX` (1500) changed tiles it calls `buildGround` for a full rebuild.

`worldChanged(tilesOnly)` in js/state.js bumps `worldVersion`; without `tilesOnly` it also bumps `groundAllVersion`, which is part of `groundSigSansWorld()` and forces a full rebuild. Use `worldChanged(true)` only for pure tile-data changes (simTick's end, recomputePowerGrid, recomputeCoverages, recomputeWater, recomputeTunnels, recomputeRail). Anything that changes how the ground looks without changing tile data (a setting, a texture, fonts) must call plain `worldChanged()`. While `previewing` is true it does nothing.

## Stamps

js/render-stamps.js caches repeated tile pictures. `drawStamped(key, anchor, w, h, ox, oy, draw)` rasterises a picture once into a small canvas by temporarily pointing the global `ctx` at it and shifting the camera, then blits it at a whole-pixel anchor. The cache is keyed by `rotation|camera.scale` and cleared whenever either changes. Roads and rails are stamped below zoom 3 and drawn directly at or above it, because their grain and ballast must go on after the stamp. Snapping the anchor rather than the corner keeps every stamp on the same rounding as the tile top under it.

## Sprites in js/sprites.js

Vibe City sprites are PNGs under img/, one frame per rotation. Most tables follow one pattern: `XXX_VARIANTS` (usually 4), `XXX_SPRITE_SPAN[variant][rot]`, `XXX_SPRITE_Y_NUDGE[variant][rot]`, a loader filling `xxxSprites[variant][rot] = {img, loaded}` from `img/<dir>/V<v>_R<rot>.png`, `getXxxSprite` returning null until loaded (the caller then falls back), and `drawXxxSprite`.

- Span is the drawn width as a fraction of one tile width (`dw = span * TW * camera.scale`). Nudge is how far up the image the tile anchor sits: `dy = anchor.y - dh + dh*nudge`.
- Zoned lots use `RES_SETS`, `COM_SETS`, `IND_SETS` (files `img/<dir>/L<row>_R<rot>.png`) and `CONDO_SETS`; the set is a hash of the tile (`resSetFor`, `comSetFor`, `indSetFor`, `condoFor`) through `lookKey(i)` and `lookGrid`, so a migrated save keeps its buildings. `CONDO_SHARE` 0.4 of level 4 homes become condos.
- Civic: `CIVIC_SPRITES` for police, school, hospital and fire (`img/<dir>/R<rot>.png`).
- Variants are stored in `levels[]` as variant+1 for parks, trees, stations, statues, plazas, towers, pumps, universities, solar, libraries, wind, galleries and casinos; `xxxVariantAt` returns `(levels[i]-1) % N` or a position hash when 0.
- `lotSprite(img, dw, nudge, tiles)` trims each sprite once to its lot diamond (cached per span, nudge and tile count) so lot spill does not show over cached ground, and returns `lotMip(cv, dw)`, a halved copy no smaller than the drawn width.
- Power plant art: `POWER_ART_SETS`, `powerSpanFor(n)` per lot size.

## Facing: facingFrame and FACING tables

Some Vibe City buildings face their street instead of turning with the camera. `facingDir(x,y)` picks the adjoining road with the highest `roadTier`, ties going in the fixed order +y, +x, -y, -x, and +y with no road. `facingFrameMap(map, x, y, dir)` turns that into a screen side for the current rotation and returns `map[side]`, with sides ordered down-left, up-left, up-right, down-right. `facingFrame(t,x,y)` uses `FACING[t]`, or plain `rotation` if the type has no table.

Tables: `FACING_STD = [0,1,2,3]` for police, fire, hospital, school, gallery and casino (T.CLUB); arcade `[2,1,0,3]`; nightclub `[3,2,2,1]`. Resheeted residential tiers (`RES_SETS[n].facing`) and condos also use FACING_STD. Depots face their track (`stationFrameAt`), pumps face their water (`pumpFrame`). Libraries and universities are not covered. Span and nudge are looked up by the chosen frame.

## View modes

`VIEW_NORMAL` 0, `VIEW_POLLUTION` 1, `VIEW_CRIME` 2, `VIEW_WIREFRAME` 3, named in `VIEW_NAMES` as "City view", "Pollution map", "Crime map" and "Utilities". `setView(mode)` and `cycleView()` (key V, or the view button) live in js/input.js. The pollution and crime maps are data views: `tileTopColor` returns `dataViewColor(i)`, and buildings, vehicles, smoke and effects are skipped. The Utilities view is drawn entirely by `drawWireframeView()` in render-wire.js (mesh, water-need marks, then buried networks) and shares only the camera. Choosing the pipe tool switches to Utilities and `viewReturn` remembers the previous view.

## Common questions

**Q: How do I convert a tile to a screen point in Vibe City?**
A: `isoPoint(x + 0.5, y + 0.5, groundTopZ(idx(x,y)))` for the tile centre on its ground.

**Q: Why does my new ground feature not appear until I pan?**
A: The ground is cached. Call `worldChanged()` after changing what the ground shows.

**Q: When should I use worldChanged(true)?**
A: Only when tile data changed and nothing else, so the cache may patch. Appearance changes need plain `worldChanged()`.

**Q: What are span and nudge?**
A: Span is the sprite's drawn width in tile widths; nudge is the fraction of image height above the bottom where the tile centre sits.

**Q: How do I add a building that faces its road?**
A: Read which frame shows the door down-left, up-left, up-right and down-right and add a row to `FACING` in js/sprites.js.

**Q: Where is draw order defined?**
A: `drawOrders[rotation]` from `buildDrawOrders()` in js/canvas.js, sorted by `depthFor`.

**Q: Why are sprites trimmed by lotSprite?**
A: The ground is drawn first from the cache, so lot paint below the diamond's near edges would show as a rim; lotSprite cuts it once per sprite.

**Q: What does the Utilities view share with the city view?**
A: Only the camera. render() calls drawWireframeView() and returns before the tile walk.

**Q: What are the zoom limits?**
A: Wheel zoom steps between 0.25 and 8 using ZOOM_LEVELS; fitCamera clamps to 0.25..2.5.
