# Vibe City: Recipes for Adding Content
Audience: developer
Keywords: add content, park pictures, PARK_PICTURES, park lines, parks folder, building variant, new sprite, sound effect, sfx, music, audio, ogg, sfxignore, casino dealer, CASINO_DEALERS, DEALER_LOOKS, portrait, arcade kid, ARCADE_RIVALS, bookie, recipe, how to add
Summary: Step by step recipes for the content Vibe City is built to grow: park pictures with their lines, a new building variant sprite, sound effects and music, a casino dealer, and character portraits. Each recipe names the files, tables and scripts involved.

## Adding a park picture: the files
Vibe City park pictures live in parks/ at the game root and show when a player clicks a park with the pan tool (1.0.0 b510). They ship with the game; parks/ is not a player folder (b544, Ryan), because each picture is written for with its own speaker and lines. The shipped pictures are square PNGs, 1254 x 1254, named in lower case with dashes and a -v1 suffix, such as kit-pouncing-at-sparrow-v1.png. Accepted formats are png, jpg, jpeg, gif, webp and avif. After dropping a file in, run ./tools/make-playlist.sh so js/parklist.js (PARK_IMAGES) lists it for the browser; the desktop shell reads the folder itself (release/assets.js). The caption is the file name without the extension and the -v1 suffix, with dashes and underscores shown as spaces. A picture whose name starts with a kid's id and a dash (kit-, mochi-, pip-, rue-) brings that kid even without a table entry.

## Adding a park picture: the PARK_PICTURES entry
In js/park.js each picture gets an entry in PARK_PICTURES, keyed by the file name in lower case without the -v1 suffix and without the extension: kit-kite-tangle-v1.png is "kit-kite-tangle". The fields:
- who: the kid who talks about it, one of "kit", "mochi", "pip" or "rue" (ARCADE_RIVALS ids).
- alt: optional stand in while who is locked. Rue is locked until Kit is beaten all the way down (arcade.rank >= 3), so Rue pictures use alt.
- lines: what who says about the picture.
- altLines: optional lines for the alt speaker, such as Kit talking about his brother Rue.
More lines can be appended through PARK_MORE and PARK_MORE_ALT, which the file folds into lines and altLines (b547 gave every picture six). The first line over a new picture is about the picture; after that, every PARK_LINE_EVERY (60000 ms) the kid says that or their usual chat from PARK_LINES. In a line, {city} becomes the city's name (or "the city") and {pop} the population with thousands separators.

## Park line rules
Every park line in Vibe City follows the game's text rules, and all 450 or so shipped lines pass them:
- no dashes of any kind, no semicolons and no colons;
- plain ASCII only, so straight apostrophes and no emoji;
- each line ends with . or ! or ?;
- short spoken sentences in the kid's own voice, often two or three per line;
- capitals for shouting are fine ("THAT SQUIRREL TOOK MY STRAWBERRY.").
Kit is the cocky rival kid who chases sparrows and never admits losing, Mochi is sweet and counts things, Pip is the speedy racer, and Rue is Kit's calm older brother. Write to match. Keep {city} and {pop} spelled exactly with braces.

## Adding a building variant sprite
To add a fifth look to a sprited Vibe City building, or a new set:
1. Generate a strip from the right template (tools/make-*-template.py) and screen it with python3 tools/check-strip.py <strip.png>.
2. For house, shop and factory tiers, run python3 tools/install-strip.py <strip.png> <dir> <tier>, which slices, copies to img/<dir>/L<tier>_R0..3.png and writes span, nudge and facing into js/sprites.js. A whole new set is one more entry in RES_SETS, COM_SETS or IND_SETS plus its folder; nothing else counts the sets.
3. For variant types, slice with tools/slice-houses.py (or tools/fit-slab.py, tools/fit-block.py for slabs and big lots), save as img/<name>/V<v>_R<r>.png, and add a row to <NAME>_SPRITE_SPAN and <NAME>_SPRITE_Y_NUDGE. Raise <NAME>_VARIANTS so applyTool in js/economy.js can roll it.
4. Make sure the draw goes through lotSprite, and the type has no PALETTE entry in js/colors.js.
5. To take a bad variant out of use without renumbering, give the VARIANTS table an array, like CLUB_IN_USE = [0, 1, 2, 3].
6. Retire replaced files in tools/retired-assets.txt, then bump and run the suite (prof/houses.js and prof/comsets.js check set shapes).

## Adding sound effects
Vibe City sound effects live under audio/effects/ in folders such as ui/, build/, events/, casino/ and world/, and the game plays one with sfx("folder/name"), which appends .ogg. Rules:
- Ogg Vorbis only. A .wav in the folder is ignored by both the browser list and the shell list.
- Mono for short sounds, 44.1 or 48 kHz, quality 4 is plenty. A clean start with no leading silence. Loops cut on a zero crossing.
- Convert with: ffmpeg -i in.wav -ac 1 -c:a libvorbis -q:a 4 -af silenceremove=start_periods=1:start_threshold=-50dB out.ogg (skip the silence removal on very quiet clips).
- Anything that should stay silent for now goes in audio/effects/.sfxignore.
- Run ./tools/make-playlist.sh so js/sfxlist.js (SFX_FILES) names it. sfx() stays silent for a name the list does not have, so a missing file never errors.
Folder decides the slider: ui/ sounds follow the Interface volume, the rest the Sound volume. A new HOOK sound also needs the one line that calls sfx() where the event happens.

## Adding music
Vibe City music is any file in audio/music/ (mp3, ogg, oga, opus, m4a, aac, wav or flac, top level only). The browser reads the list from js/playlist.js (MUSIC_TRACKS), so run ./tools/make-playlist.sh after adding or removing tracks; the desktop shell lists the folder itself on the next launch or Ctrl+R. Track names may contain spaces and non-ASCII; they are URL-encoded at play time, and in a packaged build release/userfiles.js serves audio from inside app.asar itself because Electron cannot. Music is packed into app.asar in a release, so players cannot add tracks to a packaged game; only gallery and club pictures live loose in Documents/Vibe City.

## Adding a casino dealer
Vibe City casino dealers are listed in js/casino.js. A new dealer is a name in `CASINO_DEALERS = ["pink", "snow", "ginger", "cocoa", "lilac", "teal"]` and three pictures in img/dealer/: <name>_neutral.png, <name>_win.png (the city came out ahead) and <name>_lose.png (the house did). Shipped dealer pictures are RGBA PNGs 320 x 516. If the sheet has other faces, map the moods in DEALER_LOOKS, for example `lilac: { neutral: "smirk", win: "laugh", lose: "wink" }`; an optional wow mood is used for a blackjack or a dealer bust and falls back to win. A dealer is picked at random each time the window opens, never the one who dealt last. Dealers talk in DEALER_SAYS and dealerLine, cat style ("nya", "mew", "hun") and in plain sentences.

## Adding a character portrait
Vibe City portraits are plain image files named by convention:
- Arcade kids: ARCADE_RIVALS in js/arcade.js (mochi, pip, kit, rue), with faces img/arcade/<img or id>-smug.png, -laugh.png and -pout.png via arcadeFace(r, face). Kit sets img: "rival", so his files are rival-smug.png and so on. A new kid needs an entry with id, name, tag, he, him, col, ranks and tr.
- Bookies at the Track: BOOKIES = ["", "blond"] in js/races.js. The first uses img/bookie/<face>.png, the rest img/bookie/<name>_<face>.png, with faces sly, shock and laugh.
- The advisor (img/advisor: content, furious, gettingby, thriving, unhappy), the archivist (img/archivist: calm, proud) and the teacher (img/teacher) are fixed sets read by js/hud.js, js/milestones.js and js/school.js.
Portraits are transparent PNGs; arcade faces ship about 415 x 521.

## Common questions
**Q: What is the PARK_PICTURES key for parks/pip-racing-toy-car-v1.png?**
A: "pip-racing-toy-car": lower case, no extension, no -v1 suffix.

**Q: Which kids can speak over a park picture?**
A: kit, mochi, pip and rue. Rue is locked until Kit is fully beaten, so give Rue pictures an alt speaker.

**Q: Can a park line use a colon or a dash?**
A: No. No dashes, semicolons or colons, ASCII only, and every line ends with a full stop, an exclamation mark or a question mark.

**Q: What do {city} and {pop} do?**
A: {city} becomes the city's name and {pop} the population when the line is shown.

**Q: My new sound does not play. Why?**
A: Check it is .ogg, under audio/effects, not in .sfxignore, that ./tools/make-playlist.sh was re-run, and that code calls sfx with the right "folder/name".

**Q: How do I add a casino dealer?**
A: Add the name to CASINO_DEALERS in js/casino.js and put <name>_neutral.png, <name>_win.png and <name>_lose.png in img/dealer/, mapping other face names in DEALER_LOOKS.

**Q: Where do Kit's portraits live?**
A: img/arcade/rival-smug.png, rival-laugh.png and rival-pout.png, because Kit's entry sets img: "rival".

**Q: Do I need to run anything after adding a park picture?**
A: Run ./tools/make-playlist.sh for the browser list, add the PARK_PICTURES entry, then bump and ship.
