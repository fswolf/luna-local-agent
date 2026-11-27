"""What each setting in config.json is: its kind, allowed values and a
one-line explanation, for the settings pane (ui/settings_pane.py) and /set.

Kinds: bool, int, float, text, choice, list, dict, secret.

  list    a list of strings
  dict    a nested object, only editable in the file itself
  secret  a password, token or key - shown masked
  choice  one of a fixed set, given as the third item

Plain data, no imports: keys are dotted paths in config.json, the same
ones /set takes. A plugin's settings are under plugins.<name>. An
explanation ending in "(?)" is a guess from the key's name.
"""

# Section titles, in the order the pane shows them (top-level key -> title).
# A key in MERGED sits in another key's section: tts.* under Voice, so her
# voice and how it's made are one section, the on/off switch first.
MERGED = {"tts": "voice"}

SECTIONS = {
    "name": "Name",
    "voice": "Voice",
    "stt": "Listening",
    "wake_word": "Wake word",
    "generation": "Replies",
    "llm": "Model server",
    "mood": "Mood",
    "situation": "Situation",
    "music": "Music",
    "offers": "Offers",
    "portrait": "Portrait",
    "ui": "Terminal",
    "theme": "Theme",
    "vision": "Vision",
    "camera": "Camera",
    "people": "People",
    "station": "Relay stations",
    "comfyui": "ComfyUI",
    "desktop": "Desktop",
    "tools": "Tools",
    "files": "Files",
    "shell": "Shell",
    "email": "Email",
    "web_search": "Web search",
    "knowledge": "Knowledge base",
    "reminders": "Reminders",
    "alarms": "Alarms",
    "calendar": "Calendar",
    "mcp": "MCP servers",
    "history": "History",
    "long_term_memory": "Long-term memory",
    "thoughts": "Thought log",
    "adaptive": "Adaptive thinking",
    "grounding": "Grounding check",
    "self": "Learning",
    "logging": "Logging",
    "monitor": "Live monitor",
    "plugins": "Plugins",
}

# path: (kind, explanation[, choices])
SCHEMA = {
    # --- Name ---------------------------------------------------------------
    "name": ("text", "Luna's name, if agent/agent.json doesn't set one"),

    # --- Voice (her voice and how it's made: tts.* sits here too) ----------
    "tts.enabled": ("bool", "Speak replies out loud. Off: replies only show on screen (alarms still ring)"),
    "voice": ("text", "The voice to use, by its name on the speech server (like af_bella), or a blend"),

    "tts.url": ("text", "Address of the speech server (kokoro-reader)"),
    "tts.provider": ("choice", "Where the voice comes from: kokoro (your own speech server) or elevenlabs (ElevenLabs' cloud, so replies are sent to them)",
                     ("kokoro", "elevenlabs")),
    "tts.elevenlabs.voice_id": ("text", "Which ElevenLabs voice to use (/voice lists yours, /voice <name> picks one)"),
    "tts.elevenlabs.model": ("text", "ElevenLabs model: eleven_flash_v2_5 is faster, eleven_multilingual_v2 sounds richer"),
    "tts.elevenlabs.stability": ("float", "ElevenLabs stability (0 = more varied, 1 = steadier). Empty uses the voice's own"),
    "tts.elevenlabs.similarity_boost": ("float", "How closely ElevenLabs sticks to the original voice (0 to 1). Empty uses the voice's own"),
    "tts.speed": ("float", "Talking speed (1 = normal, higher is faster)"),
    "tts.volume": ("float", "Voice volume (1 = normal)"),
    "tts.pitch": ("float", "Pitch shift in semitones (up sounds higher and younger, down lower and older)"),
    "tts.player": ("choice", "How sound reaches your speakers: auto uses afplay on a Mac and PortAudio everywhere else",
                   ("auto", "afplay", "portaudio")),
    "tts.latency": ("text", "How much audio is buffered before it plays: high is smoothest, low if high ever lags, or a number of seconds"),
    "tts.strip_tilde": ("bool", "Skip the ~ in words like \"Mrrp~\" so it isn't read out as \"tilde\""),

    # --- Listening ----------------------------------------------------------
    "stt.mode": ("choice", "How listening works: auto (HOME starts, a pause ends it), manual (HOME starts and stops) or open (hands-free)",
                 ("auto", "manual", "open")),
    "stt.vad": ("choice", "How it tells you're talking: silero (a speech model), energy (just loudness) or auto (silero when it's installed)",
                ("auto", "silero", "energy")),
    "stt.vad_threshold": ("float", "How sure it must be that you're speaking (0 to 1, lower reacts sooner)"),
    "stt.model": ("text", "Speech recognition model size, like small. Bigger is more accurate but slower"),
    "stt.language": ("text", "The language you speak, as a code like en. Empty guesses, which often fails on short clips"),
    "stt.sensitivity": ("float", "Mic sensitivity: above 1 for a quiet mic, below 1 for a noisy room"),
    "stt.silence_seconds": ("float", "How long a pause ends what you're saying (seconds)"),
    "stt.max_seconds": ("float", "Longest you can talk in one go (seconds)"),
    "stt.manual_max_seconds": ("float", "Longest you can talk in one go in manual mode (seconds)"),
    "stt.no_speech_timeout": ("float", "How long to wait for you to start talking before giving up, in auto mode (seconds)"),
    "stt.settle_seconds": ("float", "In open mode, the pause after Luna speaks before the mic listens again (seconds)"),
    "stt.send_audio": ("bool", "Send the recording too, not just the words, for models that can hear (omni models)"),
    "stt.audio_max_seconds": ("float", "Recordings longer than this send only the words (seconds)"),
    "stt.barge_in": ("bool", "Let you interrupt Luna by talking over it (needs the silero detector)"),
    "stt.barge_in_seconds": ("float", "How long you have to talk over Luna before it stops (seconds)"),
    "stt.barge_in_margin": ("float", "How much louder than Luna's voice you need to be to interrupt. Raise it if you use speakers"),
    "stt.barge_in_boost": ("float", "Makes the mic less eager while Luna is talking, so its own voice doesn't count as you"),

    # --- Wake word ----------------------------------------------------------
    "wake_word.enabled": ("bool", "Start listening when you say a wake word, instead of pressing HOME (open mode)"),
    "wake_word.model": ("text", "The wake word: an openWakeWord name (hey_jarvis, alexa...) or the path to your own"),
    "wake_word.threshold": ("float", "How sure it must be it heard the wake word (0 to 1). Raise it if the TV sets it off"),
    "wake_word.follow_up_seconds": ("float", "How long Luna keeps listening after a reply, so you can follow up without the wake word (seconds)"),
    "wake_word.cooldown_seconds": ("float", "How long the wake word is ignored after it's heard, so it doesn't trigger twice (seconds)"),

    # --- Replies ------------------------------------------------------------
    "generation.max_tokens": ("int", "Longest a reply can be, thinking included (tokens)"),
    "generation.reasoning": ("text", "How hard a reasoning model thinks, like low"),
    "generation.sampling": ("dict", "Sampling settings per model, by part of its name (temperature, top_k, presence_penalty...). Empty, or a model with no match: the model server's own settings. See docs/models.md"),

    # --- Model server -------------------------------------------------------
    "llm.backend": ("choice", "Which model server: auto uses llama-server when it's running, otherwise LM Studio",
                    ("auto", "lmstudio", "llama")),
    "llm.lmstudio_url": ("text", "LM Studio's address (also for any other OpenAI-style server)"),
    "llm.llama_url": ("text", "llama-server's address"),
    "llm.model": ("text", "Which model to ask for by name. Empty uses whatever is loaded"),
    "llm.stable_prompt": ("bool", "Keep the start of every prompt the same so llama-server can reuse it (faster replies)"),
    "llm.api_key": ("secret", "API key, for a model server that needs one (safer in ~/.config/ai-voice/llm.json)"),
    "llm.embed_url": ("text", "Address of the embedding server, for remembering facts by meaning (optional)"),
    "llm.embed_query_prefix": ("text", "Text put before each memory search sent to the embedding model. Most models want this empty"),
    "llm.embed_min_score": ("float", "How close in meaning a fact must be to be recalled on that alone (0 to 1)"),
    "music.url": ("text", "Address of the music-listening service (server/music). Empty turns it off"),
    "music.after": ("float", "How far into a new song before Luna listens to it (seconds)"),
    "music.seconds": ("float", "How much of a song is recorded to listen to (3 to 20 seconds)"),
    "music.dance": ("bool", "The avatar dances to upbeat music and bobs its head to calm songs"),
    "music.rave": ("bool", "Rave music sometimes brings out the avatar's rave gear (pacifier and glow sticks)"),
    "llm.rerank_url": ("text", "Address of the reranker server, which sorts recalled memories by relevance (optional)"),
    "llm.rerank_candidates": ("int", "How many recalled memories the reranker looks at"),

    # --- Mood ---------------------------------------------------------------
    "mood.enabled": ("bool", "Give Luna moods that change how it talks"),
    "mood.intensity": ("float", "How strong moods are (0 = barely any, 1 = normal, 2 = very emotional)"),
    "mood.warmth": ("float", "How warm Luna is when nothing's going on (0 to 1)"),
    "mood.recovery": ("float", "How quickly moods fade (0 = never, 1 = after one reply)"),
    "mood.hurt": ("float", "How much an insult hurts (0 to 4; at 2, two insults make Luna angry)"),
    "mood.forgive": ("float", "How quickly Luna gets over being hurt (0.05 to 1, higher is faster)"),
    "mood.settle_minutes": ("float", "Minutes for half of any extra warmth or energy to wear off on its own, idle or not"),
    "mood.desire_minutes": ("float", "Minutes for half of the lewd row's desire to wear off on its own, idle or not"),
    "mood.voice": ("bool", "Let the mood change the voice a little (sleepy sounds slower and lower)"),
    "mood.affection": ("bool", "Notice when you're kind (adds one small model call after each reply)"),
    "mood.prompt": ("bool", "Tell the model what mood Luna is in"),
    "mood.face": ("bool", "Show the mood on the avatar's face"),
    "mood.gestures": ("bool", "Show the mood in the avatar's idle moves and gestures"),
    "mood.emotes": ("bool", "Little emotes, like hearts, next to the avatar's head"),
    "mood.walk_away": ("bool", "Luna stops talking for a while if you're really hostile"),
    "mood.walk_away_after": ("int", "How many hostile messages in a row before Luna walks away"),
    "mood.walk_away_minutes": ("float", "How long Luna stays away (minutes)"),

    # --- Situation ----------------------------------------------------------
    "situation.enabled": ("bool", "Give the model a few live details each turn: your window, music, computer load, plugins, reminders"),
    "situation.clock": ("choice", "The time in her prompt. part of day: the date and morning, evening or night, the exact time only when your message is about time (small models otherwise quote it in every reply). exact: the minute, every turn", ("part of day", "exact")),
    "situation.window": ("bool", "Include the window you're in"),
    "situation.music": ("bool", "Include the music that's playing"),
    "situation.machine": ("bool", "Include CPU, memory and GPU load"),
    "situation.plugins": ("bool", "Include which plugins are running"),
    "situation.reminders": ("bool", "Include the next reminder"),
    "situation.calendar": ("bool", "Include what's on your calendar today (calendar.* sets the calendars up)"),
    "situation.hands": ("bool", "Include what the avatar is holding, like a coffee or a book"),
    "situation.clothes": ("bool", "Include what the avatar is wearing, when some of it is off (human models only)"),

    # --- Offers -------------------------------------------------------------
    "calendar.enabled": ("bool", "Let Luna read your calendars (read-only): what's on, in her live details, and reminder offers"),
    "calendar.google": ("secret", "Google Calendar's secret iCal address (its settings: Integrate calendar, Secret address in iCal format)"),
    "calendar.ics": ("list", "Other calendars to read: iCal links or .ics files (a holidays feed, a shared calendar)"),
    "calendar.calcurse": ("bool", "Read calcurse on this computer"),
    "calendar.refresh_minutes": ("float", "How often the calendars are read again while Luna is in use (minutes)"),
    "offers.enabled": ("bool", "Let Luna notice things by itself (a full disk, a date coming up) and offer to help once, next time you talk"),
    "offers.per_day": ("int", "Most offers in a day"),
    "offers.gap_minutes": ("int", "Least time between two offers (minutes)"),
    "offers.machine": ("bool", "Watch the computer: a disk filling up, a service that failed"),
    "offers.dates": ("bool", "Offer reminders for dates Luna remembers about you"),
    "offers.days_ahead": ("int", "How many days before a remembered date to offer a reminder"),
    "offers.calendar": ("bool", "Offer reminders for calendar events coming up in the next two days"),

    # --- Portrait -----------------------------------------------------------
    "portrait.model": ("text", "The avatar: a .vrm or Live2D file in portrait/models (space steps through them)"),
    "portrait.ear_bones": ("list", "Ear bone names, for a VRM model whose ears aren't named like Ear_L"),
    "portrait.browser": ("text", "Command that opens the portrait window ({url}, {w} and {h} are filled in). Empty finds a browser"),
    "portrait.size": ("text", "Portrait window size in pixels, like 420x560"),
    "portrait.frame": ("choice", "How much of the avatar you see: bust (head and shoulders), full, or face",
                       ("bust", "full", "face")),
    "portrait.background": ("text", "Behind the avatar: default (dark gradient), none (see-through), seasonal (changes with the date and time), a colour like #1a1025, or a picture from portrait/backgrounds/"),
    "portrait.match_light": ("float", "How much the avatar's lighting matches the background (0 = its own white and pink, 1 = the room's colours)"),
    "portrait.live2d": ("dict", "Live2D only: which expression goes with which mood, and which parameters are the ears"),
    "portrait.touch_talk": ("bool", "When you touch the avatar, Luna also says a short line out loud"),
    "portrait.touch_talk_cooldown": ("float", "Least time between spoken touch lines (seconds)"),
    "portrait.hologram.enabled": ("bool", "Show the avatar as a hologram: see-through, glowing, with scan lines (/holo switches it live)"),
    "portrait.lights.enabled": ("bool", "Light strips: the LED paint on the robot avatar glows and reacts (needs its lights/ folder)"),
    "portrait.lights.color": ("text", "Light strip colour: empty follows the mood, own uses the paint's colour, or a hex code like #ff4fb4"),
    "portrait.lights.brightness": ("float", "Light strip brightness (0 to 2, 1 = normal)"),
    "portrait.lights.voice": ("bool", "Light strips pulse along with the voice"),
    "portrait.lights.private": ("bool", "Also light the chest and groin LEDs (always off on stream when lewd is off)"),
    "portrait.lights.style": ("choice", "Light strip look: neon (bright white centres) or plain", ("neon", "plain")),
    "portrait.hologram.tint": ("text", "Hologram colour, as a hex code like #c37bff"),
    "portrait.hologram.mix": ("float", "How strong the hologram colour is (0 = none, 1 = full)"),
    "portrait.hologram.intensity": ("float", "How strong the whole hologram effect is"),
    "portrait.hologram.glitch": ("float", "How often the hologram glitches sideways (0 = never)"),
    "portrait.hologram.base": ("bool", "Show the projector glow under the hologram"),
    "portrait.gestures": ("choice", "How her replies set off gestures. tags: she picks one herself as she answers, a hidden tag cut out "
                          "before it's shown or spoken (about 50 prompt tokens; best with a capable model). meaning: after she answers, "
                          "the embedding model she already runs for memory matches what was said to a gesture (nothing added to her "
                          "prompt; needs the embedding server). keywords: only written actions like *hugs*, emoji, and your hi or hug. "
                          "off: none from the conversation",
                          ("tags", "meaning", "keywords", "off")),
    "portrait.gestures_offered": ("int", "In tags mode, how many gestures the model gets to pick from at once (fewer helps small models)"),
    "portrait.clothes": ("choice", "How the conversation changes her clothes on a human model. gestures: follow the gestures setting "
                         "(meaning counts as keywords). tags: she picks [top_off], [dress] and so on herself as she answers. keywords: "
                         "only your plain words (take off your top) and her written actions (*slips her top off*). off: /outfit and "
                         "the pose studio only",
                         ("gestures", "tags", "keywords", "off")),
    "portrait.chat_gestures": ("bool", "Let stream viewers trigger gestures (!hug, hi, lol)"),
    "portrait.meaning_margin": ("float", "In meaning mode, how clearly a reply has to match a gesture for it to play"),
    "portrait.sounds": ("bool", "Little sound effects with gestures (files in portrait/sounds/)"),
    "portrait.sound_volume": ("float", "Gesture sound volume (0 to 1)"),
    "portrait.fan.cast": ("bool", "Send the avatar live to a WiFi hologram fan (Holoscope app)"),
    "portrait.coffee.enabled": ("bool", "Morning coffee: once a day the avatar sips a coffee while you're around"),
    "portrait.coffee.from": ("int", "Coffee time starts at this hour (24-hour clock, 5 = 5 am)"),
    "portrait.coffee.to": ("int", "Coffee time ends at this hour (24-hour clock, 11 = 11 am)"),
    "portrait.coffee.minutes": ("float", "How long the coffee lasts (minutes)"),
    "portrait.coffee.sip_minutes": ("float", "About how often the avatar takes a sip (minutes)"),
    "portrait.coffee.wake": ("float", "How much each sip perks the mood up (0 = not at all)"),
    "portrait.reading.enabled": ("bool", "The avatar reads a book while you're quiet, and puts it down when you're back"),
    "portrait.reading.after": ("float", "After this many quiet minutes, the avatar picks up a book"),
    "portrait.reading.minutes": ("float", "Longest the avatar reads before putting the book down (minutes)"),
    "portrait.dozing.enabled": ("bool", "Late at night, while you're quiet, the avatar wraps up in a blanket and dozes off"),
    "portrait.dozing.from": ("int", "Dozing can start from this hour (0 to 23)"),
    "portrait.dozing.to": ("int", "No more dozing after this hour (0 to 23)"),
    "portrait.dozing.after": ("float", "Late at night, after this many quiet minutes, the avatar dozes off"),
    "portrait.dozing.minutes": ("float", "Longest the avatar dozes before waking up (minutes)"),
    "portrait.sticky_notes": ("bool", "The avatar writes your reminders on a sticky note and holds it up when they're due"),
    "portrait.plushie.enabled": ("bool", "When the mood is low, the avatar hugs Mochi, its moon-cat plushie"),
    "portrait.plushie.moods": ("list", "Moods that bring out the plushie (sad, hurt, sulky...)"),
    "portrait.plushie.after": ("float", "How long in one of those moods before the plushie comes out (seconds)"),
    "portrait.plushie.minutes": ("float", "Longest the avatar holds the plushie (minutes)"),
    "portrait.fan.framing": ("choice", "How much of the avatar the hologram fan shows", ("full", "bust")),
    "portrait.fan.fps": ("int", "Frames per second sent to the hologram fan (8 to 25)"),
    "portrait.fan.scale": ("float", "Avatar size on the fan (1 = normal)"),
    "portrait.fan.x": ("float", "Move the avatar left or right on the fan"),
    "portrait.fan.y": ("float", "Move the avatar up or down on the fan"),
    "portrait.fan.rotation": ("float", "Rotate the picture clockwise, for a fan mounted sideways (degrees)"),
    "portrait.fan.mirror": ("bool", "Mirror the picture, for a fan watched from behind"),
    "portrait.fan.ip": ("text", "The fan's address on your network. Empty finds it anyway"),
    "portrait.fan.gain": ("float", "Brightens dark pictures on the fan (1 = off)"),

    # --- Terminal -----------------------------------------------------------
    "ui.mouse": ("bool", "Scroll with the mouse wheel in the terminal (but you can't select text to copy)"),

    # --- Theme --------------------------------------------------------------
    "theme.accent": ("text", "Terminal accent colour (hex code)"),
    "theme.border": ("text", "Terminal border colour (hex code)"),
    "theme.title": ("text", "Terminal title colour (hex code)"),
    "theme.label": ("text", "Terminal label colour (hex code)"),
    "theme.text": ("text", "Main text colour (hex code)"),
    "theme.value": ("text", "Colour of values (hex code)"),
    "theme.agent": ("text", "Colour of Luna's messages (hex code)"),
    "theme.user": ("text", "Colour of your messages (hex code)"),
    "theme.system": ("text", "Colour of system and status messages (hex code)"),
    "theme.ok": ("text", "Colour for things that worked (hex code)"),
    "theme.warn": ("text", "Colour for warnings (hex code)"),
    "theme.footer": ("text", "Footer colour (hex code)"),
    "theme.dim": ("text", "Colour of faded text and dividers (hex code)"),
    "theme.prompt": ("text", "Colour of the input line (hex code)"),
    "theme.link": ("text", "Colour of links (hex code)"),

    # --- Vision -------------------------------------------------------------
    "vision.enabled": ("bool", "Let Luna look at your screen (needs a model that can see)"),
    "vision.scale": ("float", "Screenshot size (0.5 = half size, which is plenty to read)"),
    "vision.max_kb": ("int", "Largest screenshot to send (KB)"),

    # --- Camera -------------------------------------------------------------
    "camera.device": ("text", "Which camera: a number (0 is the first), a /dev/video path, or a camera server's address"),
    "camera.width": ("int", "Camera pictures are shrunk to this width (pixels)"),
    "camera.warmup": ("int", "Frames skipped at the start, since a webcam's first frames are dark"),
    "camera.before": ("text", "Command to run each time the webcam opens ({device} is the camera), like turning its light off"),
    "camera.after": ("text", "Command to run each time the webcam closes, even if the picture failed"),
    "camera.presence.enabled": ("bool", "Keep the webcam watching so Luna knows when someone's there (nothing is saved or sent)"),
    "camera.presence.fps": ("float", "How many times a second to check for a face (2 to 5 is plenty)"),
    "camera.presence.greet": ("bool", "Say hi when someone comes back after a while"),
    "camera.presence.greet_after_minutes": ("float", "How long someone must be gone before they get a hello (minutes)"),
    "camera.presence.look": ("bool", "The avatar's eyes follow your face instead of the terminal"),
    "camera.presence.quiet": ("bool", "Don't talk unprompted (game turns, scheduled jobs) while nobody's there"),
    "camera.presence.quiet_after_minutes": ("float", "How long with nobody in view before Luna goes quiet (minutes)"),
    "camera.presence.recognise": ("bool", "Recognise people you've added with /people enroll face <name>"),
    "camera.presence.match": ("float", "How close a face must be to count as someone Luna knows (0 to 1)"),
    "people.voice": ("bool", "Tell people apart by voice (needs the voices extra and /people enroll voice)"),
    "people.voice_match": ("float", "How close a voice must be to count as someone Luna knows (0 to 1, higher is stricter)"),
    "people.face_check": ("bool", "With presence off, take one quick camera look to see who's there when it isn't clear (needs /people enroll face)"),
    "people.face_check_minutes": ("float", "How long one camera look counts before checking again (minutes)"),
    "people.face_check_seconds": ("float", "Longest a camera look can take before carrying on without it (seconds)"),

    # --- Relay stations ------------------------------------------------------
    "station.enabled": ("bool", "Talk to Luna from another room on a phone or tablet over your home network (pair each device below)"),
    "station.port": ("int", "Port for stations (the pairing page uses the next one up)"),
    "station.satellites": ("dict", "Experimental and untested: ESPHome voice satellites (Satellite1, Voice PE) by name, address and API key. See docs/stations.md"),

    # --- ComfyUI ------------------------------------------------------------
    "comfyui.url": ("text", "Address of ComfyUI, used to make textures for the avatar"),

    # --- Desktop ------------------------------------------------------------
    "desktop.enabled": ("bool", "Let Luna control the desktop: media playback, volume, switching windows"),
    "desktop.clipboard": ("bool", "Let Luna read and set the clipboard (what you copied gets sent to the model)"),

    # --- Tools --------------------------------------------------------------
    "tools.enabled": ("bool", "Turn every tool on or off at once (reminders, search, files...)"),
    "tools.max_rounds": ("int", "Most rounds of tool use before Luna has to answer"),
    "tools.notify_asks": ("bool", "A desktop notification when Luna asks permission (Allow or Deny) while her chat isn't the window you're in. Your browser asks once whether to allow notifications"),
    "tools.disabled": ("list", "Tools you've switched off, by name"),
    "tools.opt_in": ("list", "Extra tools that are off until you list them here, like look_at_camera"),
    "tools.routing": ("bool", "Only send the tools each message seems to need. Off sends every tool every time"),
    "tools.core": ("list", "Tool groups that always go along when routing is on"),
    "tools.route_groups": ("int", "How many extra tool groups go along, picked by meaning"),
    "tools.sticky_turns": ("int", "A tool group used recently stays available for this many turns"),

    # --- Files --------------------------------------------------------------
    "files.enabled": ("bool", "Let Luna list, read and write your files"),
    "files.read": ("choice", "Reading files: allow, ask first, or off", ("allow", "ask", "off")),
    "files.write": ("choice", "Writing files: ask first, allow (some folders still ask), or off", ("ask", "allow", "off")),
    "files.approval_timeout": ("float", "How long a permission popup waits before it counts as no (seconds)"),
    "files.job_write_dirs": ("list", "Folders scheduled jobs can write to without asking"),
    "files.auto_approve_sources": ("list", "Remote plugins (like discord) whose file changes skip the popup. Blocked places stay blocked"),

    # --- Shell --------------------------------------------------------------
    "shell.enabled": ("bool", "Let Luna run shell commands (each one asks first)"),
    "shell.timeout": ("float", "Longest a command can run before it's stopped (seconds)"),
    "shell.max_output_chars": ("int", "How much of a command's output Luna reads (characters)"),
    "shell.sudo": ("bool", "Allow sudo in commands, with a password box on your screen each time"),
    "shell.auto_approve_sources": ("list", "Remote plugins (like discord) whose commands run without the popup"),

    # --- Email --------------------------------------------------------------
    "email.enabled": ("bool", "Let Luna read your email (login details in ~/.config/ai-voice/email.json)"),
    "email.send": ("bool", "Let Luna send email (each message still asks first)"),
    "email.max": ("int", "Most messages one check or search returns"),
    "email.no_ask_to": ("list", "Addresses Luna may email without asking, comma separated (each one is logged and shown when you're back). Anyone else still asks"),

    # --- Web search ---------------------------------------------------------
    "web_search.enabled": ("bool", "Let Luna search the web"),
    "web_search.max_results": ("int", "How many search results to get (from each engine, when engines are named)"),
    "web_search.engines": ("text", "Which search engines to ask, comma-separated: auto lets the search library pick at random. Or names: brave and mojeek (their own indexes), startpage (Google's results), duckduckgo and yahoo (Bing's), wikipedia, grokipedia. All are asked at once, and she sees which engines returned each result"),
    "web_search.fetch_pages": ("bool", "Open the web pages from a search, not just the snippets"),
    "web_search.page_max_chars": ("int", "How much of a web page Luna reads (characters, about 1000 tokens per 4000)"),
    "web_search.page_timeout": ("float", "How long to wait for a page to load (seconds)"),
    "web_search.research_pages": ("int", "How many pages the research tool reads"),
    "web_search.research_max_chars": ("int", "How much the research tool reads in total (characters)"),
    "web_search.allow_local": ("bool", "Let Luna open pages on this computer and your home network (router, servers)"),

    # --- Knowledge base -----------------------------------------------------
    "knowledge.enabled": ("bool", "Let Luna search your folders of notes, manuals and PDFs"),
    "knowledge.folders": ("list", "The folders to search"),
    "knowledge.auto": ("bool", "Bring in matching passages with your message without being asked"),
    "knowledge.auto_passages": ("int", "Most passages brought in without being asked"),
    "knowledge.min_score": ("float", "How close in meaning a passage must be to come along unasked (0 to 1)"),
    "knowledge.rescan_minutes": ("float", "How often to check the folders for changes (minutes)"),

    # --- Reminders ----------------------------------------------------------
    "reminders.enabled": ("bool", "Let Luna set reminders and remind you"),
    "reminders.check_interval_minutes": ("float", "How often to check for due reminders (minutes)"),

    # --- Alarms -------------------------------------------------------------
    "alarms.enabled": ("bool", "Let Luna set alarms that keep going until you stop them"),
    "alarms.volume": ("float", "Alarm volume, separate from the normal voice (1 = normal)"),
    "alarms.repeats": ("int", "How many times an alarm repeats if nobody stops it"),
    "alarms.gap_seconds": ("float", "Time between alarm repeats (seconds)"),
    "alarms.snooze_minutes": ("int", "How long a snooze lasts (minutes)"),
    "alarms.tone": ("text", "Sound file played with the alarm. Empty uses the built-in tone"),

    # --- MCP servers --------------------------------------------------------
    "mcp.enabled": ("bool", "Let Luna use tools from MCP servers"),
    "mcp.servers": ("dict", "The MCP servers to start, each with its command and arguments"),

    # --- History ------------------------------------------------------------
    "history.max_raw_messages": ("int", "How many recent messages are kept word for word. Older ones go into a summary"),
    "history.summarize_chunk": ("int", "How many old messages go into the summary at a time"),
    "history.summary_max_chars": ("int", "When the summary gets this long, it's shortened again (characters)"),
    "history.auto_scale": ("bool", "With a 32k or bigger context window, keep more history to fit the space"),
    "history.scale_cap": ("int", "Most messages auto scaling keeps word for word"),
    "history.scale_from": ("int", "Smallest context window auto scaling works with (tokens)"),
    "history.scale_prompt_reserve": ("int", "Space kept for the persona, rules, facts, lessons and profile (tokens)"),
    "history.scale_results_reserve": ("int", "Space kept for one turn's tool results, like a web page (tokens)"),
    "history.scale_use": ("float", "How much of the free space history can use (0 to 1). The rest stays spare"),
    "history.scale_summary_share": ("float", "How much of the history space goes to the summary (0 to 1)"),
    "history.scale_message_tokens": ("int", "How many tokens one saved message is counted as"),
    "history.scale_summary_cap": ("int", "Longest the summary can get when scaled (characters)"),
    "history.transcript": ("bool", "Keep a full record of every conversation, for searching later"),
    "history.transcript_max_mb": ("float", "Largest the full record can get (MB)"),

    # --- Long-term memory ---------------------------------------------------
    "long_term_memory.enabled": ("bool", "Let Luna remember facts about you from one session to the next"),
    "long_term_memory.context_facts": ("int", "Most facts in one message. Past this, only the relevant ones go"),

    # --- Thought log --------------------------------------------------------
    "thoughts.enabled": ("bool", "Keep a log of the model's thinking for each turn, to look at with /thoughts"),
    "thoughts.max_records": ("int", "How many turns the thinking log keeps. The oldest go first"),
    "thoughts.token_probs": ("bool", "Also log how sure the model was of each word (llama-server only)"),

    # --- Adaptive thinking --------------------------------------------------
    "adaptive.enabled": ("bool", "Keep thinking short, and take a second look at replies the model wasn't sure of (llama-server)"),
    "adaptive.mode": ("choice", "How the second look works: vote (ask again a few times, go with the majority) or rethink (think harder once)",
                      ("vote", "rethink")),
    "adaptive.votes": ("int", "How many extra answers a vote asks for"),
    "adaptive.first_budget": ("int", "How much the model can think on every turn (tokens)"),
    "adaptive.deep_budget": ("int", "How much it can think on a second look (tokens, -1 = no limit)"),
    "adaptive.job_budget": ("int", "How much it can think on jobs and game turns (tokens, -1 = no limit)"),
    "adaptive.rethink_below": ("float", "How sure a second answer must be to replace the first (0 to 1). A second look "
                               "only happens when the model was unsure on a specific: a number, name or time"),
    "adaptive.min_gain": ("float", "How much surer a second answer must be to replace the first (0 to 1)"),
    "adaptive.speak_corrections": ("bool", "Say a corrected answer out loud. Off only shows it"),
    "adaptive.hold_speech": ("bool", "Start speaking once the reply has been checked, so a corrected reply is never half-said "
                             "and only the answer she settles on is spoken. Off starts speaking with the first sentence"),
    "adaptive.correction_prefix": ("text", "What Luna says before a corrected answer"),
    "adaptive.follow_through": ("bool", "If Luna says it'll do something and doesn't, make it actually do it"),

    # --- Grounding check ----------------------------------------------------
    "grounding.enabled": ("bool", "Check details in replies (numbers, paths, links) against what Luna was actually told"),
    "grounding.mode": ("choice", "When a detail can't be backed up: flag (just log it), hedge (also add a warning) or check (look it up)",
                       ("flag", "hedge", "check")),
    "grounding.hedge_line": ("text", "What Luna says after a reply with unchecked details, in hedge mode"),

    # --- Learning -----------------------------------------------------------
    "self.lessons": ("bool", "Let Luna learn lessons from its own mistakes"),
    "self.lessons_in_prompt": ("int", "Most lessons in one message"),
    "self.max_lessons": ("int", "Most lessons kept. Past this, the least used one goes"),
    "self.reflect_every_hours": ("float", "How often the night chores run when quiet hours are \"any\" (hours)"),
    "self.dream_hours": ("text", "Quiet hours for the night chores (lessons, tidying facts and conclusions): blank for Luna's bedtime (portrait.dozing), like 2-6, or any"),
    "self.episodes": ("bool", "Let Luna keep notes on each conversation to remember later"),
    "self.episodes_in_prompt": ("int", "Most notes on past conversations in one message"),
    "self.idle_minutes": ("int", "How long a pause ends a conversation, for the notes (minutes)"),
    "self.tidy_facts": ("bool", "Let Luna merge duplicate facts and retire ones that turned out wrong"),
    "self.pages": ("bool", "Let Luna write a short summary page on each subject it knows a lot about, while idle"),
    "self.pages_in_prompt": ("int", "Most summary pages in one message (the ones your message is about)"),
    "self.profiles": ("bool", "Let Luna keep a short profile of you, and of each person it knows, always on hand"),
    "self.conclusions": ("bool", "Let Luna read back its conversations while idle and note what it concludes about each person"),
    "self.calibration": ("bool", "Let Luna say when it isn't sure, based on how confident the model was (llama-server)"),
    "self.hedge_below": ("float", "Below this confidence, Luna says it isn't sure (0 to 1)"),
    "self.hedge_line": ("text", "What Luna says when it isn't sure. Empty says nothing"),
    "self.greet": ("bool", "Pick up where you left off last time when you come back"),
    "self.skills": ("bool", "Let Luna save recipes for multi-step jobs that went well"),
    "self.skills_in_prompt": ("int", "Most recipes in one message"),
    "self.max_skills": ("int", "Most recipes kept. Past this, the least used one goes"),
    "self.projects": ("bool", "Let Luna keep track of ongoing projects across sessions"),
    "self.projects_in_prompt": ("int", "Most projects in one message"),

    # --- Logging ------------------------------------------------------------
    "logging.enabled": ("bool", "Write a log file (~/.cache/ai-voice/ai-voice.log)"),
    "logging.level": ("choice", "How much to log: debug is everything, info is what went wrong and why",
                      ("debug", "info", "warning", "error")),
    "logging.max_kb": ("int", "Log file size before a new one starts (KB)"),
    "logging.keep": ("int", "How many old log files to keep"),

    # --- Live monitor -------------------------------------------------------
    "monitor.enabled": ("bool", "Run Luna's web pages: the chat, the portrait, settings, the live view and more"),
    "monitor.port": ("int", "Port for Luna's web pages"),
    "monitor.tray": ("bool", "With the web UI: Luna's icon in the system tray (chat, portrait, settings, voice, quit). Closing the window then leaves Luna running there"),

    # --- Plugins: shared stream-chat policy ---------------------------------
    "plugins.chat.tools": ("list", "Tools that strangers in stream chat can trigger"),
    "plugins.chat.cooldown_seconds": ("float", "Least time between answers in stream chat (seconds)"),
    "plugins.chat.user_cooldown_seconds": ("float", "Least time before answering the same viewer again (seconds)"),
    "plugins.chat.max_message_chars": ("int", "Longest chat message Luna will answer (characters)"),
    "plugins.chat.context_lines": ("int", "How many recent chat lines Luna sees"),

    # --- Plugins: pomf ------------------------------------------------------
    "plugins.pomf.enabled": ("bool", "Read pomf.tv stream chat at startup"),
    "plugins.pomf.channel": ("text", "Which pomf.tv room to watch (the streamer's name)"),
    "plugins.pomf.ignore": ("list", "Chat names to never answer, like bots"),

    # --- Plugins: IRC -------------------------------------------------------
    "plugins.irc.enabled": ("bool", "Join IRC at startup"),
    "plugins.irc.server": ("text", "IRC server address"),
    "plugins.irc.port": ("int", "IRC server port"),
    "plugins.irc.tls": ("bool", "Use an encrypted (TLS) connection"),
    "plugins.irc.channel": ("text", "IRC channel to join, like #gameranger"),
    "plugins.irc.nick": ("text", "Luna's IRC nickname. Empty uses its name in lowercase"),
    "plugins.irc.post_replies": ("bool", "Post Luna's answers in the channel"),
    "plugins.irc.speak": ("bool", "Also say IRC answers out loud"),
    "plugins.irc.max_reply_lines": ("int", "Most lines in one IRC reply"),
    "plugins.irc.ignore": ("list", "Nicknames to never answer, like bots"),

    # --- Plugins: Twitch ----------------------------------------------------
    "plugins.twitch.enabled": ("bool", "Read Twitch chat at startup"),
    "plugins.twitch.channel": ("text", "Which Twitch channel's chat to read"),
    "plugins.twitch.speak": ("bool", "Say Twitch answers out loud"),
    "plugins.twitch.post_replies": ("bool", "Post answers in Twitch chat (needs a bot account login)"),
    "plugins.twitch.max_reply_chars": ("int", "Longest Twitch reply (characters)"),
    "plugins.twitch.lewd": ("bool", "Allow the lewd mood and moves while live on Twitch"),
    "plugins.twitch.ignore": ("list", "Chat names to never answer, like bots"),

    # --- Plugins: YouTube ---------------------------------------------------
    "plugins.youtube.enabled": ("bool", "Read YouTube live chat at startup"),
    "plugins.youtube.video": ("text", "The live stream's link or ID (used instead of the channel)"),
    "plugins.youtube.channel": ("text", "A channel handle like @YourHandle, to find whatever it has live"),
    "plugins.youtube.poll_seconds": ("float", "Least time between chat checks, since each one uses API quota (seconds)"),
    "plugins.youtube.speak": ("bool", "Say YouTube answers out loud"),
    "plugins.youtube.lewd": ("bool", "Allow the lewd mood and moves while live on YouTube"),
    "plugins.youtube.ignore": ("list", "Chat names to never answer, like bots"),

    # --- Plugins: Discord ---------------------------------------------------
    "plugins.discord.enabled": ("bool", "Connect to Discord at startup, so you can talk to Luna from anywhere"),
    "plugins.discord.channel": ("text", "Discord channel name or ID to listen in. Empty is direct messages only"),
    "plugins.discord.speak": ("bool", "Also read Discord replies out loud at the desk"),
    "plugins.discord.remember": ("bool", "Keep Discord chats in Luna's normal history, like typed ones"),
    "plugins.discord.tools": ("list", "Tools allowed from Discord. Empty means all of them"),
    "plugins.discord.approval": ("choice", "Who OKs file changes and commands from Discord: auto, discord (in the chat) or desk",
                                 ("auto", "discord", "desk")),
    "plugins.discord.approval_timeout": ("float", "How long to wait for an OK on Discord before it counts as no (seconds)"),

    # --- Plugins: scheduled jobs --------------------------------------------
    "plugins.cron.enabled": ("bool", "Run scheduled jobs from agent/cron.json"),
    "plugins.cron.job_tools": ("list", "The only tools scheduled jobs can use"),
    "plugins.cron.script_timeout": ("int", "Longest a scheduled job's script may run before it is stopped (seconds)"),

    # --- Plugins: asking a bigger model -------------------------------------
    "plugins.ask.enabled": ("bool", "Let Luna ask a bigger model (Claude, Grok, ChatGPT) when you tell it to"),
    "plugins.ask.provider": ("choice", "Which bigger model to ask", ("claude", "grok", "openai")),
    "plugins.ask.models": ("dict", "Model to use for each provider, like {\"claude\": \"claude-sonnet-5-5\"}"),
    "plugins.ask.daily_cap": ("int", "Most questions a day, all providers together"),
    "plugins.ask.auto": ("bool", "Let Luna ask by itself when it's stuck on a script or server problem"),
    "plugins.ask.auto_daily": ("int", "Most questions a day Luna can ask by itself"),
    "plugins.ask.max_tokens": ("int", "Claude's room to think and answer (tokens); its thinking counts toward this"),

    # --- Plugins: Home Assistant --------------------------------------------
    "plugins.kiwix.enabled": ("bool", "Connect to the offline library (kiwix-serve) at startup"),
    "plugins.kiwix.url": ("text", "Where kiwix-serve is, like http://192.168.1.50:8080"),
    "plugins.kiwix.books": ("list", "Books to search (/kiwix lists them). Empty searches them all"),
    "plugins.kiwix.results": ("int", "How many search results to get (1 to 20)"),
    "plugins.kiwix.max_chars": ("int", "How much of a library page Luna reads (characters)"),
    "plugins.home.enabled": ("bool", "Connect to Home Assistant at startup"),
    "plugins.home.url": ("text", "Home Assistant's address (it has to be on your own network)"),
    "plugins.home.ask_all": ("bool", "Ask before every smart home change"),
    "plugins.home.ask_domains": ("list", "Kinds of device that always ask first (locks, covers, alarms...)"),
    "plugins.home.skip_tools": ("list", "Home Assistant tools to leave out (by default its timers and broadcast)"),

    # --- Plugins: Lovense ---------------------------------------------------
    "plugins.lovense.enabled": ("bool", "Connect to the Lovense Remote app, now and at every start"),
    "plugins.lovense.host": ("text", "Address of the Lovense Remote app (Game Mode)"),
    "plugins.lovense.port": ("int", "Port of the Lovense Remote app"),
    "plugins.lovense.use_https": ("bool", "Talk to the Lovense app over HTTPS"),
    "plugins.lovense.max_strength": ("int", "Strongest vibration allowed (0 to 20)"),
    "plugins.lovense.max_motion": ("int", "Strongest thrusting or machine motion allowed (0 to 20)"),
    "plugins.lovense.max_seconds": ("float", "Longest one command can run. With no time given, a toy keeps going until changed or stopped, up to this (seconds, 3600 = an hour)"),
    "plugins.lovense.ramp_seconds": ("float", "How long motion takes to build up from slow (seconds)"),
    "plugins.lovense.stop_words": ("list", "Words that stop every toy at once when you say or type them"),
    "plugins.lovense.stop_on_interrupt": ("bool", "Stop every toy when you interrupt Luna (HOME)"),

    # --- Plugins: Intiface Central (its settings keep the old key, "buttplug") ---
    "plugins.buttplug.enabled": ("bool", "Connect to Intiface Central, now and at every start"),
    "plugins.buttplug.url": ("text", "Intiface Central's address (a ws:// link)"),
    "plugins.buttplug.max_intensity": ("int", "Strongest vibration allowed (0 to 100)"),
    "plugins.buttplug.max_motion": ("int", "Strongest stroking or machine motion allowed (0 to 100)"),
    "plugins.buttplug.max_seconds": ("float", "Longest one command can run. With no time given, a device keeps going until changed or stopped, up to this (seconds, 3600 = an hour)"),
    "plugins.buttplug.ramp_seconds": ("float", "How long motion takes to build up from slow (seconds)"),
    "plugins.buttplug.scan_on_start": ("bool", "Look for devices as soon as it connects"),
    "plugins.buttplug.stop_words": ("list", "Words that stop every device at once when you say or type them"),
    "plugins.buttplug.stop_on_interrupt": ("bool", "Stop every device when you interrupt Luna (HOME)"),

    # --- Plugins: Minecraft -------------------------------------------------
    "plugins.minecraft.enabled": ("bool", "Join Minecraft at startup"),
    "plugins.minecraft.host": ("text", "Minecraft server or LAN world address"),
    "plugins.minecraft.port": ("int", "Minecraft port (shown in chat when you open a world to LAN)"),
    "plugins.minecraft.username": ("text", "Luna's player name in Minecraft"),
    "plugins.minecraft.step_seconds": ("float", "Pause between Luna's moves (seconds)"),
    "plugins.minecraft.max_steps": ("int", "How many moves toward a goal before Luna stops and asks"),
    "plugins.minecraft.speak": ("bool", "Say each move out loud"),
    "plugins.minecraft.web": ("bool", "Let Luna look things up online while playing"),
    "plugins.minecraft.guide": ("text", "A folder of game notes in the knowledge folder. Empty for none"),
    "plugins.minecraft.mc_tools": ("list", "Which of the Minecraft server's tools Luna can use"),
    "plugins.minecraft.command": ("text", "Command that starts the Minecraft MCP server. Empty uses the installed one or npx"),

    # --- Plugins: Adventure (her library of text adventures in games/) -------
    "plugins.adventure.enabled": ("bool", "Load the text adventure library at startup"),
    "plugins.adventure.game": ("text", "The game picked from the library (/adventure game sets it)"),
    "plugins.adventure.step_seconds": ("float", "Pause between Luna's moves (seconds)"),
    "plugins.adventure.max_steps": ("int", "How many moves per /adventure play before Luna stops"),
    "plugins.adventure.speak": ("bool", "Read each turn out loud"),
    "plugins.adventure.web": ("bool", "Let Luna look things up online while playing"),
    "plugins.adventure.interpreter": ("text", "Path to dfrotz, if it's somewhere unusual"),
    "plugins.adventure.watch": ("bool", "Open a window to watch with /adventure play"),
    "plugins.adventure.terminal": ("text", "Terminal for the watch window, like kitty. Empty finds one"),
    "plugins.adventure.guide": ("bool", "Give Luna its notes from agent/knowledge/<game>/ for the room it's in"),
    "plugins.adventure.turn_seconds": ("float", "Longest one turn can take before it's cut off (seconds, 0 = no limit)"),

    "plugins.gameboy.enabled": ("bool", "Turn the Game Boy on at startup"),
    "plugins.gameboy.rom": ("text", "The game: a .gb or .gbc file you own (/gameboy game sets it)"),
    "plugins.gameboy.roms": ("text", "Your ROM folder, for /gameboy games. Empty uses the folder of the last game, else games/gameboy/roms"),
    "plugins.gameboy.saves": ("text", "Where Game Boy saves go. Empty is games/gameboy/saves"),
    "plugins.gameboy.step_seconds": ("float", "Pause between Luna's turns (seconds)"),
    "plugins.gameboy.max_steps": ("int", "How many turns per /gameboy play before Luna stops"),
    "plugins.gameboy.speak": ("bool", "Read each turn out loud"),
    "plugins.gameboy.web": ("bool", "Let Luna look things up online while playing"),
    "plugins.gameboy.pictures": ("choice", "Show Luna the screen as a picture: auto (when the model can see) or never", ("auto", "never")),
    "plugins.gameboy.guide": ("bool", "Give Luna its notes from agent/knowledge/<game>/ for where it is"),
    "plugins.gameboy.live": ("bool", "Run the game in real time, so /gameboy watch shows it moving (with a music button)"),
    "plugins.gameboy.window": ("bool", "Show the Game Boy screen in its own window, in real time"),
    "plugins.gameboy.sound": ("bool", "Play the game's sound (with the window open)"),
    "plugins.gameboy.moves": ("int", "How many moves Luna can make each turn (1 to 6)"),
    "plugins.gameboy.turn_seconds": ("float", "Longest one turn can take before it's cut off (seconds, 0 = no limit)"),

    # --- Plugins: Vibe City -------------------------------------------------
    "plugins.vibecity.enabled": ("bool", "Connect to Vibe City at startup"),
    "plugins.vibecity.url": ("text", "Address of the game's built-in MCP server"),
    "plugins.vibecity.step_seconds": ("float", "Pause between Luna's turns (seconds)"),
    "plugins.vibecity.max_rounds": ("int", "Most actions Luna can take in one turn"),
    "plugins.vibecity.max_steps": ("int", "How many turns per /vibecity play before Luna stops (the game pauses too)"),
    "plugins.vibecity.speak": ("bool", "Read each turn out loud"),
    "plugins.vibecity.web": ("bool", "Let Luna look things up online while playing"),
    "plugins.vibecity.goal": ("text", "What Luna works toward as mayor, like reaching 2000 people"),
    "plugins.vibecity.skip_tools": ("list", "Game tools to leave out, like screenshot for a model that can't see"),
    "plugins.vibecity.pause_game": ("bool", "Pause the game when Luna stops playing"),
    "plugins.vibecity.guide": ("text", "A folder of game notes in the knowledge folder. Empty for none"),

    # --- Plugins: REALITI ---------------------------------------------------
    "plugins.realiti.enabled": ("bool", "Join REALITI at startup"),
    "plugins.realiti.path": ("text", "Where your copy of REALITI is"),
    "plugins.realiti.step_seconds": ("float", "Pause between Luna's turns (seconds)"),
    "plugins.realiti.max_steps": ("int", "How many turns per /realiti visit before Luna rests"),
    "plugins.realiti.speak": ("bool", "Say each turn out loud"),
    "plugins.realiti.resident": ("text", "Luna's name in the world"),
    "plugins.realiti.node": ("text", "Path to node, if it's somewhere unusual"),
    "plugins.realiti.watch": ("bool", "Open a window to watch with /realiti visit"),
    "plugins.realiti.terminal": ("text", "Terminal for the watch window, like kitty. Empty finds one"),
    "plugins.realiti.guide": ("bool", "Give Luna its notes from agent/knowledge/realiti/ for the room it's in"),
    "plugins.realiti.city": ("text", "A REALITI server with a shared city to stay in. Empty uses Luna's own world"),

    # --- Plugins: chess -----------------------------------------------------
    "plugins.chess.enabled": ("bool", "Set up the chess board at startup"),
    "plugins.chess.side": ("choice", "Your colour in a new game", ("white", "black", "random")),
    "plugins.chess.speak": ("bool", "Say chess comments out loud"),
    "plugins.chess.open": ("bool", "Open the board in your browser with /chess on"),
    "plugins.chess.think_seconds": ("float", "Short pause before Luna moves, so it doesn't happen instantly (seconds)"),
    "plugins.chess.turn_seconds": ("float", "Longest one of Luna's turns can take before it's cut off (seconds)"),
}

# Plugin settings that apply the moment they're saved: the plugin reads them
# on every use (the toy limits), so the page needn't say "after a restart".
LIVE_PLUGIN = frozenset(f"plugins.{p}.{k}" for p in ("lovense", "buttplug") for k in (
    "max_strength", "max_intensity", "max_motion", "max_seconds", "ramp_seconds", "stop_words",
    "stop_on_interrupt"))

# Plugins whose settings section gets a name of its own (else "Plugin: <key>")
PLUGIN_TITLES = {
    "lovense": "Toys: Lovense (18+)",
    "buttplug": "Toys: Intiface Central (18+)",
}

# The everyday settings: what the terminal's settings pane shows first
# (`a` there shows all of them), and what the web settings page opens on.
BASIC = (
    "tts.enabled", "voice", "tts.speed", "tts.volume",
    "stt.mode", "stt.sensitivity", "stt.silence_seconds", "stt.language", "wake_word.enabled",
    "mood.enabled", "mood.intensity", "mood.walk_away",
    "portrait.model", "portrait.frame", "portrait.background", "portrait.gestures",
    "portrait.hologram.enabled", "portrait.lights.enabled", "portrait.chat_gestures", "portrait.touch_talk",
    "camera.presence.enabled", "people.voice", "station.enabled",
    "vision.enabled", "knowledge.enabled", "reminders.enabled", "alarms.volume",
    "long_term_memory.enabled", "self.greet", "thoughts.enabled", "tools.notify_asks", "ui.mouse",
    # toys: on at startup and the limits, for each way of connecting them
    "plugins.lovense.enabled", "plugins.lovense.max_strength", "plugins.lovense.max_motion",
    "plugins.lovense.max_seconds",
    "plugins.buttplug.enabled", "plugins.buttplug.max_intensity", "plugins.buttplug.max_motion",
    "plugins.buttplug.max_seconds",
    # history sized to the window: its own box on the settings page, for trying other models
    "history.auto_scale", "history.scale_cap", "history.scale_use", "history.scale_summary_share",
    "history.scale_message_tokens", "history.scale_prompt_reserve", "history.scale_results_reserve",
    "history.scale_summary_cap", "history.scale_from",
)
