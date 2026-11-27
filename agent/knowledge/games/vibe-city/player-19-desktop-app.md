# Vibe City: The Desktop App
Audience: player
Keywords: desktop app, desktop version, Electron, install, download, AppImage, Windows, Linux, exe, zip, SmartScreen, saves, save folder, Documents/Vibe City, player folders, gallery folder, clubs folder, mods, mods folder, Discord, Rich Presence, full screen, browser version, differences
Summary: Vibe City runs in a web browser and as a desktop app for Linux and Windows. The desktop app saves to Documents/Vibe City/saves, lets you add your own gallery pictures and club dancers in Documents/Vibe City, loads mods from Documents/Vibe City/mods, and can show your city's status on Discord. This page covers installing it, where your files go, and how it differs from the browser.

## Installing and running the desktop app
The Vibe City desktop app comes as a Linux build and a Windows build. There is no Mac build yet.
- Linux AppImage: download it, make it executable if your file manager lost the permission (chmod +x on the file), and run it directly. No installation needed.
- Linux tar.gz: unpack the folder and start the game with vibe-city.sh inside it.
- Windows zip: unzip it anywhere and run "Vibe City.exe" in the folder. There is no installer.
The builds are not code signed, so the first time you run the Windows version, SmartScreen may warn you. Click "More info", then "Run anyway". The app opens a 1400 by 900 window (it can be resized down to 900 by 600) and remembers whether you last played in full screen.

## Where your saves go
In the Vibe City desktop app, saving opens a proper native Save As dialog that starts in Documents/Vibe City/saves, with the file name already filled in. Loading opens a native Open dialog in the same folder. Saves are .json files, and you can save anywhere you like by changing folder in the dialog. The saves folder is created the first time you save or load, not before.

This is the main difference from the browser. In a Chromium based browser the save picker opens wherever it was last, and in Firefox there is no picker at all, so saves download to your Downloads folder. Save files are the same in both: a city saved in the browser loads in the desktop app and the other way round.

The game has no autosave. The menu's Exit item works in the desktop app and asks "Quit Vibe City? Anything you have not saved will be lost." with Keep playing as the safe default.

## Your player folders: gallery and clubs
The Vibe City desktop app keeps two player folders in Documents/Vibe City, made the first time the app starts:
- Documents/Vibe City/gallery: your own pictures for the Art Gallery. PNG, JPG, GIF, WebP and AVIF work.
- Documents/Vibe City/clubs: your own dancers for the Club. Animated GIF, WebP, PNG and APNG work.
Pictures and dancers you put there show alongside the ones the game ships, sorted by name. Reload the game (Ctrl+R) or restart it after adding files. A file with exactly the same name as one the game already ships is ignored in favour of the game's own, so give yours distinct names. New versions of the game leave these folders alone.

The parks are not a player folder. Park pictures ship with the game because each one is written for, with its kid and their lines, so you cannot add your own. The music is not a player folder either: the soundtrack is built into the app.

## Mods
Mods are a separate download, never part of the game, and they work only in the Vibe City desktop app. Each mod is a folder you put in Documents/Vibe City/mods; that folder is made when the app starts. A mod folder holds a mod.json file, the mod's pictures, and optionally a page for a window the building opens (a mini game). Reload (Ctrl+R) or restart the game after adding one.

A mod adds a new building to the build menu, in the drawer the mod chooses (Transport, Utilities, Civic or Decor, Decor by default). Its tooltip shows its price, what it does, its monthly upkeep and "A mod by" its author. Mod buildings work like the game's own: they can need power and water, give jobs and boost growth. A mod with a window opens it when you click the building with the pan tool. Up to 64 mods load at once.

## Mod safety and missing mods
A Vibe City mod's window runs walled off from the game: it cannot reach your files, the game's internals or the internet, and can only send the game a few checked messages. A mod may pay money into your city, but never more than its stated monthly amount, and a toast tells you when it does ("X paid $Y into the city").

If a mod has a problem (a bad mod.json, wrong picture count, a duplicate id) a "Mod trouble" toast appears a few seconds after start. If you open a city that used a mod you no longer have installed, those buildings become grass and a toast lists which mods are missing. Install the mod again and the buildings come back, unless you have built on those lots in the meantime.

## Discord status
The Vibe City desktop app can show what you are doing on your Discord profile (Discord Rich Presence). It is on by default and has its own switch in Settings: "Discord Rich Presence". What it shares:
- your population and city funds,
- whether you are starting a city, building a city, or the city is paused,
- how long this session has been running.
It never sends your city's name, your save paths or your player files. It updates at most once every 15 seconds, and not at all if nothing changed. Discord must be running on the same computer with activity sharing turned on; no login or bot is involved. On Linux it also finds the Flatpak and Snap versions of Discord and Vesktop's Flatpak. If Discord is not running, nothing happens and the app keeps trying quietly. The browser version has no Discord connection and no setting for it.

## Other differences from the browser version
The Vibe City desktop app and the browser game are the same game with the same cities. Beyond saves, player folders, mods and Discord, the desktop app:
- Reads its own music, effects, gallery, clubs and parks folders when it starts, so everything that is there shows up.
- Remembers full screen between runs. F11 toggles it; the Full screen box in Settings follows it.
- Has no menu bar, so pressing Alt does nothing to the map.
- Ctrl+R reloads the game (unsaved progress is lost, so save first). F12 does nothing on purpose.
- Has a desktop only Settings option, "Let an AI play", which opens a local connection so an AI such as Claude can look at your city and build in it. It is off by default; click or press any key to take over.
- Has a working Exit item in the menu.
Settings such as volumes, month length and traffic are stored by the app, separately from your city saves.

## Common questions
**Q: Where are my saves in the desktop app?**
A: Documents/Vibe City/saves. The Save and Open dialogs start there.

**Q: Where do saves go in the browser?**
A: Wherever the browser's file picker last was in Chromium browsers, or your Downloads folder in Firefox.

**Q: How do I add my own pictures to the Art Gallery?**
A: Put them in Documents/Vibe City/gallery, then reload with Ctrl+R or restart.

**Q: Can I add my own park pictures?**
A: No. Parks is not a player folder; only gallery and clubs are.

**Q: Where do mods go?**
A: In Documents/Vibe City/mods, one folder per mod with its mod.json.

**Q: Do mods work in the browser?**
A: No. Mods load only in the desktop app.

**Q: What does Discord see?**
A: Population, city funds, whether you are starting, building or paused, and session time. Never your city name or files.

**Q: How do I turn off Discord status?**
A: Untick "Discord Rich Presence" in Settings.

**Q: Windows says the app is unrecognised. Is that normal?**
A: Yes. The build is not signed. Click "More info", then "Run anyway".

**Q: Is there a Mac version?**
A: Not yet. There are Linux and Windows builds.

**Q: Does the desktop app autosave?**
A: No. Save before quitting or reloading; the Exit item warns you.
