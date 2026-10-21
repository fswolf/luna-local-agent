# Minecraft: Mining and ores
Audience: Luna, playing Minecraft
Keywords: mining, mine, ore, ores, coal, iron, copper, gold, diamond, redstone, lapis, emerald, deepslate, y level, depth, height, pickaxe tier, which pickaxe, raw iron, caves, strip mining, bedrock
Summary: Which pickaxe mines which ore, how deep to go for each one in Minecraft 1.18 and newer, the deepslate versions of ore names, and safe ways to dig. Height is the y coordinate: sea level is y 63, deepslate starts around y 0 and bedrock is at y -64.

## Which pickaxe mines what
Mined with too weak a pickaxe (or none), a block drops nothing.
- Any pickaxe (wooden and up): stone, cobblestone, coal ore.
- Stone pickaxe and up: iron ore, copper ore, lapis ore.
- Iron pickaxe and up: gold ore, redstone ore, diamond ore, emerald ore.
- Diamond pickaxe: obsidian.
- No tool needed: logs, dirt, sand, gravel, leaves (shovels and axes are just faster).

## Where each ore is
The y coordinate where each is most common:
- Coal: everywhere above about y 0, most around y 96. Easy to see in cliffs and caves.
- Copper: around y 48.
- Iron: around y 16, and also high up in mountains.
- Lapis: around y 0.
- Gold: around y -16.
- Redstone: deep, near the bottom.
- Diamond: deepest, best around y -58. Rare: dig long tunnels.
- Emerald: only inside mountains.

## Ore names
- Above y 0 the stone is stone and the ores are coal_ore, iron_ore, copper_ore, gold_ore, lapis_ore, redstone_ore, diamond_ore, emerald_ore.
- Below about y 0 the stone is deepslate and the ores have deepslate in front: deepslate_iron_ore, deepslate_diamond_ore and so on. Search for both names with find-blocks when you're near y 0.
- Mined ores drop raw items: raw_iron, raw_gold, raw_copper (smelt them into ingots), coal, diamond, redstone, lapis_lazuli, emerald.

## Digging safely
- Never dig straight down under yourself: you can fall into a cave, lava or water. Dig a staircase: down one block, forward one block.
- Lava below y 0 is common. If you see it, go around it.
- Put torches every few blocks in tunnels, so mobs don't spawn and you can find your way back.
- Pin the way back to your base with remember_minecraft_spot before going deep.
- Gravel and sand fall when the block under them goes.

## Common questions
- Where do I find iron? Around y 16 in stone, in caves, or in mountains. Mine it with a stone pickaxe or better, then smelt the raw_iron.
- Why didn't the ore drop anything? Your pickaxe is too weak for it (see the list above), or you weren't holding one.
- find-blocks found nothing. It only looks 16 blocks around by default; raise maxDistance, or move somewhere else (a cave, a cliff, deeper down) and search again.
