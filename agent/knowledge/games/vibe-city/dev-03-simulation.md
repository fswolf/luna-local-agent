# Vibe City: Simulation model
Audience: developer
Keywords: simulation, simTick, monthly tick, SPEED_MS, growth, growthPass, demand, calcDemand, economy, budget, taxes, upkeep, power grid, recomputePowerGrid, water, plumbing, recomputeWater, waterTick, coverage, services, pollution, crime, prison, mood, events, disasters, fire, festival
Summary: In Vibe City one simulation tick is one in-game month, run by simTick in js/simulation.js on a setInterval. Each tick recomputes the utility networks and coverage, settles pollution and crime, runs the reservoir, recomputes demand, grows or shrinks lots, applies the budget and rolls events. This file lists the order of a tick, the formulas and constants, and which file owns each system.

## The tick and its timing

The Vibe City simulation clock is `simTick()` in js/simulation.js, started by `setSpeed(s)` with `setInterval(simTick, SPEED_MS[s])`. One tick is one month. `SPEED_MS` in js/state.js is `[0, 4000, 1556]`: paused, normal and fast. The Settings pace slider (js/menu.js `applyPace`, stored as `prefs.pace`, default 4.0 seconds) sets normal to pace times 1000 ms and fast to that divided by `FAST_RATIO` (1800/700), never under 150 ms.

The order inside simTick:
1. `recomputeTunnels()`, `recomputeRail()`, `trainTick()`
2. `recomputeCoverages()` (power grid, water network, service, amenity and nightlife coverage)
3. `computeTotals()` (population and jobs)
4. `recomputePollution()`, `recomputeCrime()`
5. `waterTick()` (reservoir fills or drains)
6. `demand = calcDemand()`, `recordDemand()`
7. `growthPass()`, then `computeTotals()` again
8. `budget()`, `computePowerStats()`, `moodTick()`
9. `recomputeWater()` again for readouts, `advanceDate()`
10. `manageVehiclePopulation()`, `neighboursMonth()`, `milestonesTick()`, `cityNameTick()`, `eventsTick()`
11. `worldChanged(true)`, `updateHUD()`

Real-time things (vehicles, trains, ships, active events, the newspaper clock, fallout) are advanced by `render()` every frame instead, and only while `speed > 0`.

## Population, jobs and demand

In Vibe City `computeTotals()` derives everything from the map: each RES lot gives `level*10` residents, each COM lot `level*8` commercial jobs, each IND lot `level*10` industrial jobs. Working venues add jobs: CLUB_JOBS 12 per open casino or club, TRACK_JOBS 24, ARCADE_JOBS 14, PORT_JOBS 20 (industrial), PRISON_JOBS 30, plus mod jobs.

`calcDemand()` returns r, c and i, each clamped to -1..1:
- r = 0.5 - taxRate/25 + (jobs - pop)/300 + neighbour bonus
- c = 0.4 - taxRate/25 + (pop - 2*jobsC)/300 + neighbour bonus
- i = 0.55 - taxRate/30 - jobsI/400 + pop/1000 + neighbour bonus, then `portDemand(i)` from js/ships.js

`neighbourDemand()` (js/neighbours.js) adds demand for opened road and rail links to the four edge towns. `TAX_ZERO` records where each tax term reaches zero: c at 10, r at 12.5, i at 16.5. A coastal city past PORT_NEED_POP 2500 with no working port has industry held to PORT_CAP 0.2.

## Growth: growthPass

`growthPass()` visits every RES, COM and IND tile. Per-lot demand starts from the city figure and adds `festivalBonus`. Industry adds RAIL_FREIGHT_DEMAND 0.25 if `railServed[i]`. Homes and shops lose `POLLUTION_DEMAND_HIT` 0.45 times `pollutionLevel(i)` and `CRIME_DEMAND_HIT` 0.5 times `crimeLevel(i)` (half for shops); homes also lose PRISON_DEMAND_HIT 0.3 times `prisonNimby[i]`. Fallout empties lots (FALLOUT_EMPTY_CHANCE 0.35 a month) and scorched lots do not grow.

Rules, with growMul = 1 + 0.3 (service coverage) + 0.15 (amenity coverage):
- No adjacent road: 3 percent a month to lose a level.
- Level 0 with positive demand: becomes level 1 with chance 0.25*d*growMul if powered, 0.05*d*growMul if not.
- Built and powered: if dry (no mains) and above WATER_FREE_LEVEL 1, lose a level at WATER_SHRINK_CHANCE 0.10; else level up with `LEVEL_UP_CHANCE[level-1]*d*growMul` (0.045, 0.02, 0.008) up to `maxLevel(t)`, which is 4 for RES, COM and IND; negative demand loses a level at 0.12*|d|*shrinkMul.
- Built and unpowered: 8 percent a month to lose a level.

## Economy and budget

In Vibe City `computeBudgetStats()` fills `stats` without touching funds; `budget()` adds its result to `funds` once a tick. Income is `round((pop*0.6 + (jobsC+jobsI)*0.4) * taxRate/100 * 10)`. Monthly upkeep:
- Roads: 1 per street, 2 per avenue, 4 per highway tile; rail and crossings 2 each; depots 25.
- Civic: power plant 50, solar 5, wind 8, police 40, fire 40, school 30, hospital 45, university 90, library 20, gallery 25, casino and club 30 each, track 50, arcade ARCADE_UPKEEP 60, port PORT_UPKEEP 40, prison PRISON_UPKEEP 60, plus mods.
- Decor: park 4, plaza 6, statue 1, power line 1.
- Water: pump 35, tower 6, pipe 1.

Build prices are in `COST` in js/constants.js (for example road 10, avenue 25, highway 60, power plant 3000, solar 1500, wind 1000, pump 800, tower 250, pipe 12). `spend(cost)` in js/economy.js refuses with "Insufficient funds". New cities start with funds 20000 and tax 8.

## Power network

The Vibe City power grid is `recomputePowerGrid()` in js/simulation.js. Generators (`GENERATOR_MW`: plant 600, solar 150, wind 100 plus WIND_HILL_BONUS 0.25 per hill tier) light adjacent lines. Current runs line to line, into every `POWER_USER` within `POWER_SERVE_RADIUS` 1 of a line, and then building to building through touching power users, so a block conducts. Empty zoned lots conduct too. Solar and wind farms daisy-chain: a farm touching a wired farm is wired (`plantWired`). Big buildings count once, at their anchor (`isAnchor`).

Draw is `tilePowerDraw(i)`: `POWER_DEMAND_MW` 3, 4, 5 per level for RES, COM, IND; `PUMP_POWER_MW` 20; flat `CIVIC_POWER_MW` for civics (police 8, fire 8, school 10, hospital 16, university 30, library 6, casino 10, club 10, track 3 per tile, arcade 12, depot 6, port 4, prison 3). `computePowerStats()` sets `stats.powerDraw` (times `weatherPowerMult()`), `powerOutput` and `plantsWired`. A brownout is `powerDraw > powerOutput`. `CIVIC_POWER_MW` and the `POWER_USER` set must agree.

## Water network

Plumbing is js/plumbing.js. `recomputeWater()` floods `pipeLive` from every working pump (`pumpWorks`: powered and orthogonally beside water) through pipes, pumps and towers, then marks `watered` within `WATER_SERVE_RADIUS` 1 of a live main; a multi-tile building is watered whole. Supply is PUMP_OUTPUT 1200 per working pump; storage is TOWER_CAPACITY 2400 per tower on a live main. Draw is `WATER_DEMAND` 4, 5, 8 per level for RES, COM, IND plus flat `CIVIC_WATER`, times `weatherWaterMult()`.

`waterTick()` runs monthly: surplus fills `waterStored` up to capacity; a shortfall drains it, and `stats.drought` is set only when storage cannot cover the gap. `waterOk(i)` is `watered[i] && !stats.drought`. `recomputeWater` must run after `recomputePowerGrid`; `refreshWater()` is that pair for build tools. Water terrain is separate, in js/water-tiles.js.

## Services and coverage

`recomputeCoverages()` builds square catchments with `computeCoverage(radius, ok)`. A civic building only covers while `civicWorks(i)` (powered and watered). `SERVICE_REACH`: police, fire, school and hospital SERVICE_RADIUS 10, university 16, library 7, unioned into `serviceCov`. `AMENITY_REACH`: park, plaza, tree and statue AMENITY_RADIUS 4, gallery 8, track 8, casino and club CLUB_RADIUS 6, arcade 6 (plus a tile per rank its rival has lost, set in js/arcade.js), into `amenityCov` (decor needs no utilities; venues must be open). `nightlifeCov` uses CLUB_RADIUS 6 around open venues. `civicStatus(i)` gives "In service" or which utility is missing.

## Pollution, crime and prison

Pollution (js/pollution.js): per-tile emission, POLL_POWER_PLANT 55 per plant, POLL_IND_PER_LEVEL 7, POLL_COM_PER_LEVEL 1, POLL_RAIL_TILE 0.15, roads `POLL_ROAD_TIER` 1.2, 2.4, 5 times road activity ((pop+jobs)/1500, capped 1.5). Spread over POLLUTION_RADIUS 4 with linear falloff; each tree removes up to TREE_CLEAN 6 within 2 tiles. `pollutionLevel(i)` = field / POLLUTION_HEAVY 90, clamped 0..1.

Crime (js/crime.js): each open casino or club emits CRIME_CLUB 70 over CRIME_RADIUS 5; a working police station within 10 tiles cuts it by CRIME_POLICE_CUT 0.7. `crimeLevel(i)` = field / CRIME_HEAVY 60. Prison (js/prison.js): past PRISON_NEED_POP 3000, short of cells (`prisonShort`), level 3+ homes emit PRISON_LOOSE_CRIME 1.5 scaled by the shortage and the police cut weakens by up to PRISON_POLICE_LOSS 0.5. One prison holds PRISON_CELLS 40 at PRISON_PER_INMATE 250 residents each.

## Mood

`cityMoodNow()` scores 0..1 from `MOOD_WEIGHTS`: power 0.24, water 0.20, tax 0.18, air 0.14, services 0.12, safety 0.07, nightlife 0.05. Tax is free to MOOD_TAX_FREE 7 and worst at MOOD_TAX_SORE 20. Disasters add `MOOD_SHOCKS` (meltdown 0.30 over 18 months down to robbery 0.03), capped at 0.45. `moodTick()` eases the shown mood: MOOD_FALL 0.6, MOOD_RISE 0.25. Faces use MOOD_STEPS 0.28, 0.48, 0.68, 0.85, naming the city Furious, Unhappy, Getting by, Content or Thriving. Only built zoned lots are scored, so an empty map returns no score. The largest shortfall above MOOD_GRIPE_FLOOR 0.04 becomes the gripe line shown to the player.

## Events and disasters

js/events.js holds the `EVENTS` registry. General events roll once a month in `eventsTick()`, scaled by `eventRate` (the Random events slider): fire (FIRE_CHANCE_BASE 0.003, raised by industry share), robbery (0.007, cooldown 18 months), ufo (0.0015, pop 200+), weather (0.007, in season, cooldown 44), storm (0.005, cooldown 8), festival (0.0045, mood 0.62+, pop 300+). At most one starts per month, none while one is running, and a quiet spell of EVENT_QUIET_MONTHS 12 and EVENT_QUIET_S 900 running seconds follows each. Active events tick every frame in `updateEvents(dt)`.

js/disasters.js adds `kind: "disaster"` entries (flood, tornado, quake, meltdown, invasion) that never roll; `unleashDisaster(id)` starts them from the Disasters window, and "fire" starts a firestorm. js/milestones.js checks population and age milestones each month.

## Common questions

**Q: How long is a month in Vibe City?**
A: 4000 ms at normal speed and about 1556 ms on fast with the default pace of 4.0 seconds.

**Q: Where is growth decided?**
A: `growthPass()` in js/simulation.js.

**Q: Why is a civic building giving no coverage?**
A: Coverage requires `civicWorks(i)`, meaning both `powered[i]` and `watered[i]`.

**Q: Which order must power and water be recomputed in?**
A: `recomputePowerGrid()` then `recomputeWater()`, because pumps need power. `recomputeCoverages()` does both in order.

**Q: How is monthly income calculated?**
A: `(pop*0.6 + jobs*0.4) * taxRate/100 * 10`, rounded, in `computeBudgetStats()`.

**Q: How do I add a new power-drawing building?**
A: Add it to `CIVIC_POWER_MW` in js/constants.js and to `POWER_USER` in js/simulation.js; for water add it to `CIVIC_WATER`.

**Q: Do disasters happen randomly?**
A: No. Disasters are started only from the Disasters window; general events roll monthly.

**Q: What stops events from clumping?**
A: At most one general event a month, none while one runs, and a quiet spell of 12 months and 900 running seconds after each.

**Q: Where is pollution computed?**
A: `recomputePollution()` in js/pollution.js, once a month inside simTick.
