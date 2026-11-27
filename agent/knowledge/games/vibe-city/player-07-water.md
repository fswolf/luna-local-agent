# Vibe City: Water Pipes, Pumps, Towers and Drought
Audience: player
Keywords: water, water supply, pipe, water main, mains, pump, water pump, water tower, reservoir, storage, drought, dry, well, plumbing, Utilities view, water view, shore, upkeep, heatwave, no water
Summary: In Vibe City water comes only from water pumps on the shore, which need power. Buried pipes carry it to buildings within one tile, and water towers store spare water as a reservoir. Lots without water can still be built but never grow past level 1, and civic buildings close without it.

## How water works
The water system in Vibe City has three parts, and each is useless without the others:

- The Water Pump lifts water out of a lake, river or sea. It is the city's only source.
- The Water Pipe (also called a water main) carries the water. It is buried, so it runs under anything.
- The Water Tower stores what the pumps make and nobody drinks, so the city has a reserve when the pumps fall short.

Water reaches a building when a live pipe runs under it or within 1 tile of it, including diagonals. A pipe down a street therefore waters the lots on both sides. Pumps and towers count as part of the pipe network, so a pump built against a pipe, or with a pipe under it, is connected without any extra fitting. A building bigger than one tile, such as the Track or the prison, is watered whole if a main reaches any one of its tiles.

All three are in the Utilities group of the build menu.

## The water pump
The Water Pump costs $800 and $35 a month in upkeep, the most expensive running cost per building in the water system. It pumps 1,200 water a month.

A pump has two requirements:

1. It must stand on bare ground on the shore, with open water on at least one of its four sides. If you try to build it inland the game says "Pumps go on the shore, beside open water".
2. It needs power. A pump is a motor and draws 20 MW from the grid. If you build one with no power the game warns "Pump built - it needs power before it will run".

Every pump turns its intake grate toward its own water, so the side with the big pipe and grating always faces the lake or river it draws from, whichever way you rotate the camera. There are four pumphouse designs, picked at random when you build one: a blue pumphouse, an open bank of green upright pumps, a red brick pumphouse with a tank, and a blue pumphouse with solar panels on the roof.

The pump is checked every month, not just when built. If you fill in the water it was drawing from with the land tools, it stops and reads "Stranded - the water it drew from is gone". If the power goes, it reads "No power - a pump is a motor" and the whole pipe run it fed goes dry. Water in Vibe City therefore always depends on your power grid.

## Water pipes
The Water Pipe costs $12 per tile, $72 per tile under water (six times), and 1.6 times the price on hills. Upkeep is $1 per tile per month. Drag to lay a run.

Because pipes are buried, they go under grass, roads, rail, houses, factories and hills alike, so you can plumb a district that is already built without knocking anything down. The only thing a pipe cannot share a tile with is a tunnel bore. Pipes are not affected by fire or surface wrecking, and bulldozing a building on top of a pipe leaves the pipe in place.

Selecting the Water Pipe tool switches the map to the Utilities view automatically, and choosing another tool takes you back to the view you were in. To remove a pipe, use Bulldoze while in the Utilities view ($5 a tile). In that view the bulldozer takes the pipe and leaves the street above it alone.

## Water towers and the reservoir
The Water Tower costs $250 and $6 a month. It stores up to 2,400 water. It can go on any bare grass tile; it has no siting rule beyond that, but it must be on a live main to fill. A tower not on a live main reads "Empty - not on a live main" and adds nothing.

Towers do not add supply. Each month, any water the pumps make beyond what the city draws goes into storage, up to the total capacity of your connected towers. When the city draws more than the pumps make, the shortfall comes out of storage instead. Towers buy you months to build the next pump while the reservoir drains.

Water towers need no power. The City Stats panel's Reservoir row shows stored over capacity, or "No towers", or "Towers not on a live main".

## Drought and running dry
A drought in Vibe City is what happens when the city draws more water than the pumps make and the reservoir is empty. During a drought every building on the mains is treated as dry, even though its pipes are connected. The inspector says "On the mains, but the city is short" and towers read "Drained - the city is drawing more than it makes".

Before that, a draining reservoir already worries people. With 6 or fewer months of water left at the current rate, the water share of the city mood is cut, by up to 60% in the last month, and the advisor says "The reservoir runs dry in about N months". Water is 20% of the mood score.

A heatwave (June to August) multiplies the city's water draw by 1.7 and a cold snap (December to February) by 1.1, so a reservoir you never needed can start emptying in summer. Keep a supply margin and some towers for these spells.

## How much water buildings use
Only buildings actually on the mains draw water. Zoned lots draw per building level:

- Residential: 4 per level. Commercial: 5 per level. Industrial: 8 per level.

Civic and other buildings draw a flat amount: Police 6, Fire Station 14, School 14, Hospital 30, University 45, Library 8, Prison 4, Rail Depot 4, Seaport 3, Casino 10, Club 10, Arcade 8, Track 3.

One pump at 1,200 covers roughly a third of a mid-sized city. A building on a well, with no main in reach, draws nothing from the city supply, so plumbing a district raises the draw. Weather changes the total: heatwaves and cold snaps multiply the draw. Double-click a building to see its own draw in the Draws row.

## What happens without water
Water is a ceiling on growth, not an on/off switch. A zoned lot with no main in reach still gets built and lived in, on a well, but it can never grow past level 1. A building already above level 1 when its water is lost (no main, or a drought) loses a level with a 10% chance each month while it has power. Plumbing is what turns a town into a city.

Civic buildings are different: police, fire, schools, hospitals, libraries, universities, the prison and the nightlife buildings close without water ("Closed - no water"), so their coverage and service stop entirely.

The Demand panel's needs list reports "N lots held small with no water" when this is holding your city back.

## The Utilities view for water
Press V to cycle views until you reach Utilities, or pick the Water Pipe tool. The Utilities view draws the ground as a wireframe and shows what is buried and strung:

- Live pipes are bright blue. Dry pipes, not connected to a working pump, are a dull blue-grey.
- Pumps are marked as diamonds, red when a pump is built but not pumping. Towers are rings.
- Tiles that want water and have no main in reach are outlined in bright magenta. Tiles that want water and already have it are a muted shade of the same colour. The view is a list of what is left to plumb and goes quiet as you finish.
- The power grid is drawn in amber underneath, so you can see when a red pump is red because no power reaches it.

A zoned lot is only marked as wanting water from level 1 up. Civic buildings always want it.

## Reading water in the panels
The City Stats panel's Water section shows Supply (from working pumps), Draw, Balance, Reservoir, "Pumps working N of M", Mains (pipe tiles) and "Lots on the mains". Water upkeep (pumps $35, towers $6, pipes $1 a tile) has its own line in the budget.

Double-click a tile with Pan and Inspect for its details. A building shows a Water row ("On the mains", "No main in reach" or "On the mains, but the city is short") and a Draws row. A pump shows Source, Mains and Supplies. A tower shows Mains and Stores. Any tile with a pipe under it shows a Water main row: "Carrying" or "Dry - no working pump on this run".

## Common questions
**Q: Why will my water pump not build?**
A: It has to go on bare ground right on the shore, with open water on one of its four sides.

**Q: My pump is built but nothing has water. Why?**
A: The pump needs power. Connect it to the grid with a power line or a powered building beside it. Then make sure pipes run from it to your buildings.

**Q: Do I need pipes if I have a water tower?**
A: Yes. A tower only stores water from a live main. It adds no supply and must be on the pipe network with a working pump.

**Q: How far does a pipe reach?**
A: One tile. A pipe waters its own tile and the eight tiles around it, so one pipe down a street serves both sides.

**Q: Can I lay pipes under existing buildings?**
A: Yes. Pipes are buried and go under roads, rail, houses and factories without disturbing them. Only a tunnel bore blocks a pipe.

**Q: What is a drought?**
A: The city draws more water than the pumps make and the towers are empty. Every building is treated as dry until you add pumps or the demand falls.

**Q: What happens to houses without water?**
A: They can be built but stay at level 1. Buildings above level 1 that lose water slowly lose levels.

**Q: How do I remove a pipe?**
A: Switch to the Utilities view and use Bulldoze on it, $5 a tile. In the normal city view the bulldozer leaves pipes alone.

**Q: How much water does a pump make?**
A: 1,200 a month, for $800 to build and $35 a month to run, plus 20 MW of power.
