# Vibe City: Build, Versioning and Release
Audience: developer
Keywords: version, build number, GAME_VERSION, GAME_BUILD, bump.sh, cache busting, ?v=, index.html, make-playlist.sh, playlist.js, sfxlist.js, gallerylist.js, clublist.js, parklist.js, build-client.js, Electron, electron-builder, AppImage, Windows zip, asar, Documents, prune-assets.sh, release, packaging, ship
Summary: How Vibe City is versioned, cache-busted, shipped and packaged. Covers tools/bump.sh, the generated asset lists from tools/make-playlist.sh, the Electron desktop client built by tools/build-client.js, the player folders in Documents, and tools/prune-assets.sh.

## Two numbers: GAME_VERSION and GAME_BUILD
Vibe City keeps two separate numbers in js/constants.js. `GAME_VERSION = "1.0.0"` is semantic versioning, for people. `GAME_BUILD = 547` is a plain counter with no meaning beyond "not the last one", for the browser. Release 1.0.0 was reached on 10 Oct 2026 at build 492 (Ryan: "pretty solid for a 1.0.0 release"), and since then the version has stayed at 1.0.0 while only the build has moved, up to b547. The build is the ?v= cache-buster on every script and stylesheet in index.html, so it goes up on every ship, even for a one-line comment fix. It shows small under the version in the About window because a stale cache and a real update otherwise look the same. A third number, `SAVE_FORMAT = 6`, is bumped only when the shape of a save changes in a way the loader must know about. The desktop shell's release/package.json carries the version too, because npm cannot read a JS constant.

## Bumping with ./tools/bump.sh
In Vibe City every ship starts with `./tools/bump.sh` and no argument, which bumps the build only. The script reads the current version and build out of js/constants.js, then:
- rewrites every `?v=NNN"` in index.html to the new build, including suffixed tags such as ?v=240-about-1 that Ryan uses to force one file to reload;
- updates `const GAME_BUILD` (and `GAME_VERSION` if it moved);
- syncs "version" in release/package.json when the version changed;
- prints "version a -> b" and "build a -> b", then runs node prof/version.js and fails loudly if anything disagrees.
Arguments exist for patch, minor, major or an exact X.Y.Z, but the standing practice since the release is build only. `./tools/bump.sh major` leaves prof/version.js failing on purpose, because that rig holds the major at 1 and a new major is a deliberate break.

## Cache busting and index.html
Vibe City runs from file:// with plain script and link tags, so the browser cache is controlled entirely by the ?v= on each tag in index.html. At b547 there are 80 tagged files and every one reads ?v=547. Missing a single one leaves the browser serving that file from an old build while everything else, including the About window, looks current. That is why bump.sh rewrites them all and why prof/version.js checks that every ?v= equals GAME_BUILD and that no local script or stylesheet is loaded without a tag. The consequence for shipping: index.html changes on every bump, so index.html must always ship with a bump, even when no markup changed. A new JS file is added to index.html with the current ?v= tag; prof/client.js also checks that every script index.html loads is present in the packaged stage.

## Generated lists: tools/make-playlist.sh
A page opened from file:// cannot list a directory, so in the browser Vibe City reads its content folders from generated JS files. `./tools/make-playlist.sh` rebuilds all five; they start with a GENERATED comment and are never hand-edited:
- js/playlist.js: MUSIC_DIR and MUSIC_TRACKS from audio/music (mp3, ogg, oga, opus, m4a, aac, wav, flac).
- js/sfxlist.js: SFX_DIR and SFX_FILES from audio/effects, .ogg only, named by path without extension (such as "ui/button_click"), skipping anything matched in audio/effects/.sfxignore.
- js/gallerylist.js: GALLERY_DIR and GALLERY_IMAGES from gallery/ (png, jpg, jpeg, gif, webp, avif).
- js/parklist.js: PARK_DIR and PARK_IMAGES from parks/ (added 1.0.0 b510).
- js/clublist.js: CLUB_DIR and CLUB_ANIMS from clubs/ (gif, webp, png, apng).
Names are sorted in C byte order. In the desktop shell the lists come from release/assets.js instead, which reads the same folders at start, so there a new file shows up on the next launch or Ctrl+R. prof/assetlist.js holds the shell's lists to exactly what this script writes.

## The Electron shell in release/
The Vibe City desktop shell lives in release/ and does not contain the game. In development release/main.js opens ../index.html in place, and `npm start` runs it after a one-time `npm install`. The shell files are main.js, preload.js, assets.js, saves.js, quit.js, keys.js, window.js, userfiles.js, discord.js, mods.js, mcp.js, mcp-bridge.js, plus icon.png and icons/. `GAME_ROOT` is path.join(__dirname, "game") when app.isPackaged and the parent folder otherwise. The window runs with contextIsolation true, nodeIntegration false and sandbox true, and preload.js is the only bridge; DevTools are off in a packaged build. release/package.json pins electron ^44.4.3 and electron-builder ^26.15.3, appId city.vibe.game, productName Vibe City.

## Packaging with tools/build-client.js
From release/, Vibe City is packaged with:
- `npm run dist`: Linux AppImage and tar.gz;
- `npm run dist:win`: the Linux builds plus a Windows x64 zip;
- `npm run dist:dir`: only the unpacked app.
compile.sh at the game root runs npm install if needed, then npm run dist:win. tools/build-client.js first stages a throwaway copy in dist/stage: the shell files at the top and the game under game/ (index.html, style.css and the folders js, img, fonts, audio, gallery, clubs, parks). It skips retired, node_modules and .git folders, .wav originals under audio/effects, .DS_Store and Thumbs.db; prof/, tools/ and saves/ never go in. It writes a package.json with asar: true, npmRebuild: false, publish: null, desktopName vibe-city.desktop and artifact name Vibe-City-${version}-${arch}.${ext}, plus a vibe-city.sh launcher (it passes --no-sandbox) and a README.txt. Results are sorted into dist/Package/linux/ and dist/Package/windows/, with the unpacked app beside each as unpacked/. `--stage-only` stops after staging.

## asar and the Documents folders
A Vibe City release packs the whole game, music included, into one read-only archive, app.asar (since 0.9.14; music since 0.9.16). prof/asar.js checks that build-client.js says asar: true. What a player can change lives outside the archive in Documents/Vibe City:
- saves: Documents/Vibe City/saves in a packaged build (release/saves.js); the dev folder uses saves/ beside the game.
- gallery and clubs: Documents/Vibe City/gallery and Documents/Vibe City/clubs, created at start in a packaged build and served by release/userfiles.js as if they were in the game's own folders. Only a bare file name is accepted.
- mods: Documents/Vibe City/mods, used in dev and packaged builds alike (release/mods.js).
parks/ is not a player folder (b544, Ryan): park pictures ship with the game because each one comes with written lines. userfiles.js also serves audio and non-ASCII file names out of the archive itself, because Electron fails to load those from inside app.asar.

## Retiring files: tools/prune-assets.sh
Vibe City retires old art through tools/retired-assets.txt: one path per line relative to the game folder, # for comments, and since 0.9.28 a line may be a glob such as img/res/*.png. The comments record why each file was retired. `./tools/prune-assets.sh` shows what would go; `./tools/prune-assets.sh --yes` deletes it. It also empties img/_to_delete/, where files are parked when they can be moved but not deleted. Lines starting with / or containing .. are skipped as outside the game folder. Never list img/vibe-city.ico or img/vibe-city-mark.svg, and never write a glob wide enough to catch them (img/*.png or img/*).

## The ship checklist
A Vibe City ship, in order:
1. Make the change.
2. Run ./tools/make-playlist.sh if any music, effects, gallery, parks or clubs file was added or removed.
3. Run ./tools/bump.sh with no argument and check that prof/version.js passes.
4. Run ./tools/suite.sh (or a filtered subset while iterating, then the full suite before shipping).
5. Ship the changed files and always index.html, since the bump rewrote its ?v= tags, plus js/constants.js.
6. For a desktop release, cd release and npm run dist or dist:win.

## Common questions
**Q: How do I bump the build?**
A: Run ./tools/bump.sh with no argument. It raises GAME_BUILD by one and rewrites every ?v= in index.html, then runs prof/version.js.

**Q: Does the version change on a normal ship?**
A: No. Vibe City has stayed at release 1.0.0 since build 492, and only the build number goes up.

**Q: Why must index.html ship with every bump?**
A: The ?v= cache-busters live in index.html. Without the new copy the browser keeps loading the old files.

**Q: Can I edit js/playlist.js or js/sfxlist.js by hand?**
A: No. They are generated by tools/make-playlist.sh, along with gallerylist.js, parklist.js and clublist.js. Re-run the script instead.

**Q: Why is a new sound not playing in the browser?**
A: It must be .ogg, not listed in audio/effects/.sfxignore, and make-playlist.sh must have been re-run so js/sfxlist.js names it.

**Q: How do I build the Windows client?**
A: cd release, npm install once, then npm run dist:win. The zip lands in dist/Package/windows/.

**Q: Where do players put their own pictures in the desktop game?**
A: Documents/Vibe City/gallery and Documents/Vibe City/clubs. Saves go in Documents/Vibe City/saves and mods in Documents/Vibe City/mods.

**Q: Is the release packed?**
A: Yes, into app.asar, with music included. Only the Documents folders are loose.

**Q: How are old sprites deleted?**
A: Add them to tools/retired-assets.txt with a note, then run ./tools/prune-assets.sh --yes.
