# Vibe City: Getting Started
Audience: player
Keywords: start, new game, new city, main menu, menu button, save, load, save file, world generation, seed, map size, settings, preferences, game speed, pause, fast forward, month length, splash screen, loading screen, about, exit, quit, desktop app, browser
Summary: How to start playing Vibe City, from the loading screen and the main menu to generating a new city, saving and loading, and the Settings window. It also covers the three game speeds, how long a month lasts, and what is and is not kept between sessions.

## The loading screen and first launch
The loading screen in Vibe City is a card with the game's icon, the name "Vibe City", a progress bar, the line "Building the city" and the version (v1.0.0). It shows from launch until the map's first frame is drawn, for at least 2.5 seconds, then fades. The same card returns, reading "Loading your city", while a save loads.

There is no separate title screen. The game starts straight into an empty city on a random map with the default world settings (rolling terrain, lakes, sparse trees, no river), $20,000, an 8% tax rate and the date Jan, year 1, with the clock running at normal speed. For different land, choose New City in the main menu.

## The main menu
The main menu in Vibe City opens from the menu button at the far right of the top bar. Click it again, click anywhere else, or press Escape to close it. The menu holds, from top to bottom:

- New City: opens the New City window (world generation).
- Save: saves the current city to a file.
- Load: opens a save file.
- Disasters: opens the Disasters window, where you can unleash a disaster on your own city on purpose. There is no undo and no refund.
- Settings: opens the Settings window.
- About: the version (1.0.0), build number and credits (created by Ryan Autet, music from Open Lo-Fi).
- Exit: desktop app only. It asks "Quit Vibe City?" with Quit and Keep playing; Enter and Escape both choose Keep playing. In a browser the button is hidden.

## Starting a new city
The New City window in Vibe City is where you choose what kind of map to play on. Nothing happens to your current city until you press Generate, and the window warns you: "Generating replaces the current city. Save first if you want to keep it."

The options are:

- Terrain: Flat (wide open ground, cheap to build on), Rolling (gentle hills), Hilly (plenty of slopes), Mountains (steep country, budget for tunnels).
- Water: Dry (no lakes at all), Ponds (a few small ponds), Lakes (lakes scattered across the map), Islands (the land breaks up into islands).
- Trees: None, Sparse, Wooded (groves), Forest (thick forest, cleared as you build).
- River: Off or On. On carves a river that winds from one edge of the map to the other.
- Funds: $10k (Hard), $20k (Normal), $50k (Easy).
- Seed: a text box of up to 16 characters. The same seed with the same options always makes the same map. The dice button rolls a new random six-digit seed.

The defaults are Rolling, Lakes, Sparse, River off and $20,000.

## The map preview and generating
The New City window in Vibe City shows a live preview of the exact map your choices and seed will make, with the share of Water and Hills and the number of Trees underneath.

Press Generate (or Enter in the seed box) to build it; "New city generated" confirms it. The window stays open afterwards so you can keep rolling maps until one feels right, then close it with its close button or Escape. Surprise me rolls a new seed and generates it in one click. Your choices are remembered for next time, but the seed is rolled fresh each time the window opens.

A new city starts on Jan, year 1, with an 8% tax rate and the funds you picked. It is called "Vibe City" until a year in, when the game pauses and asks you to name it (up to 14 characters). Click the city name at the top left to rename it any time.

## Map size
Every map in Vibe City is 128 by 128 tiles (16,384 tiles), the same size as SimCity 2000, and there is no map size option. Saves from older versions on smaller maps (48 by 32, 96 by 64 or 96 by 96) still load: the old city is placed inside the 128 by 128 world with new country around it, blended over 6 tiles so the join does not show. Coasts, rivers and connections to neighbouring towns that ran off the old edge are carried out to the new edge. A save from a bigger world cannot be loaded.

## Saving your city
The Save button in Vibe City's main menu writes the whole city to a .json file. The file is named after your city and the date, for example "daves-y176m4.json" for a city called Dave's in year 176, month 4. An unnamed city saves as "vibe-city-...". Where the file goes depends on how you play:

- Desktop app: a native save dialog opens in the game's saves folder with the filename already filled in. When running from a folder, that is the saves folder beside the game; in a packaged build (such as the AppImage) it is Documents/Vibe City/saves.
- Chrome, Edge and other Chromium browsers: a "Save as" file picker opens.
- Firefox and browsers without a picker: the file downloads normally.

A message "City saved" confirms it. Vibe City has no autosave, so save often. Quitting or reloading without saving loses everything since the last save.

## Loading a city
The Load button in Vibe City's main menu opens a save file. In the desktop app a native dialog opens in the saves folder; in a browser the normal file chooser opens and accepts .json files. While the city loads the loading card says "Loading your city", and then the message "City loaded" appears. If the file cannot be read, you see "Could not read save file" and your current city is left alone.

A save keeps the map, every building and its level, all networks, funds, tax rate, date, the city's name, milestones, neighbours, fallout and arcade records. Cars are not saved; traffic refills on its own.

## Game speed and pausing
Vibe City has three speed buttons on the right of the top bar: Pause, Normal and Fast. One tick of the simulation is one in-game month: growth, the monthly budget and the calendar all move together once a month.

- Pause stops the clock completely. You can still build, bulldoze and look around while paused, and a ticket you buy at a station still rides while paused.
- Normal runs one month every 4.0 seconds by default, so a year takes 48 seconds.
- Fast runs about 2.6 times quicker than Normal; at the default it is one month every 1.56 seconds. It is never faster than 0.15 seconds per month.

There is no keyboard shortcut for the speed buttons. Some windows stop the clock for you: a milestone window pauses the game until you press Continue, and the one-year "Name your city" window pauses it until you name the city or close the window. Both put the speed back the way it was.

## The Settings window
The Settings window in Vibe City opens from the main menu. Settings belong to your computer, not to a city: they are kept in the browser's local storage, survive reloads, are not changed by New City or Load, and are never written into save files. The window can be dragged by its title bar.

Simulation:
- Month length: 0.8 to 5.0 seconds, in steps of 0.1, default 4.0. How long a month takes at Normal speed. Fast speed scales with it.
- Traffic: 0% to 200%, default 100%. How many cars are on the roads.
- Random events: 0% to 200%, default 100%. How often fires, robberies, storms and fairs happen. 0 shows "Off" and stops them. Disasters from the Disasters window are not affected.

Audio:
- Music (the radio), default 60%. Sound (building, traffic, sirens), default 80%. Interface (menus and buttons), default 70%. All 0% to 100% in steps of 5.

Display:
- Full screen (F11 does the same).
- Ground textures, on by default. Off draws the land in flat colours, which is lighter on slower machines.
- Cab view on train rides, on by default.
- Show FPS, off by default: a frame rate readout in the corner.
- Show event history, off by default: a running list of what has happened this session.

The desktop app adds Discord Rich Presence (on by default) and Let an AI play (off by default).

## Common questions
**Q: How do I start a new game in Vibe City?**
A: Open the main menu with the button at the right of the top bar, choose New City, pick your terrain, water, trees, river and starting funds, then press Generate. Save your current city first if you want to keep it.

**Q: Can I choose a bigger or smaller map?**
A: No. Every Vibe City map is 128 by 128 tiles. Old saves from smaller maps load into the middle of a 128 by 128 world with new land around them.

**Q: How do I get the same map again?**
A: Type the same seed into the Seed box with the same options. Same seed and same options always make the same map.

**Q: Does Vibe City autosave?**
A: No. There is no autosave. Use Save in the main menu regularly; quitting or reloading loses anything unsaved.

**Q: Where are my saves in the desktop app?**
A: In the saves folder beside the game when it runs from a folder, or in Documents/Vibe City/saves in a packaged build such as the AppImage. The save and load dialogs open there automatically.

**Q: How do I pause the game?**
A: Click the Pause button among the three speed buttons on the right of the top bar. There is no pause hotkey. You can still build while paused.

**Q: How long is a year?**
A: At the default month length of 4.0 seconds, a year is 48 seconds at Normal speed and about 19 seconds at Fast. Change it with the Month length slider in Settings.

**Q: Are my settings saved inside my city file?**
A: No. Settings are stored on your computer and apply to every city.

**Q: How do I rename my city?**
A: Click the city name at the top left. Names can be up to 14 characters.
