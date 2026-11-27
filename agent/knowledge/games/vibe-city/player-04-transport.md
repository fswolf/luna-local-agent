# Vibe City: Transport
Audience: player
Keywords: transport, roads, streets, highway, bridge, rail, railway, trains, rail depot, station, tickets, train ride, tunnel, bore, crossover, level crossing, traffic, cars, vehicles, freight, neighbours, connections, seaport, upkeep, road access
Summary: How to build and use roads, bridges, railways, rail depots, tunnels and level crossings in Vibe City, what trains do and how to buy a ticket to ride one. It also explains the traffic on the roads, connections to neighbouring towns, and how transport affects growth, pollution and the budget.

## Roads
Roads in Vibe City are the backbone of the city: a zoned lot only grows if a road touches one of its four sides. The Road tool in the Transport drawer costs $10 per tile, $16 on hill ground and $60 over water as a bridge, plus $1 per tile per month in upkeep. Drag to lay a straight run; release and drag again from the corner to turn.

A road can go over grass, an empty zoned lot, water or a power line (the line carries on overhead), and trees in the way are cleared free. It will not go over a built lot: "Bulldoze the building first. A road will not go over it". Bulldozing road costs $5 per tile.

The inspector names a road's class as Street, Avenue, Highway or Bridge, but the Road tool in version 1.0.0 lays streets only. Where avenues or highways exist, they cost $2 or $4 a tile per month and pollute more.

## Bridges
Bridges in Vibe City are simply roads or railways laid across water, at six times the normal price: $60 a tile for road and $90 for rail (power lines cost $48 and pipes under water $72). They are drawn as concrete decks on piers with steel railings, and spans run down off hills to the water. A bridge works exactly like the road or track it belongs to, including giving road access to lots beside it. Bulldozing a bridge leaves the water behind.

## Rail and level crossings
Rail in Vibe City carries trains and freight. The Rail tool costs $15 per tile, $24 on hill ground and $90 over water, with $2 per tile per month in upkeep. Track goes over grass, water or a power line, in straight drags like roads. Track alone does nothing: a line works only with at least two working rail depots on it.

A level crossing is made by laying rail across a road or a road across rail. The existing route must run straight through the tile and the new one must cross it at right angles; otherwise you see "A crossing goes where the road cuts across the line". Gates close when a train is 2.5 tiles away, and traffic crosses at 45% of normal speed. A tunnel avoids the wait.

## Rail depots and stations
A Rail Depot in Vibe City costs $500 and $25 a month. It must go on bare ground beside track, at the same height as the track; otherwise you see "Depots go beside track, on level ground". A depot needs power and water like a civic building: it draws 6 MW and 4 water.

A depot is in service only when it touches level track, has power and water, and another working depot is on the same line. The inspector shows "In service", "Not connected - needs level track alongside", "No power - needs a line beside it", "No water - needs a main", or "Idle - the line needs a second depot in service".

A working depot serves everything within 6 tiles. Industry there gets freight, +0.25 to its demand, and the more of the city's zoned lots are in range, the fewer cars are on the roads, up to 40% fewer. Each depot gets a station name such as Kitty Junction or Vibe Central.

## Trains
Trains in Vibe City run automatically on every working line, about one train a year per line, and never two on one line at once. A service starts at one end of the line and calls at every working depot in turn, standing 2.5 seconds at each, at 3.2 tiles per second, much faster than cars.

Half the trains are passenger trains (a locomotive and three coaches) and half are freight (a locomotive and four wagons). The two furthest depots on a line must be at least 4 tiles apart along the track, counting the depots themselves, for a train to be sent.

## Buying a ticket and riding a train
The ticket office in Vibe City opens when you click a rail depot with the Pan tool. The window is titled with the station's name, and the Departures board lists every other working station on the same line, nearest first, with the distance and the fare. A fare is $40 per tile of track, with a minimum of $200, and it comes out of the city treasury. A station without power or water sells nothing, and the buy buttons are disabled if you cannot afford the fare or a ride is already under way.

Buy a ticket and the camera zooms to 3.5x and follows the train to your destination, even while the game is paused. A ride bar shows the destination and tiles left; press Get off or Escape to leave early. On arrival you see "Now arriving at" the station, and the zoom goes back. With "Cab view on train rides" on in Settings (the default), a Cab view button opens a window looking out of the front of the locomotive.

## Tunnels
Tunnels in Vibe City are bores that run under the ground and leave the surface alone. The Tunnel tool costs $40 per tile, the same on hills, laid in straight drags. A bore can go under open ground, trees, water, a road or a railway, but not under a building, a level crossing or a water main. It needs something to pass beneath: a hillside, a lake, or a street or railway. On flat open ground it is refused, and on the flat it may only cross under a street or line whose road or rail already reaches both sides.

A tunnel carries traffic once both of its ends meet the same kind of route: road at two mouths carries cars, rail at two mouths carries trains. The inspector shows "Carrying road traffic", "Carrying rail", "Road and rail" or "Unconnected - needs a road or rail at both mouths". In the Utilities view bores are drawn blue for road, purple for rail, teal for both and grey when unconnected.

## Crossovers and removing tunnels
A crossover in Vibe City is where two streets or two railways cross in an X and one runs underneath the other. Use the Tunnel tool on the crossing tile to make one for $40; click it again with the Tunnel tool to swap which line goes under, for free. Traffic goes straight across a crossover and cannot turn there.

To remove a tunnel, Bulldoze it in the Utilities view for $5; the road or railway above is untouched. Bulldozing a road or track over a bore on flat ground in City view also fills the bore in, while a bore under a hill or lake survives.

## Traffic and vehicles
Traffic in Vibe City is the cars, buses and service vehicles on the streets. There is about one vehicle per 220 residents plus jobs, at most about one per 8 road tiles and 40 in all. The Traffic slider in Settings scales this from 0% to 200%, and rail depots cut it by up to 40%.

Vehicles keep right, slow for corners, queue, and wait at junctions and closed crossings. Service vehicles keep their colours at any zoom: blue police cars (two per police station), red fire engines (one per fire station) and yellow school buses (two per school or university). Traffic pulls over for a vehicle on a call. A black car is a robber's getaway car.

The cars themselves do not change growth or demand. Road pollution comes from the size of the city (residents plus jobs), not the number of cars, so an empty grid laid ahead of the city stays clean until people move in.

## Neighbours, the map edge and the seaport
Connections in Vibe City link your city to the four towns off the edges of the map. When a road or railway reaches the map edge, a sign offers to open a connection: $1,000 for road, $1,500 for rail ("Open it" or "Not now"). A road link lifts commercial and residential demand, a rail link lifts industry, and a link only counts while it still joins your city. Some cars drive off the map through open road links and some arrive from outside.

The Seaport, also in the Transport drawer, costs $6,000 for a 2 by 2 lot on the shore and $40 a month. With power, water and a way out to open sea, ships call, it adds 20 jobs and lifts industry. A coastal city of 2,500 people or more needs one.

## Common questions
**Q: How much does a road cost in Vibe City?**
A: $10 per tile on low ground, $16 on hills and $60 over water as a bridge, plus $1 per tile per month in upkeep.

**Q: Why are no trains running?**
A: A line needs at least two rail depots that are each beside level track, powered and watered. Check each depot's status in the inspector.

**Q: How much does a train ticket cost?**
A: $40 per tile of track to the destination, with a minimum of $200, paid from the city treasury.

**Q: How do I make a tunnel through a hill?**
A: Drag the Tunnel tool through the hillside from road to road (or rail to rail) so both ends meet the route. It costs $40 per tile.

**Q: Why can I not dig a tunnel here?**
A: Bores need something to go under: a hill, a lake, or a street or railway. They cannot go under buildings, level crossings or water mains, and on flat ground they can only cross under an existing street or line.

**Q: Does traffic slow my city's growth?**
A: No. The vehicles are a picture of the city's activity. They do not change demand or growth.

**Q: What does a rail depot do for my city?**
A: It gives industry within 6 tiles freight, raising its demand, and takes cars off the roads, up to 40% fewer if the whole city is in range of working depots.

**Q: Is Maze Courier a transport feature?**
A: No. Maze Courier is an arcade game inside the Arcade building, not part of the city's transport.
