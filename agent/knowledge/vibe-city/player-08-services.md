# Vibe City: Civic Services - Police, Fire, Health, Education and Prison
Audience: player
Keywords: services, civic, police station, fire station, fire engine, fire crews, hospital, school, university, library, prison, coverage, radius, service bonus, growth bonus, upkeep, crime, classroom, school bus, patrol car, jail
Summary: Vibe City has seven civic buildings in the Civic group: police station, fire station, school, hospital, library, university and prison. Each needs both power and water to work, costs monthly upkeep, and gives a growth bonus to lots within its coverage radius. Police also fight crime and chase robbers, fire stations send engines to fires, and a prison is needed once the city passes 3,000 people.

## What civic buildings do in general
Every civic building in Vibe City works the same basic way. It only does its job while it has both power and water; with either missing it is closed, and the inspector's Status row says "In service", "Closed - no power", "Closed - no water" or "Closed - no power, no water". A closed building gives no coverage at all but still costs its upkeep.

A working police station, fire station, school, hospital, library or university gives a service bonus to every lot inside its coverage, which is a square reaching the radius in tiles in every direction. A lot with the service bonus grows 30% faster and is 30% less likely to shrink when demand falls. Being covered by two services does not count twice; coverage is coverage.

Service coverage also feeds the city mood: the "services" share (12% of the mood) is the fraction of built lots inside any service coverage. The advisor's gripe for it is "Too few police, fire, schools and hospitals". Double-click a zoned lot with Pan and Inspect and its Service bonus row says Yes or No.

## Costs, reach and upkeep
The civic buildings in Vibe City, with build price, coverage radius and monthly upkeep:

- Police Station: $1,500, 10 tiles, $40 a month. Draws 8 MW and 6 water.
- Fire Station: $1,500, 10 tiles, $40 a month. Draws 8 MW and 14 water.
- School: $1,200, 10 tiles, $30 a month. Draws 10 MW and 14 water.
- Hospital: $2,000, 10 tiles, $45 a month. Draws 16 MW and 30 water.
- Library: $900, 7 tiles, $20 a month. Draws 6 MW and 8 water.
- University: $4,000, 16 tiles, $90 a month. Draws 30 MW and 45 water.
- Prison: $8,000 for a 3x3 lot, $60 a month. Draws 3 MW and 4 water. It gives no service bonus; its job is holding prisoners.

All one-tile civic buildings go on bare grass. Prices are 1.6 times higher on hill ground. Upkeep shows in the City Stats budget as Civic upkeep.

## Police station
The Police Station in Vibe City does three jobs. It gives the service growth bonus within 10 tiles. It cuts crime: on every tile within its 10-tile reach, 70% of the crime that lands there is removed. And it chases robbers.

Each police station keeps 2 patrol cars on the road (blue cruisers), up to about 10% of all traffic. When a robbery happens, every patrol car that can reach the getaway car by road turns after it, and the nearest working station sends one more. Police cars drive a little faster than the getaway car. If one catches it within 75 seconds the stolen $1,000 is returned; otherwise the robbers get away. With no police at all the robbers simply drive off.

Crime in Vibe City comes from open casinos and clubs, and from dense housing when the city is short of prison cells. The Crime map view (press V to cycle views) and the inspector's Crime row ("patrolled" when covered) show where police are needed. The newspaper runs "Crime Wave Sweeps City" when a city over 300 people has no police station.

## Fire station and fire crews
The Fire Station gives the service growth bonus within 10 tiles and sends fire engines. Each station keeps 1 engine on the road (red, with a ladder), up to about 5% of traffic.

When a fire starts, every engine already out on patrol that can reach it by road is turned round and sent, and the nearest working fire station sends one of its own. Engines drive faster than traffic, and cars pull over to let them pass. An engine parks at the kerb beside a burning tile and its hoses reach 3 tiles from where it stands, putting out one tile about every 0.6 seconds. Fire does not spread from tiles under or near a hose.

If more than 4 tiles are burning for each engine on scene, a further alarm calls another engine from the next working station along, every 6 seconds. A building put out in time loses one level; one that burns down (after 9 seconds alight) is emptied to a bare zoned lot. If no engine can reach the fire you see "no fire engine can reach it", and it burns until it runs out of steam. Dispatch works by road from any working station, not only inside the 10-tile coverage, but a nearby station arrives sooner, and a tile burns down 9 seconds after it catches.

## School, library and university
In Vibe City the school, library and university form one ladder of the same service: each gives the service growth bonus over its radius.

- The Library ($900, 7 tiles) is the cheap small one, for a neighbourhood a school does not quite reach.
- The School ($1,200, 10 tiles) is the standard. Each school runs 2 yellow school buses on the roads, up to about 10% of traffic.
- The University ($4,000, 16 tiles, $90 a month) covers a much wider area for more money.

Click a school or university with Pan and Inspect to open the classroom: the teacher and a chalkboard with two games, Chalkboard Maths and Word Scramble, one minute a round. A school sets the easy version and the university the hard one. The first round each month is graded in public and affects the city mood: an A lifts it by 6% for 6 months, a B by 3% for 4 months, a C does nothing, a D costs 3% for 4 months and an F costs 6% for 6 months. Later rounds that month are practice. The paper runs "Parents Demand A School" when a city over 500 people has none.

## Hospital
The Hospital in Vibe City costs $2,000 and $45 a month and gives the service growth bonus within 10 tiles. It is the thirstiest of the basic civic buildings, drawing 16 MW and 30 water, and like all of them it closes without power or water ("A dark hospital treats nobody"). There is no separate health statistic; its value is the growth bonus and its share of the services part of the mood. The newspaper runs "Sick Turned Away, No Hospital" when a city over 800 people has no hospital.

## Prison
The Prison is a 3x3 building costing $8,000 and $60 a month. It gives 30 jobs (counted as commercial) while open.

Once your city passes 3,000 people the police need somewhere to put the people they arrest. The need ramps in over the next 1,500 people, so it is fully felt at 4,500. Each prison has 40 cells, with one inmate per 250 people, so one working prison serves a city of 10,000; the biggest cities need a second.

If the city is short of cells, two things happen: every home at level 3 or higher starts producing crime, scaled by how short you are, and police lose up to half of their crime-cutting strength because the people they pick up are back out. The advisor warns "The police will need a prison soon" from 2,500 people.

The downside: nobody wants to live beside a prison. Homes within 4 tiles of its walls lose up to 0.3 of their demand, even if the prison is closed. The inspector shows its cells in use, for example "12 of 40 cells in use".

## What happens without services
A city with no civic buildings still grows, but more slowly: no lot gets the 30% growth bonus, lots shrink faster when demand dips, and the services share of the mood falls to zero. Without a police station clubs make crime freely and robberies go unchased. Without a fire station fires burn until they exhaust themselves (up to 60 tiles or 3 minutes). Past 3,000 people, without a prison, crime rises in dense neighbourhoods and the police weaken. The newspaper and the Demand panel point out missing services, so check them when growth stalls.

## Common questions
**Q: Why does my police station say Closed?**
A: Civic buildings need both power and water. Check the Status row in the inspector: it says whether power, water or both are missing.

**Q: How far does a fire station reach?**
A: Its service bonus covers 10 tiles in every direction. Engines are sent by road from the nearest working station to any fire they can reach, but a closer station gets there before the fire spreads.

**Q: What is the difference between a school, a library and a university?**
A: They give the same growth bonus over different radii: library 7 tiles for $900, school 10 tiles for $1,200, university 16 tiles for $4,000.

**Q: Does being covered by two services help more?**
A: No. A lot either has the service bonus or not; overlapping coverage does not stack.

**Q: When do I need a prison?**
A: From 3,000 people. One prison covers 10,000 people. Without one, dense homes produce crime and the police lose up to half their effect.

**Q: Why are homes near my prison not growing?**
A: Homes within 4 tiles of a prison lose up to 0.3 of their demand. Keep prisons away from housing.

**Q: How do police stop robberies?**
A: Patrol cars and a car from the nearest working station chase the getaway car. If they catch it within 75 seconds, the $1,000 is returned.

**Q: Can school lessons change the city mood?**
A: Yes. The first classroom round each month is graded: an A or B lifts the mood for a few months, a D or F lowers it.

**Q: Does a hospital do anything besides the growth bonus?**
A: No. It gives the service growth bonus within 10 tiles and counts toward the services part of the city mood.
