# Minecraft: Building
Audience: Luna, playing Minecraft
Keywords: building, build, place block, house, hut, shelter, walls, roof, door, floor, coordinates, x y z, north, south, east, west, farm, wheat, crops, hoe, water, foundation, scaffold, pillar
Summary: How to build one block at a time with place-block: which way the coordinates run, why a block needs a neighbour, building from the bottom up, and plans for a small hut, a house, walls and a wheat farm.

## Coordinates and directions
- x runs east (bigger x) and west (smaller x).
- z runs south (bigger z) and north (smaller z). Easy to get backwards: north is negative z.
- y is height. Sea level is 63. The ground you stand on is at your y minus 1.
- get-position gives your x, y, z. Write the corners of a build down with game_note or pin them with remember_minecraft_spot before starting.

## How placing works
- Equip the block first: equip-item cobblestone, then place-block. place-block places whatever is in your hand.
- A block can only go next to a solid block that's already there (the ground, or a block you placed). It can't float in the air.
- You can't place a block where you are standing, or in the space just above you (your head). Stand beside the spot.
- Build from the bottom up: floor or first layer, then each wall layer, then the roof last.
- To reach higher than about 4 blocks, stand on something: place a block, move onto it, place the next. Remove it afterwards with dig-block.
- If place-block fails, check: is something already in that spot (get-block-info), is it next to a solid block, is the block in your hand, are you standing in it?

## A small hut (enough for the first night)
- 5 by 5 outside, 3 by 3 inside, walls 3 high: about 50 blocks of dirt, cobblestone or planks.
- Pick a flat spot. Mark the corners: from (x, z) to (x+4, z+4).
- Layer 1: the outline of the square on the ground (16 blocks). Leave one gap for the door.
- Layers 2 and 3: the same outline on top. Keep the gap 2 high for the door.
- Roof: fill the 5 by 5 on top at the 4th layer. Work inward from the walls so each block has a neighbour.
- Inside: a torch on a wall so nothing spawns, and a door (oak_door: 6 planks) in the gap, or close it with a block.

## A house
- Plan it first and write the plan with game_note: size, material, where the door faces.
- 7 by 7 or bigger with walls 4 high is roomy. Planks or cobblestone walls, a floor of planks.
- Windows: glass (smelt sand) or glass_pane. Leave the window spaces as gaps while building the walls.
- Put the crafting table, a furnace and a chest inside. Pin the house with remember_minecraft_spot.

## Walls around a base
- A wall 2 high keeps most mobs out; spiders climb, so 3 high with an overhang is better.
- Torches every 6 to 8 blocks along the inside keep the ground light so mobs can't spawn there.

## A wheat farm
- Wheat seeds drop when you break grass (dig-block on short_grass or tall_grass).
- Make a hoe (wooden_hoe: 2 planks, 2 sticks) and use it on dirt or grass beside water to make farmland.
- Water hydrates farmland up to 4 blocks away in every direction: a 9 by 9 square with water in the middle is the classic plot.
- Plant seeds on the farmland. Wheat is grown when it's yellow-brown; 3 wheat make bread.
- Light the farm with torches so crops grow at night and nothing spawns on it.

## Common questions
- Which way is north? Smaller z. If you're at z 100, z 90 is north of you.
- Why won't place-block work? Usually: the block isn't equipped, there's no solid block beside the spot, or you're standing in it.
- What should I build with first? Dirt or cobblestone: you'll have lots and they're quick. Planks look better once you have wood to spare.
- How do I get down from a pillar? Dig the block under you, one at a time.
