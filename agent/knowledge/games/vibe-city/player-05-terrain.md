# Vibe City: Terrain, Water and Trees
Audience: player
Keywords: terrain, land, terraform, raise land, lower land, level land, flatten, water tool, lake, river, fill water, trees, forest, plant trees, hills, slopes, terraces, height, elevation, shore, waterline, world generation, hill cost, building on hills
Summary: How the ground works in Vibe City: the five Land tools (Raise, Lower, Level, Water and Tree), what each costs and the rules for using them. It also explains how maps are generated, how height and water affect building costs and placement, and what can be built on hills and shores.

## How the ground is shaped
The ground in Vibe City is built in flat terraces rather than smooth slopes. Every tile sits at one of five heights: under water, the plain (height 0), or one of three hill steps (heights 1, 2 and 3). Between tiles of different heights the game draws a wall or bank, and where water steps down from one level to another it draws a waterfall. Because every tile is flat on top, any one-tile building can stand on any dry height.

The tile inspector (double click a tile with the Pan tool) shows a tile's Elevation as a number from 0 to 1. Below 0.33 is below the waterline. Above 0.62 is hill ground, which costs more to build on. While holding Raise, Lower or Level, the cursor badge shows the height directly, such as "Height 2 of 3" or "Under water".

## Raise Land and Lower Land
Raise Land and Lower Land in Vibe City are in the Land drawer of the toolbar. Each moves a tile one step up or down for $25 a step. Moving earth across the waterline costs four times as much, $100: raising a lake bed up to dry ground is landfill, and lowering dry ground below the waterline digs a hole that fills with water.

Both tools only work on bare ground: grass, trees or water. They do nothing to roads, rail, zoned lots (even empty ones) or buildings. Trees on a tile you raise or lower are removed.

One stroke (pressing the button, dragging, and letting go) moves each tile at most one step, and never more than one step away from the height of the tile where the stroke began. So dragging Raise from a tile at height 1 lifts everything you cross that is below height 2 up a step, and nothing goes above 2. This evens ground out rather than piling it into spikes. To go higher or deeper, let go and stroke again. Heights run from under water up to 3; you cannot raise past 3.

## Level Land
Level Land in Vibe City flattens ground to the height of the first tile you click. Press on a tile and drag across others: every bare tile you cross is moved to that height, however many steps it takes, at $30 per step. Moving across the waterline costs four times as much. Level is the quickest way to make a flat platform for a big building, which needs every tile of its square at one height. Like Raise and Lower, it only works on grass, trees and water.

## The Water tool
The Water tool in Vibe City paints water onto bare ground for $100 per tile. Drag it across the map to make a lake or a river. It floods the tile at whatever height it already stands, so water painted on a hilltop makes a raised lake, and where it meets lower water a waterfall is drawn. The flat price does not change with height. It only works on grass and trees, not on roads, zones or buildings, and does nothing on tiles that are already water.

To remove water, use Bulldoze on it. Bulldozing a water tile fills the ground back in for $100. If the tile was below the waterline, the ground comes up to plain height (height 0).

Water painted with this tool is real water: pumps can draw from it, a seaport needs water along one side, and roads or rail across it become bridges.

## Trees
The Tree tool in Vibe City plants a tree for $20 on grass (more on hill ground). Each new tree picks one of several looks at random. Trees have no upkeep. A tree does two jobs:

- It cleans the air. Each tree takes pollution off its own tile, with the effect falling to nothing 2 tiles away. A belt of trees between a factory row and housing can turn a heavily polluted street into a lightly polluted one. City Stats shows how much pollution trees clean each month.
- It gives a small growth boost to zoned lots within 4 tiles, like a park.

Trees are also cleared for you. When you build a road, rail, zone or building on a tile with trees, the trees come down for free. If the build is refused (not enough money, wrong ground), the trees are put back. Water pipes and tunnels pass under trees without felling them. Bulldozing a tree costs $5. Trees can burn: a fire spreads into trees and parks less readily than through houses, so a forest does not usually burn edge to edge.

## World generation
World generation in Vibe City happens in the New City window. Every map is 128 by 128 tiles. The options shape the land:

- Terrain: Flat has few, low hills; Rolling has gentle hills; Hilly has more and higher hills; Mountains has the most and steepest high ground.
- Water: Dry keeps all land above the waterline, so there are no lakes. Ponds gives a few small ponds, Lakes scatters lakes across the map, and Islands lowers most of the land so it breaks up into islands.
- Trees: None, Sparse (about 1 dry tile in 90 has a tree), Wooded (groves, about four times as many trees) and Forest (thick forest, about nine times as many). Trees are about 30% more likely on hill ground.
- River: On carves a river a couple of tiles wide that runs from one edge of the map to the opposite edge, wandering as it goes. A river can be carved even on a Dry map.

The preview shows the share of water and hills and the number of trees. A seed always produces the same map with the same options.

## Building on hills
Hill ground in Vibe City (elevation above 0.62) costs 1.6 times the normal price for most things built on it: zones ($80 instead of $50 a tile), roads ($16 instead of $10), rail ($24 instead of $15), power lines, water pipes, parks, trees and buildings. Some tiles at the foot of a hill sit at plain height but still count as hill ground; the inspector's Elevation number tells you. Tunnels ($40), rail depots, water pumps and water towers cost the same anywhere.

Hills have advantages too. A Wind Farm makes 100 MW on the plain and 25% more for every hill step it stands on: 125 MW on height 1, 150 MW on height 2 and 175 MW on height 3. During a flood disaster, water spreads over the plain and the first hill step, but tiles two or more steps up stay dry. Tunnels can be bored straight through hillsides to carry roads and rail.

Roads and rail can climb from terrace to terrace. A rail depot, however, must be at the same height as the track beside it.

## Big buildings and level ground
Big buildings in Vibe City need a clear, level square. The Power Plant and Seaport take a 2 by 2 square and the Track and Prison a 3 by 3 square. Every tile of the square must be grass or trees, none of it under water, none of it over a tunnel, and all of it at the same height. If not, the cursor turns red and you see a message such as "The ground under it has to be level", "Part of that square is under water" or "There isn't room for it here". Use Level Land to prepare a site on uneven ground.

## Building on shores and water
Shores in Vibe City matter for several buildings:

- Water Pump: must go on the shore, with open water on at least one of its four sides ("Pumps go on the shore, beside open water"). It also needs power.
- Seaport: a 2 by 2 lot on level ground with water along at least one side.
- Roads and rail on water become bridges at six times the price, and power lines cross water on piers at six times the price. Water pipes can run under water at six times the price.

Zones and ordinary buildings cannot be placed on water. To build there, fill the water in first with Bulldoze or Raise Land.

## Common questions
**Q: How do I make a lake in Vibe City?**
A: Use the Water tool from the Land drawer and drag across bare ground. It costs $100 per tile, at any height.

**Q: How do I get rid of water?**
A: Bulldoze the water tile for $100, or raise it with Raise Land, which also costs $100 to cross the waterline.

**Q: Why can I not raise the land any higher?**
A: Heights stop at 3. Also, one stroke only moves ground one step from where the stroke started; let go and drag again to go higher.

**Q: Why does Raise Land do nothing on my zoned lot?**
A: The land tools only work on bare ground: grass, trees or water. Bulldoze the zone, road or building first.

**Q: How do I flatten ground for a power plant?**
A: Pick Level Land, press on a tile at the height you want, and drag across the site. Each step moved costs $30.

**Q: Why is building more expensive here?**
A: The tile is hill ground (elevation above 0.62), where most building costs 1.6 times as much.

**Q: Do trees cost upkeep?**
A: No. A tree costs $20 to plant (more on hills) and nothing after that.

**Q: How far do trees clean the air?**
A: Each tree cleans pollution on its own tile, fading to nothing 2 tiles away. Its growth boost reaches 4 tiles.

**Q: Where can I put a water pump?**
A: On bare ground beside open water, on any of its four sides. Water you painted with the Water tool counts.

**Q: Will the river always be there?**
A: Only if River is set to On in the New City window. It runs from one edge of the map to the opposite edge.
