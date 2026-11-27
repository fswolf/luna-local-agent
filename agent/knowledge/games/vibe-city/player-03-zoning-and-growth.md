# Vibe City: Zoning and Growth
Audience: player
Keywords: zoning, zones, residential, commercial, industrial, RCI, demand, growth, level up, density, houses, shops, factories, jobs, population, tax rate, land value, pollution, crime, services, road access, power, water, shrink, empty lots
Summary: How residential, commercial and industrial zones work in Vibe City, how lots get built on and climb through four density levels, and what drives demand. It lists everything that speeds growth up, holds it back or makes buildings shrink, so you can work out why a district is or is not growing.

## The three zones
Zoning in Vibe City marks land for the city to build on; you never place houses, shops or factories yourself. There are three zone tools in the Zoning drawer of the toolbar:

- Residential Zone (Res): homes. Each level of a residential lot houses 10 people.
- Commercial Zone (Com): shops and offices. Each level gives 8 commercial jobs.
- Industrial Zone (Ind): factories. Each level gives 10 industrial jobs.

All three cost $50 per tile on low ground and $80 per tile on hill ground (1.6 times the price). Zones can only go on bare grass; trees in the way are cleared for free as you zone. A zoned tile starts empty, at level 0, and the city builds on it when it wants to. Drag to zone a rectangle: the price is shown before you let go, and tiles that cannot be zoned (water, roads, existing buildings) are skipped and not charged.

## What every lot needs
A zoned lot in Vibe City needs three things to grow well:

- Road access: a road on one of its four sides (not diagonally). Nothing is ever built on a lot no road reaches, and a built lot that loses its road loses a level now and then (a 3% chance each month).
- Power: a powered lot grows five times faster from empty, and only a powered lot can climb above level 1. An unpowered built lot loses a level 8% of the time each month. Power reaches a lot from a live line within 1 tile, and every zoned lot, built or empty, passes power to the lots and civic buildings touching it. A street between blocks breaks the chain; run a line across it.
- Water: without a water main within 1 tile, a lot can still reach level 1 (it has a well) but no higher. A lot above level 1 without water loses a level 10% of the time each month.

## Density levels
Every zoned lot in Vibe City has a level from 0 (empty) to 4. Residential, commercial and industrial lots can all reach level 4. So a full residential lot holds 40 people, a full commercial lot gives 32 jobs and a full industrial lot gives 40 jobs. The inspector shows a lot's level, such as "3 / 4".

Each level up is slower than the last. At full demand and with no help from services, the chance of climbing each month is:

- Level 1 to 2: 4.5%
- Level 2 to 3: 2%
- Level 3 to 4: 0.8%

Level 4 is something a district earns over decades. Some level 4 homes become a condo villa or an apartment block instead of a house. Each level adds to what the lot draws: 3 MW and 4 water per residential level, 4 MW and 5 water per commercial level, 5 MW and 8 water per industrial level.

## How an empty lot gets built
An empty zoned lot in Vibe City is built on only when demand for its zone is positive and a road reaches it. Each month the chance is 25% times the demand if the lot has power, or only 5% times the demand without power, multiplied by the growth bonus from services and amenities. So at full demand a powered lot fills in within a few months, while an unpowered one takes about five times as long. When demand drops below zero, nothing new is built and built lots can start losing levels.

## Demand and the RCI meter
Demand in Vibe City is a number from -1 to +1 for each zone, shown as the R, C and I bars in the top bar. Above the middle line the city wants more of that zone; below it wants less. Demand is worked out each month from the whole city:

- Residential demand starts at 0.5, falls as the tax rate rises, and rises when there are more jobs than residents.
- Commercial demand starts at 0.4, falls with the tax rate, and rises when there are more than two residents per commercial job.
- Industrial demand starts at 0.55, falls with the tax rate and with the number of industrial jobs, and rises slowly as the population grows.

Open connections to neighbouring towns add to demand: road links lift commercial most and residential with it, rail links lift industry. Together they are capped at +0.3 per zone. Click the meter for the Demand Report: a graph of the last 24 months, whether each line is rising, falling or steady, and a list of what is holding each zone back, worst first.

## Taxes and demand
The tax rate in Vibe City pushes down demand for every zone, and each zone gives up at a different rate. With nothing else pushing either way, commercial demand reaches zero at 10%, residential at 12.5% and industrial at 16.5%. A new city starts at 8%, and the slider in City Stats runs from 0% to 25%. Taxes of 12% or more are flagged in the Demand Report, and the city's mood suffers above 7%, as badly as it can by 20%. Lower taxes mean faster growth but less income.

## Jobs and people in balance
Balance between homes and jobs drives Vibe City's growth. If there are more people than jobs, residential demand drops and commercial and industrial demand rise, so zone shops and industry. Each commercial job wants about two residents; with fewer, commercial demand drops, so build homes first. Industry slows itself as it grows and picks up as the population does. Open venues add jobs too: a Casino or Club 12, an Arcade 14, a Track 24, a Prison 30 and a Seaport 20.

## Things that boost growth
Several things in Vibe City make lots grow faster or want to grow more:

- Service coverage: a working Police Station, Fire Station, School or Hospital covers 10 tiles around it, a Library 7 tiles and a University 16 tiles. Civic buildings only count while they have both power and water. A covered lot gets a 30% bonus to its growth chance and resists shrinking.
- Amenities: a Park, Plaza, Statue or Tree reaches 4 tiles, an Art Gallery or Track 8 tiles, a Casino, Club or Arcade 6 tiles. A lot in reach gets a 15% growth bonus. Amenities need no utilities, except the venues, which close without power and water.
- Rail freight: an industrial lot within 6 tiles of a working rail depot gets +0.25 demand. Homes and shops get nothing from it.
- A working Seaport lifts industrial demand across the city.
- A fair, which sets up on a park or plaza in a happy city, lifts commercial and residential demand within 5 tiles while it lasts.

## Things that hold growth back
Some things in Vibe City cut demand on individual lots, so a district can stall while the meter looks healthy:

- Pollution: homes and shops lose up to 0.45 demand on badly polluted ground. Industry does not mind. Keep factories and the power plant away from homes, and plant trees between them: each tree cleans the air within 2 tiles.
- Crime: homes lose up to 0.5 demand on rough streets, shops half that. Casinos and clubs bring crime; a working police station within reach cuts it.
- A prison: homes within 4 tiles lose up to 0.3 demand.
- No seaport: a coastal city of 2,500 people or more without a working seaport has its industrial demand held down to 0.2.
- Disasters: nothing grows on scorched ground after a meltdown until it cools, and lots inside a fallout zone empty out.

Vibe City has no land value number; a lot's appeal is its zone's demand plus these local effects.

## What makes buildings shrink
Buildings in Vibe City can lose levels as well as gain them. Each month a built lot may drop a level when:

- Its zone's demand is below zero: a 12% chance times how negative demand is, reduced by up to 30% for service coverage and 10% for amenities.
- It has no power: an 8% chance.
- It is above level 1 and has no water: a 10% chance.
- It has no road access: a 3% chance.
- It is in a fallout zone: a 35% chance.

A lot that drops to level 0 is an empty zoned lot again and can rebuild when conditions improve.

## Common questions
**Q: Why are my zones not building anything?**
A: Check that a road touches each lot on one of its four sides, that demand for that zone is above the middle line, and that the lots have power. Unpowered lots build very slowly. Click the RCI meter for a list of what is holding the city back.

**Q: Why do my buildings stay small?**
A: Lots without a water main in reach cannot grow past level 1. Lay water pipes from a powered pump to the district.

**Q: How many people live in a residential lot?**
A: 10 per level, so up to 40 at level 4.

**Q: What is the highest building level?**
A: Level 4 for residential, commercial and industrial lots.

**Q: Does Vibe City have land value?**
A: No. Growth comes from zone demand plus local effects: pollution, crime, service coverage, amenities, rail freight and nearby prisons.

**Q: What tax rate should I use?**
A: Below 10% every zone still wants to build. Commercial stalls from 10%, residential from 12.5% and industrial from 16.5%. The default is 8%.

**Q: Why is residential demand falling?**
A: Usually because there are more residents than jobs, or taxes are too high. Zone commercial or industrial land so people have work.

**Q: Why are homes near my factories not growing?**
A: Pollution cuts residential and commercial demand. Move industry further away or plant a belt of trees between them.

**Q: Do I need power lines down every street?**
A: No. Zoned lots and civic buildings pass power to whatever touches them, so a block lights up from one connection. Only a street between blocks breaks the chain.
