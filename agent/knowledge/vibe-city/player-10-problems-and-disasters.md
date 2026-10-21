# Vibe City: Pollution, Crime, Fires and Disasters
Audience: player
Keywords: pollution, smog, air, crime, robbery, fire, firestorm, lightning, storm, heatwave, cold snap, weather, disaster, flood, tornado, earthquake, quake, meltdown, fallout, alien invasion, UFO, saucer, smoke, pollution map, crime map
Summary: Vibe City has two map-wide problems, pollution and crime, each shown on its own data view and each lowering demand where it is bad. Fires, robberies and storms happen at random, while flood, tornado, earthquake, meltdown, alien invasion and firestorm happen only when you choose them in the Disasters window. This page explains each one and how to prevent or handle it.

## Pollution
Pollution in Vibe City is a field over the map. Each source pollutes its own tile most and fades to nothing 4 tiles away. The sources:

- Power plant: 55 per plant, the largest single source.
- Industrial lots: 7 per building level.
- Commercial lots: 1 per level.
- Roads: street 1.2, avenue 2.4, highway 5 per tile, scaled by how busy the city is (none on an empty grid).
- Rail: 0.15 per tile, close to nothing.

Solar and wind farms do not pollute. Each tree removes up to 6 from its own tile, fading out 2 tiles away.

A tile at 90 or more counts as badly polluted. Homes and shops lose up to 0.45 of their demand on polluted ground; industry does not mind. The air share of the city mood (14%) falls as the city average rises ("The air is filthy"). The inspector labels each tile Clean, Light, Moderate, Heavy or Severe.

## Reading pollution and smoke
Press V to cycle the map views: City view, Pollution map, Crime map, Utilities. The Pollution map hides buildings and colours the ground from dark green (clean) through yellow and orange to red (filthy). City Stats shows Pollution: emitted per month, cleaned by trees, the worst tile and the city average. The Demand panel warns "N homes breathing smog".

Smoke in Vibe City is the visible puff from power plant chimneys: a grey puff about every half second per plant, rising and fading over about 3 seconds. It is only drawn while the game is running and is hidden in the data views. Burning tiles also show flames and a column of smoke until the fire is out.

To prevent pollution problems, zone industry away from housing, use solar or wind instead of a power plant near homes, move freight onto rail, and plant trees as a buffer.

## Crime
Crime in Vibe City is a second field, shaped like pollution. Each open casino and club puts 70 into the ground, fading out over 5 tiles. A shut club (no power or water) makes none. The Track and Arcade make no crime. When the city is short of prison cells (past 3,000 people), homes at level 3 and up also make crime.

A working police station removes 70% of the crime on every tile within its 10-tile reach, less if the city lacks prison space. A tile at 60 or more counts as a bad neighbourhood; homes there lose up to 0.5 of their demand and shops half that. The safety share of the mood (7%) falls with crime where people live ("The streets are not safe at night").

The Crime map view colours crime from dark to red. Inspector labels run Safe, Petty, Rough, Dangerous and Lawless, with "patrolled" where police cover the tile. Fix crime by putting a police station within 10 tiles of your nightlife and building a prison past 3,000 people.

## Robbery
A robbery is a random event in Vibe City that only happens where crime is at least half of the bad-neighbourhood mark. Lots with no police cover are three times as likely to be targeted. When one happens, $1,000 is taken from the treasury at once and a black getaway car drives off. After a 5-second head start, police cars chase it. If they catch it within 75 seconds the money is returned ("Getaway car stopped, $1,000 recovered"). After a robbery there is an 18-month gap before another can happen. Robberies shake the city a little: a 3% mood drop fading over 4 months.

## Fire
Fires break out at random on built lots, industry most often. The chance is about 0.3% a month for a city with no industry, rising to as much as three times that with heavy industry. Fire spreads from a burning tile to each neighbour with a 60% chance every 2 seconds (40% to trees and parks). A tile burns down after 9 seconds: a building is emptied to a bare zoned lot, and a tree or park becomes grass. Wooden power poles burn too and cut the line.

Fire engines from your fire stations drive to the fire and hose tiles within 3 tiles; a building saved in time loses only one level. Every fire runs out of steam after 60 tiles have caught or 3 minutes, and rain from a storm halves the spread. You cannot build on or bulldoze a burning tile ("That's on fire. Wait for the fire brigade to put it out"), but you can clear tiles next to it as a firebreak. A fire shakes the mood by 5% for 5 months. Prevention: fire stations near industry, and roads beside buildings so engines can park.

## Storms, heatwaves and cold snaps
A storm darkens the sky and rains for 14 to 26 seconds, with lightning every 3 to 7 seconds. Half the strikes aim at something that burns, and each such strike has a 15% chance to start a fire; a storm starts at most one fire, and about one storm in four starts one. Storms come at about 0.5% a month with at least 8 months between them.

A heatwave can arrive in June, July or August and a cold snap in December, January or February, each lasting 12 to 20 seconds of play (never more than 30 months). A heatwave multiplies power draw by 1.35 and water draw by 1.7; a cold snap multiplies power by 1.40 and water by 1.1. The map takes on an orange or blue tint. Keep spare power and water towers to ride them out.

## Random event pacing and settings
In Vibe City at most one random event starts in a month, and after one starts there are at least 12 months and 15 minutes of play before the next. The Random events slider in Settings (0% to 200%) scales how often fires, robberies, storms, weather, saucers and fairs happen; 0 turns them off. Turn on "Show event history" in Settings for a running list of everything that has happened, with how long each lasted.

A flying saucer sometimes crosses the sky over a city of 200 or more people. It does no harm, but the newspaper runs the sighting.

## The Disasters window
Disasters in Vibe City never happen on their own. Open the main menu and choose Disasters, then click one to unleash it on your city. There is no undo and no refund. If the game is paused it starts running. Only one of each kind can run at a time.

- Fire (3 of 5): fires break out in many places at once, about 5% of built lots, at least 6 and at most 28. This firestorm can burn three times longer and further than a normal fire.
- Flood (3 of 5): water rises off the shore over low ground for 11 seconds, stands for 5 and drains over 9. Tiles more than one step above the plain stay dry, and it covers at most 22% of the map. Flooded buildings are emptied and each civic building has a 40% chance to be lost. Needs water on the map. Mood drop 10% for 8 months.
- Tornado (2 of 5): two funnels, about 3 lots wide, aimed at built-up spots, tearing up buildings, trees, roads, rail and power lines for up to 34 seconds. Mood drop 12% for 8 months.
- Earthquake (5 of 5): 6 seconds of shaking that levels 60% of built lots, 30% of civic buildings and 7% of roads, rail and lines, then starts 3 fires. Mood drop 16% for 10 months.
- Nuclear Meltdown (5 of 5): needs a power plant. See the next section. Mood drop 30% for 18 months.
- Alien Invasion (4 of 5): 5 saucers from one of three crews fire death rays for 34 seconds; each hit destroys its target, may take the lots around it and sets fires. Mood drop 20% for 12 months.

Zoned lots are emptied, not unzoned, so rebuilding is quick.

## Nuclear meltdown and fallout
The meltdown picks one of your power plants. It glows red for 4 seconds ("evacuate the area!"), then explodes. Everything within 10 tiles is razed to bare ground, zoning included. Between 10 and 17 tiles out, buildings catch fire, almost certainly near the blast and about half at the edge, and what burns leaves scorched ground where nothing rebuilds for about 5 minutes of play.

The blast leaves a green fallout zone reaching 11 tiles. Nothing can be built and no land can be reshaped there ("Radioactive, nothing can be built here until the fallout fades"); only the bulldozer works. Lots inside lose a level with a 35% chance each month. The zone shrinks from its edge and its middle clears after 8 minutes of play. Fallout is kept in the save. The only prevention is not building power plants: solar and wind farms cannot melt down.

## Common questions
**Q: How do I reduce pollution?**
A: Keep industry and power plants away from homes, use solar or wind power, move freight to rail, and plant trees, which each clean up to 6 within 2 tiles.

**Q: Where does crime come from?**
A: Open casinos and clubs, and dense homes when the city is short of prison cells. Police stations cut 70% of it within 10 tiles.

**Q: Can I turn off random events?**
A: Yes. Set the Random events slider in Settings to 0. Disasters only happen when you choose them anyway.

**Q: How do I stop a fire spreading?**
A: Have fire stations with road access near the fire. You can bulldoze tiles next to a fire as a firebreak, but not the burning tiles.

**Q: How long does meltdown fallout last?**
A: It shrinks from the edge and the centre clears after 8 minutes of play. It is saved with the city, so reloading does not remove it.

**Q: Can a disaster happen by itself?**
A: No. Flood, tornado, earthquake, meltdown, invasion and firestorm only happen from the Disasters window. Ordinary fires, robberies and storms are the random ones.

**Q: Does the smoke from power plants do anything?**
A: The smoke itself is just the visible sign. The plant's pollution, 55 per plant spreading 4 tiles, is what lowers demand and mood.

**Q: What does a UFO do?**
A: A passing saucer is harmless and only makes the news. The Alien Invasion disaster is the one that attacks.
