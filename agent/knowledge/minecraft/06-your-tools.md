# Minecraft: Your tools
Audience: Luna, playing Minecraft
Keywords: tools, find-blocks, dig-block, place-block, craft-item, can-craft, get-recipe, smelt-item, equip-item, move-to-position, look-at, find-entity, get-position, list-inventory, get-block-info, detect-gamemode, send-chat, read-chat, error, failed, No suitable reference block, already a block, not found, timed out
Summary: How each of your Minecraft tools behaves in practice, what it needs before it works, and what its messages mean. The two that trip you up most: dig-block and place-block both use whatever is in your hand, so equip the right thing first.

## Looking around
- get-position: your x, y, z. Check it at the start of a step.
- find-blocks: needs the exact block name (oak_log, not "wood"; iron_ore and deepslate_iron_ore are different). It looks 16 blocks away unless you give maxDistance, and count asks for several at once. "No X found within 16 blocks" means try a bigger maxDistance, a different name, or go somewhere else.
- find-entity: finds a mob or player nearby (16 blocks by default). Good for checking for danger, or finding cows and sheep.
- get-block-info: what block is at a spot. Use it before digging or placing when a tool says something unexpected.
- list-inventory: everything you're carrying, with counts.
- detect-gamemode: survival or creative.

## Moving
- move-to-position: walks there with pathfinding and stops within about a block. It can take a while; "Move timed out" means the way is blocked or too far. Try somewhere closer, or dig through.
- look-at: turns to face a spot. Handy before digging, and for not looking at endermen.

## Digging
- dig-block: walks to within reach and breaks the block. It does NOT pick a tool: equip the pickaxe for stone and ores, the axe for wood (faster), the shovel for dirt and sand. Stone or ore dug with the wrong tool (or bare hands) drops nothing.
- Dropped items are picked up when you're close. If something didn't land in your inventory, walk to where the block was.
- "No block found" means that spot is air: check the coordinates.

## Placing
- place-block: places what's in your hand. Equip the block first.
- It needs a solid block next to the spot. "No suitable reference block found" means nothing is touching that spot: place a block beside or under it first.
- "You can't place a block where you're standing or one block above": step aside and try again.
- "There's already a block (name) at ...": dig that one first, or pick the spot next to it.

## Crafting
- craft-item: exact output names (oak_planks, crafting_table, stone_pickaxe). Small recipes work anywhere; anything that needs a 3 by 3 grid needs a crafting_table placed within 16 blocks, which it uses on its own.
- A failed craft says what's missing. Read it and get that, rather than trying again.
- can-craft: tells you whether you have everything, and what's missing if not.
- get-recipe: what an item needs, before you go gathering.

## Smelting
- smelt-item: needs a furnace block placed in the world and its x, y, z, the item to smelt, and a fuel. It waits up to a minute for the result.
- "No furnace block found" means wrong coordinates or no furnace there: place one (8 cobblestone at the table) and pin it with remember_minecraft_spot.
- "Furnace input slot is occupied" or "fuel slot is occupied": something is already in it. Use another furnace, or wait for it to finish.
- "No output after..." means it didn't finish in time; smelt fewer at once.

## Equipping
- equip-item: matches part of the name, so "pickaxe" equips whatever pickaxe you have. It goes in your hand unless you say otherwise. Armour goes on with destination head, torso, legs or feet.

## Chat
- read-chat: what players said. Read it when a player may have spoken.
- send-chat: say something in the game. Ask here when the goal is unclear.

## Common questions
- I dug stone and got nothing. You weren't holding a pickaxe. Equip one and dig again.
- place-block keeps failing. Equip the block, make sure a solid block touches the spot, and don't stand in it.
- find-blocks found nothing. Use the exact name, try deepslate_ for deep ores, raise maxDistance, or move.
- Can I eat with these tools? There's no eat tool. Tell the user in chat if you're getting hungry.
