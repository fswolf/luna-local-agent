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
SECTIONS = {
    "name": "Name",
    "voice": "Voice",
    "tts": "Speaking",
    "stt": "Listening",
    "wake_word": "Wake word",
    "generation": "Replies",
    "llm": "Model server",
    "mood": "Mood",
    "situation": "Situation",
    "portrait": "Portrait",
    "ui": "Terminal",
    "theme": "Theme",
    "vision": "Vision",
    "camera": "Camera",
    "people": "People",
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
    "name": ("text", "Her name, used only when agent/agent.json doesn't give one"),

    # --- Voice --------------------------------------------------------------
    "voice": ("text", "Which voice she speaks with, by the speech server's name for it (e.g. af_bella), or a blend"),

    # --- Speaking -----------------------------------------------------------
    "tts.url": ("text", "Address of the speech server (kokoro-reader) that turns her words into sound"),
    "tts.speed": ("float", "How fast she talks: 1.0 is normal, higher is faster"),
    "tts.volume": ("float", "How loud her voice is: 1.0 is normal"),
    "tts.pitch": ("float", "Voice pitch shift in semitones: positive sounds higher and younger, negative lower and older"),
    "tts.player": ("choice", "How her voice reaches the speakers: auto picks afplay on macOS and PortAudio elsewhere",
                   ("auto", "afplay", "portaudio")),
    "tts.strip_tilde": ("bool", "Drop the ~ in words like \"Mrrp~\" before speaking, so it isn't read out as \"tilde\""),

    # --- Listening ----------------------------------------------------------
    "stt.mode": ("choice", "How listening starts and stops: auto (HOME starts, silence ends), manual (HOME starts and stops), open (hands-free)",
                 ("auto", "manual", "open")),
    "stt.vad": ("choice", "What decides you're talking: silero (a speech model), energy (loudness only), auto (silero if available)",
                ("auto", "silero", "energy")),
    "stt.vad_threshold": ("float", "How sure the speech detector must be that it hears speech, 0-1: lower picks up sooner"),
    "stt.model": ("text", "Whisper model size for speech-to-text (e.g. small); bigger is more accurate but slower"),
    "stt.language": ("text", "Language you speak, as a code like en; empty lets Whisper guess (unreliable on short clips)"),
    "stt.sensitivity": ("float", "Mic sensitivity: above 1 triggers more easily on a quiet mic, below 1 less in a noisy room"),
    "stt.silence_seconds": ("float", "Seconds of silence after you speak before she stops recording and listens"),
    "stt.max_seconds": ("float", "Longest single recording, in seconds"),
    "stt.manual_max_seconds": ("float", "Longest recording in manual mode, in seconds, where nothing else stops it"),
    "stt.no_speech_timeout": ("float", "Seconds to wait for you to start talking before giving up (auto mode only)"),
    "stt.settle_seconds": ("float", "Pause in seconds after she speaks before the mic re-arms in open mode"),
    "stt.barge_in": ("bool", "Let you interrupt her by talking while she speaks (needs the silero detector)"),
    "stt.barge_in_seconds": ("float", "Seconds you must keep talking before she stops for you"),
    "stt.barge_in_margin": ("float", "How much louder than her own voice at the mic you must be to interrupt: raise on speakers"),
    "stt.barge_in_boost": ("float", "Added to the speech threshold while she's talking, so her own voice doesn't count as you"),

    # --- Wake word ----------------------------------------------------------
    "wake_word.enabled": ("bool", "Listen for a wake word instead of pressing HOME, in open mode"),
    "wake_word.model": ("text", "Wake word: an openWakeWord name (hey_jarvis, alexa...) or the path to one you trained"),
    "wake_word.threshold": ("float", "How sure it must be it heard the wake word, 0-1: raise if it fires at the TV"),
    "wake_word.follow_up_seconds": ("float", "Seconds she keeps listening after answering, so a follow-up needs no wake word"),
    "wake_word.cooldown_seconds": ("float", "Seconds she ignores the wake word right after hearing it, so it isn't heard twice"),

    # --- Replies ------------------------------------------------------------
    "generation.max_tokens": ("int", "Most tokens one reply may use, thinking included"),
    "generation.reasoning": ("text", "How much a reasoning model thinks, sent with each request (e.g. low)"),

    # --- Model server -------------------------------------------------------
    "llm.backend": ("choice", "Which model server to use: auto prefers llama-server when it's running, else LM Studio",
                    ("auto", "lmstudio", "llama")),
    "llm.lmstudio_url": ("text", "LM Studio's chat address"),
    "llm.llama_url": ("text", "llama-server's chat address"),
    "llm.model": ("text", "Model id to ask the server for; empty uses whatever model it has loaded"),
    "llm.api_key": ("secret", "API key for a model server that wants one (better kept in ~/.config/ai-voice/llm.json)"),
    "llm.embed_url": ("text", "Address of the embedding server used to recall facts by meaning (optional)"),
    "llm.embed_query_prefix": ("text", "Instruction put before each search sent to the embedding model; empty for most models"),
    "llm.embed_min_score": ("float", "How alike, 0-1, a fact must be by meaning to be recalled on that alone"),
    "llm.rerank_url": ("text", "Address of the reranker server that re-orders recalled matches (optional)"),
    "llm.rerank_candidates": ("int", "How many of the embedding's best matches the reranker reads"),

    # --- Mood ---------------------------------------------------------------
    "mood.enabled": ("bool", "Give her moods that colour how she talks"),
    "mood.intensity": ("float", "How far her moods swing and show: 0 almost flat, 1 as designed, 2 very emotional"),
    "mood.warmth": ("float", "The warmth she settles back to when nothing is pushing it, 0-1"),
    "mood.recovery": ("float", "How fast moods fade each turn, 0-1: 0 never fades, 1 lasts only one turn"),
    "mood.voice": ("bool", "Let her mood tint her voice a little (a sleepy Luna slightly slower and lower)"),
    "mood.affection": ("bool", "Notice when you're kind to her (one small extra model call after each turn)"),
    "mood.prompt": ("bool", "Tell her about her mood in her instructions"),
    "mood.face": ("bool", "Show her mood on the portrait's face"),
    "mood.gestures": ("bool", "Show her mood in idle moves and feeling gestures"),
    "mood.emotes": ("bool", "Show little emotes, like hearts, beside her head"),
    "mood.walk_away": ("bool", "Let her stop talking for a while after being treated with real hostility"),
    "mood.walk_away_after": ("int", "How many hostile exchanges in a row before she walks away"),
    "mood.walk_away_minutes": ("float", "How long she stays away, in minutes"),

    # --- Situation ----------------------------------------------------------
    "situation.enabled": ("bool", "Give her a few live lines each turn: your window, music, machine load, plugins, reminders"),
    "situation.window": ("bool", "Include the focused window in the situation lines"),
    "situation.music": ("bool", "Include what music is playing in the situation lines"),
    "situation.machine": ("bool", "Include CPU, RAM and GPU load in the situation lines"),
    "situation.plugins": ("bool", "Include which plugins are running in the situation lines"),
    "situation.reminders": ("bool", "Include the next reminder in the situation lines"),

    # --- Portrait -----------------------------------------------------------
    "portrait.model": ("text", "Her portrait model: a .vrm or Live2D file, relative to the portrait folder"),
    "portrait.ear_bones": ("list", "Names of the ear bones on a VRM model whose ears aren't named like Ear_L"),
    "portrait.browser": ("text", "Command to open the portrait window with ({url}, {w}, {h} filled in); empty finds one"),
    "portrait.size": ("text", "Portrait window size in pixels, width x height (e.g. 420x560)"),
    "portrait.frame": ("choice", "How much of her the camera shows: bust (head and shoulders), full, or face (close crop)",
                       ("bust", "full", "face")),
    "portrait.live2d": ("dict", "Live2D only: which model expression is which mood, and which parameters are the ears"),
    "portrait.touch_talk": ("bool", "When you touch her portrait, she also answers out loud in one short line"),
    "portrait.touch_talk_cooldown": ("float", "Seconds between spoken touch lines"),
    "portrait.hologram.enabled": ("bool", "Show her as a hologram (Live2D portrait)"),
    "portrait.hologram.tint": ("text", "Hologram colour, as a hex code like #c37bff"),
    "portrait.hologram.mix": ("float", "How much the hologram tint replaces her own colours, 0-1"),
    "portrait.hologram.intensity": ("float", "Strength of the hologram effect (?)"),
    "portrait.hologram.glitch": ("float", "How often the hologram tears sideways; 0 turns the tearing off"),
    "portrait.hologram.base": ("bool", "Show the projector glow under the hologram"),
    "portrait.gestures": ("choice", "How replies trigger gestures: tags (she picks), meaning, keywords, or off",
                          ("tags", "meaning", "keywords", "off")),
    "portrait.chat_gestures": ("bool", "Let stream viewers set off gestures (!hug, hi, lol)"),
    "portrait.meaning_margin": ("float", "In meaning mode, how clearly a gesture must beat an ordinary reply to play"),
    "portrait.sounds": ("bool", "Play little sounds with her gestures (files in portrait/sounds/)"),
    "portrait.sound_volume": ("float", "Volume of gesture sounds, 0-1"),
    "portrait.fan.cast": ("bool", "Send her live to a WiFi hologram fan (Holoscope app)"),
    "portrait.fan.framing": ("choice", "How much of her the hologram fan shows", ("full", "bust")),
    "portrait.fan.fps": ("int", "Frames per second sent to the hologram fan, 8-25"),
    "portrait.fan.scale": ("float", "Her size in the fan's circle: 1 is normal"),
    "portrait.fan.x": ("float", "Moves her sideways in the fan's circle"),
    "portrait.fan.y": ("float", "Moves her up or down in the fan's circle"),
    "portrait.fan.rotation": ("float", "Turns the picture clockwise, in degrees, for a fan hung sideways"),
    "portrait.fan.mirror": ("bool", "Mirror the picture, for a fan watched from behind"),
    "portrait.fan.ip": ("text", "The fan's address on your network; empty still finds it"),
    "portrait.fan.gain": ("float", "Brightness lift for dark pictures on the fan; 1 turns it off"),

    # --- Terminal -----------------------------------------------------------
    "ui.mouse": ("bool", "Mouse wheel scrolling in the terminal, at the cost of selecting text to copy"),

    # --- Theme --------------------------------------------------------------
    "theme.accent": ("text", "Terminal accent colour, as a hex code"),
    "theme.border": ("text", "Terminal border colour, as a hex code"),
    "theme.title": ("text", "Terminal title colour, as a hex code"),
    "theme.label": ("text", "Terminal label colour, as a hex code"),
    "theme.text": ("text", "Main text colour, as a hex code"),
    "theme.value": ("text", "Colour of values, as a hex code"),
    "theme.agent": ("text", "Colour of her lines, as a hex code"),
    "theme.user": ("text", "Colour of your lines, as a hex code"),
    "theme.system": ("text", "Colour of system and status lines, as a hex code"),
    "theme.ok": ("text", "Colour for things that went fine, as a hex code"),
    "theme.warn": ("text", "Colour for warnings, as a hex code"),
    "theme.footer": ("text", "Footer colour, as a hex code"),
    "theme.dim": ("text", "Colour of dimmed text and separators, as a hex code"),
    "theme.prompt": ("text", "Colour of the input prompt, as a hex code"),
    "theme.link": ("text", "Colour of links, as a hex code"),

    # --- Vision -------------------------------------------------------------
    "vision.enabled": ("bool", "Let her look at your screen (needs a vision model)"),
    "vision.scale": ("float", "Screenshot scale, 0-1: 0.5 is half size, plenty to read and a quarter of the bytes"),
    "vision.max_kb": ("int", "Largest screenshot she will send, in KB"),

    # --- Camera -------------------------------------------------------------
    "camera.device": ("text", "Which camera: a number (0 is the first), a /dev/video path, or a camera server's URL"),
    "camera.width": ("int", "Camera pictures are scaled down to this width, in pixels"),
    "camera.warmup": ("int", "Frames thrown away first, because a webcam's first frame is nearly black"),
    "camera.presence.enabled": ("bool", "Keep the webcam watching so she notices when someone is there (nothing is saved or sent)"),
    "camera.presence.fps": ("float", "Checks a second for a face; 2-5 is plenty and costs a few percent of one core"),
    "camera.presence.greet": ("bool", "Say hi when someone shows up after being away a while"),
    "camera.presence.greet_after_minutes": ("float", "How long someone must have been gone before she greets them, in minutes"),
    "camera.presence.look": ("bool", "Her eyes follow the face in front of the camera instead of the terminal"),
    "camera.presence.quiet": ("bool", "No unprompted talking (game turns, scheduled jobs out loud) while nobody is there"),
    "camera.presence.quiet_after_minutes": ("float", "Minutes with nobody in view before she goes quiet"),
    "camera.presence.recognise": ("bool", "Recognise faces enrolled with /people enroll face <name>"),
    "camera.presence.match": ("float", "How alike a face must be to an enrolled one to count, 0-1 (0.36 is OpenCV's advice)"),
    "people.voice": ("bool", "Tell people apart by voice on spoken turns (needs the voices extra and /people enroll voice)"),
    "people.voice_match": ("float", "How alike a voice must be to an enrolled one to count, 0-1: higher is stricter"),

    # --- ComfyUI ------------------------------------------------------------
    "comfyui.url": ("text", "Address of ComfyUI, used to make textures for her model"),

    # --- Desktop ------------------------------------------------------------
    "desktop.enabled": ("bool", "Let her act on the desktop: media playback, volume, window focus"),
    "desktop.clipboard": ("bool", "Let her read and set the clipboard (whatever you last copied reaches the model)"),

    # --- Tools --------------------------------------------------------------
    "tools.enabled": ("bool", "Let her use tools at all (reminders, search, files...); the master switch"),
    "tools.max_rounds": ("int", "How many rounds of tool calls she may make before she must answer"),
    "tools.disabled": ("list", "Tools switched off by hand, by name"),
    "tools.opt_in": ("list", "Opt-in tools switched on, like look_at_camera, which stay off until listed here"),
    "tools.routing": ("bool", "Send each turn only the tool groups it seems to need; off sends every tool every turn"),
    "tools.core": ("list", "Tool groups always sent when routing is on"),
    "tools.route_groups": ("int", "How many tool groups matched by meaning go along each turn"),
    "tools.sticky_turns": ("int", "A tool group used in this many recent turns stays available"),

    # --- Files --------------------------------------------------------------
    "files.enabled": ("bool", "Let her list, read and write your files"),
    "files.read": ("choice", "Reading files: allow, ask first, or off", ("allow", "ask", "off")),
    "files.write": ("choice", "Writing files: ask first, allow (some places still ask), or off", ("ask", "allow", "off")),
    "files.approval_timeout": ("float", "Seconds an approval popup waits; no answer counts as no"),
    "files.job_write_dirs": ("list", "Folders a scheduled job may write in without asking"),
    "files.auto_approve_sources": ("list", "Remote plugins (e.g. discord) whose file writes skip the popup; the deny list still applies"),

    # --- Shell --------------------------------------------------------------
    "shell.enabled": ("bool", "Let her run shell commands; every one asks first"),
    "shell.timeout": ("float", "Seconds a command may run before it is stopped"),
    "shell.max_output_chars": ("int", "Most characters of a command's output she gets to read"),
    "shell.sudo": ("bool", "Allow sudo in her commands, with a password box on your screen for each one"),
    "shell.auto_approve_sources": ("list", "Remote plugins (e.g. discord) whose commands run without the popup"),

    # --- Email --------------------------------------------------------------
    "email.enabled": ("bool", "Let her read your email (the login lives in ~/.config/ai-voice/email.json)"),
    "email.send": ("bool", "Let her send email; every message still asks first"),
    "email.max": ("int", "Most messages one check or search returns"),

    # --- Web search ---------------------------------------------------------
    "web_search.enabled": ("bool", "Let her search the web"),
    "web_search.max_results": ("int", "How many search results she gets"),
    "web_search.fetch_pages": ("bool", "Let her open pages she found, not just read the search snippets"),
    "web_search.page_max_chars": ("int", "Most characters of a page she reads (about 1000 tokens per 4000)"),
    "web_search.page_timeout": ("float", "Seconds to wait for a page to load"),
    "web_search.research_pages": ("int", "How many pages the research tool reads"),
    "web_search.research_max_chars": ("int", "Most characters the research tool reads in total"),
    "web_search.allow_local": ("bool", "Let her open pages on this machine and your local network (router, servers)"),

    # --- Knowledge base -----------------------------------------------------
    "knowledge.enabled": ("bool", "Let her look things up in your folders of notes, manuals and PDFs"),
    "knowledge.folders": ("list", "Folders she looks in"),
    "knowledge.auto": ("bool", "Bring matching passages along with your message without being asked"),
    "knowledge.auto_passages": ("int", "Most passages brought along unasked"),
    "knowledge.min_score": ("float", "How close by meaning, 0-1, a passage must be to come along unasked"),
    "knowledge.rescan_minutes": ("float", "How often she checks the folders for changes, in minutes"),

    # --- Reminders ----------------------------------------------------------
    "reminders.enabled": ("bool", "Let her set and give reminders"),
    "reminders.check_interval_minutes": ("float", "How often due reminders are checked, in minutes"),

    # --- Alarms -------------------------------------------------------------
    "alarms.enabled": ("bool", "Let her set alarms that repeat until dismissed"),
    "alarms.volume": ("float", "Alarm volume, separate from her normal voice: 1.0 is normal"),
    "alarms.repeats": ("int", "How many times an alarm repeats if not dismissed"),
    "alarms.gap_seconds": ("float", "Seconds between alarm repeats"),
    "alarms.snooze_minutes": ("int", "How long a snooze lasts, in minutes"),
    "alarms.tone": ("text", "Sound file played after the alarm; empty uses the built-in tone"),

    # --- MCP servers --------------------------------------------------------
    "mcp.enabled": ("bool", "Let her use tools from MCP servers"),
    "mcp.servers": ("dict", "The MCP servers to start, each with its command and arguments"),

    # --- History ------------------------------------------------------------
    "history.max_raw_messages": ("int", "Recent messages kept word for word; older ones are folded into a summary"),
    "history.summarize_chunk": ("int", "How many older messages are folded into the summary at a time"),
    "history.summary_max_chars": ("int", "Length in characters at which the running summary is compressed again"),
    "history.transcript": ("bool", "Keep a full archive of every turn, for searching past conversations"),
    "history.transcript_max_mb": ("float", "Size in MB the archive of every turn may grow to"),

    # --- Long-term memory ---------------------------------------------------
    "long_term_memory.enabled": ("bool", "Let her remember facts about you between sessions"),
    "long_term_memory.backend": ("choice", "Where facts are kept: json (capped list) or sqlite (uncapped, searchable)",
                                 ("json", "sqlite")),
    "long_term_memory.max_facts": ("int", "Most facts kept (json storage)"),
    "long_term_memory.context_facts": ("int", "Most facts put in one prompt; past this, only the relevant ones"),

    # --- Thought log --------------------------------------------------------
    "thoughts.enabled": ("bool", "Keep a log of her thinking for each turn, to review with /thoughts"),
    "thoughts.max_records": ("int", "Most turns kept in the thought log; the oldest go first"),
    "thoughts.token_probs": ("bool", "Also keep how sure she was of each word (llama-server only)"),

    # --- Adaptive thinking --------------------------------------------------
    "adaptive.enabled": ("bool", "Think on a modest budget, and take a second look at shaky replies (llama-server)"),
    "adaptive.mode": ("choice", "Second look: vote (ask again a few times, go with the majority) or rethink (think deeper once)",
                      ("vote", "rethink")),
    "adaptive.votes": ("int", "How many extra answers a vote asks for"),
    "adaptive.first_budget": ("int", "Thinking budget for every turn, in tokens"),
    "adaptive.deep_budget": ("int", "Thinking budget for the deeper second look, in tokens; -1 is no limit"),
    "adaptive.job_budget": ("int", "Thinking budget for jobs and game turns, in tokens; -1 is no limit"),
    "adaptive.rethink_below": ("float", "Take a second look when she was less sure than this, 0-1"),
    "adaptive.min_gain": ("float", "How much surer, 0-1, a second answer must be to replace the first"),
    "adaptive.speak_corrections": ("bool", "Say the corrected answer out loud; off only records it"),
    "adaptive.correction_prefix": ("text", "What she says before a corrected answer"),
    "adaptive.follow_through": ("bool", "When she announces a step but doesn't do it, make her do it"),

    # --- Grounding check ----------------------------------------------------
    "grounding.enabled": ("bool", "Check specifics in her replies (numbers, paths, links) against what she was told"),
    "grounding.mode": ("choice", "On an unsourced detail: flag (log it), hedge (also add a warning line), check (verify it)",
                       ("flag", "hedge", "check")),
    "grounding.hedge_line": ("text", "What she says after a reply with unchecked details, in hedge mode"),

    # --- Learning -----------------------------------------------------------
    "self.lessons": ("bool", "Let her write lessons from her own mistakes"),
    "self.lessons_in_prompt": ("int", "Most lessons in one prompt"),
    "self.max_lessons": ("int", "Most lessons kept; past this the least-used old one goes"),
    "self.reflect_every_hours": ("float", "How often she reviews her mistakes for lessons, in hours"),
    "self.episodes": ("bool", "Let her keep notes on each conversation to recall later"),
    "self.episodes_in_prompt": ("int", "Most past-conversation notes in one prompt"),
    "self.idle_minutes": ("int", "Minutes of quiet that end a conversation for her notes"),
    "self.tidy_facts": ("bool", "Let her merge duplicate facts and retire contradicted ones"),
    "self.calibration": ("bool", "Let her say when she's unsure, measured from her word probabilities (llama-server)"),
    "self.hedge_below": ("float", "How sure, 0-1, a reply must be before she skips the unsure line"),
    "self.hedge_line": ("text", "What she says when unsure; empty keeps her quiet"),
    "self.greet": ("bool", "Pick up where the last session left off when you come back"),
    "self.skills": ("bool", "Let her keep recipes for multi-step jobs she did well"),
    "self.skills_in_prompt": ("int", "Most recipes in one prompt"),
    "self.max_skills": ("int", "Most recipes kept; past this the least-used goes"),
    "self.projects": ("bool", "Let her track ongoing projects that span sessions"),
    "self.projects_in_prompt": ("int", "Most projects in one prompt"),

    # --- Logging ------------------------------------------------------------
    "logging.enabled": ("bool", "Write a log to ~/.cache/ai-voice/ai-voice.log"),
    "logging.level": ("choice", "How much to log: debug is everything, info is what went wrong and why",
                      ("debug", "info", "warning", "error")),
    "logging.max_kb": ("int", "Size of the log file in KB before it rotates"),
    "logging.keep": ("int", "How many old log files to keep"),

    # --- Live monitor -------------------------------------------------------
    "monitor.enabled": ("bool", "Serve the live monitor page (each turn as it happens, the portrait, the chess board)"),
    "monitor.port": ("int", "Port the live monitor uses on this machine"),

    # --- Plugins: shared stream-chat policy ---------------------------------
    "plugins.chat.tools": ("list", "Tools stream-chat strangers may reach"),
    "plugins.chat.cooldown_seconds": ("float", "Seconds between her chat answers"),
    "plugins.chat.user_cooldown_seconds": ("float", "Seconds before she answers the same viewer again"),
    "plugins.chat.max_message_chars": ("int", "Longest chat message she will answer, in characters"),
    "plugins.chat.context_lines": ("int", "How many recent chat lines she can see"),

    # --- Plugins: pomf ------------------------------------------------------
    "plugins.pomf.enabled": ("bool", "Read pomf.tv stream chat at startup"),
    "plugins.pomf.channel": ("text", "Which pomf.tv room to watch (the streamer's name)"),
    "plugins.pomf.ignore": ("list", "Chat names she never answers, such as bots"),

    # --- Plugins: IRC -------------------------------------------------------
    "plugins.irc.enabled": ("bool", "Join IRC at startup"),
    "plugins.irc.server": ("text", "IRC server address"),
    "plugins.irc.port": ("int", "IRC server port"),
    "plugins.irc.tls": ("bool", "Connect to IRC with encryption (TLS)"),
    "plugins.irc.channel": ("text", "IRC channel to join, like #gameranger"),
    "plugins.irc.nick": ("text", "Her IRC nickname; empty uses her name in lowercase"),
    "plugins.irc.post_replies": ("bool", "Post her answers in the channel"),
    "plugins.irc.speak": ("bool", "Also say her IRC answers out loud"),
    "plugins.irc.max_reply_lines": ("int", "Most lines one IRC reply may take"),
    "plugins.irc.ignore": ("list", "Nicks she never answers, such as bots"),

    # --- Plugins: Twitch ----------------------------------------------------
    "plugins.twitch.enabled": ("bool", "Read Twitch chat at startup"),
    "plugins.twitch.channel": ("text", "Twitch channel whose chat she reads"),
    "plugins.twitch.speak": ("bool", "Say her Twitch answers out loud"),
    "plugins.twitch.post_replies": ("bool", "Post her answers in Twitch chat (needs a bot account login)"),
    "plugins.twitch.max_reply_chars": ("int", "Longest Twitch chat reply, in characters"),
    "plugins.twitch.lewd": ("bool", "Allow her lewd mood and moves while live on Twitch"),
    "plugins.twitch.ignore": ("list", "Chat names she never answers, such as bots"),

    # --- Plugins: YouTube ---------------------------------------------------
    "plugins.youtube.enabled": ("bool", "Read YouTube live chat at startup"),
    "plugins.youtube.video": ("text", "The live stream's link or id; wins over channel"),
    "plugins.youtube.channel": ("text", "A channel handle like @YourHandle, to find whatever it has live"),
    "plugins.youtube.poll_seconds": ("float", "Least seconds between chat checks (each one costs API quota)"),
    "plugins.youtube.speak": ("bool", "Say her YouTube answers out loud"),
    "plugins.youtube.lewd": ("bool", "Allow her lewd mood and moves while live on YouTube"),
    "plugins.youtube.ignore": ("list", "Chat names she never answers, such as bots"),

    # --- Plugins: Discord ---------------------------------------------------
    "plugins.discord.enabled": ("bool", "Connect to Discord at startup, so you can talk to her from anywhere"),
    "plugins.discord.channel": ("text", "Discord channel name or id she listens in; empty is direct messages only"),
    "plugins.discord.speak": ("bool", "Also read her Discord replies aloud at the desk"),
    "plugins.discord.remember": ("bool", "Keep Discord turns in her normal history, like typed ones"),
    "plugins.discord.tools": ("list", "Tools allowed from Discord; empty (null) means every tool"),
    "plugins.discord.approval": ("choice", "Who approves file writes and commands from Discord: auto, discord (in chat) or desk",
                                 ("auto", "discord", "desk")),
    "plugins.discord.approval_timeout": ("float", "Seconds to wait for an answer on Discord; no answer counts as no"),

    # --- Plugins: scheduled jobs --------------------------------------------
    "plugins.cron.enabled": ("bool", "Run scheduled jobs from agent/cron.json"),
    "plugins.cron.job_tools": ("list", "The only tools a scheduled job may use"),

    # --- Plugins: Home Assistant --------------------------------------------
    "plugins.home.enabled": ("bool", "Connect to Home Assistant at startup"),
    "plugins.home.url": ("text", "Home Assistant's address; must be on your own network"),
    "plugins.home.ask_all": ("bool", "Every smart home change asks first"),
    "plugins.home.ask_domains": ("list", "Kinds of device that always ask first (locks, covers, alarms...)"),
    "plugins.home.skip_tools": ("list", "Home Assistant tools to leave out (by default its timers and broadcast)"),

    # --- Plugins: Lovense ---------------------------------------------------
    "plugins.lovense.enabled": ("bool", "Connect to the Lovense Remote app at startup"),
    "plugins.lovense.host": ("text", "Address of the Lovense Remote app (Game Mode)"),
    "plugins.lovense.port": ("int", "Port of the Lovense Remote app"),
    "plugins.lovense.use_https": ("bool", "Talk to the Lovense app over HTTPS"),
    "plugins.lovense.max_strength": ("int", "Strongest vibration she may use, 0-20"),
    "plugins.lovense.max_seconds": ("float", "Longest she may run a toy, in seconds"),
    "plugins.lovense.max_motion": ("int", "Strongest thrusting or machine motion she may use, 0-20"),
    "plugins.lovense.ramp_seconds": ("float", "Seconds motion takes to build up from slow"),
    "plugins.lovense.stop_words": ("list", "Words in your message that stop every toy at once"),
    "plugins.lovense.stop_on_interrupt": ("bool", "Stop every toy when you interrupt her (HOME)"),

    # --- Plugins: Buttplug --------------------------------------------------
    "plugins.buttplug.enabled": ("bool", "Connect to Intiface Central at startup"),
    "plugins.buttplug.url": ("text", "Intiface Central's address (a ws:// link)"),
    "plugins.buttplug.max_intensity": ("int", "Strongest vibration she may use, 0-100"),
    "plugins.buttplug.max_seconds": ("float", "Longest she may run a device, in seconds"),
    "plugins.buttplug.max_motion": ("int", "Strongest stroking or machine motion she may use, 0-100"),
    "plugins.buttplug.ramp_seconds": ("float", "Seconds motion takes to build up from slow"),
    "plugins.buttplug.scan_on_start": ("bool", "Look for devices as soon as it connects"),
    "plugins.buttplug.stop_words": ("list", "Words in your message that stop every device at once"),
    "plugins.buttplug.stop_on_interrupt": ("bool", "Stop every device when you interrupt her (HOME)"),

    # --- Plugins: Minecraft -------------------------------------------------
    "plugins.minecraft.enabled": ("bool", "Join Minecraft at startup"),
    "plugins.minecraft.host": ("text", "Minecraft server or LAN world address"),
    "plugins.minecraft.port": ("int", "Minecraft port (shown in chat when you open a world to LAN)"),
    "plugins.minecraft.username": ("text", "Her player name in Minecraft"),
    "plugins.minecraft.step_seconds": ("float", "Seconds of quiet before she takes her next step"),
    "plugins.minecraft.max_steps": ("int", "Steps per goal before she pauses and asks"),
    "plugins.minecraft.speak": ("bool", "Say each step out loud"),
    "plugins.minecraft.web": ("bool", "Let her look things up on the web while playing"),
    "plugins.minecraft.guide": ("text", "Her guide: a folder in her knowledge folder; empty for none"),
    "plugins.minecraft.mc_tools": ("list", "Which of the Minecraft server's tools she gets"),
    "plugins.minecraft.command": ("text", "Command that starts the Minecraft MCP server; empty uses the installed one or npx"),

    # --- Plugins: Zork ------------------------------------------------------
    "plugins.zork.enabled": ("bool", "Load Zork at startup"),
    "plugins.zork.step_seconds": ("float", "Seconds of quiet before her next move"),
    "plugins.zork.max_steps": ("int", "Moves per /zork play before she pauses"),
    "plugins.zork.speak": ("bool", "Narrate each turn out loud"),
    "plugins.zork.web": ("bool", "Let her look things up on the web while playing"),
    "plugins.zork.interpreter": ("text", "Path to dfrotz if it's somewhere unusual"),
    "plugins.zork.watch": ("bool", "Open the watch window with /zork play"),
    "plugins.zork.terminal": ("text", "Terminal for the watch window, e.g. kitty; empty finds one"),
    "plugins.zork.guide": ("bool", "Show her what agent/knowledge/zork/ says about the room she's in"),
    "plugins.zork.turn_seconds": ("float", "Longest one turn may run before it is cut short, in seconds; 0 is no limit"),

    # --- Plugins: Vibe City -------------------------------------------------
    "plugins.vibecity.enabled": ("bool", "Connect to Vibe City at startup"),
    "plugins.vibecity.url": ("text", "Address of the game's built-in MCP server"),
    "plugins.vibecity.step_seconds": ("float", "Seconds of quiet before her next turn"),
    "plugins.vibecity.max_rounds": ("int", "Most tool calls she may make in one turn"),
    "plugins.vibecity.max_steps": ("int", "Turns per /vibecity play before she stops (and the game pauses)"),
    "plugins.vibecity.speak": ("bool", "Narrate each turn out loud"),
    "plugins.vibecity.web": ("bool", "Let her look things up on the web while playing"),
    "plugins.vibecity.goal": ("text", "What she aims for as mayor, e.g. reach 2000 people"),
    "plugins.vibecity.skip_tools": ("list", "Game tools to leave out, e.g. screenshot for a model that can't see"),
    "plugins.vibecity.pause_game": ("bool", "Pause the game when she stops playing"),
    "plugins.vibecity.guide": ("text", "Her guide: a folder in her knowledge folder; empty for none"),

    # --- Plugins: REALITI ---------------------------------------------------
    "plugins.realiti.enabled": ("bool", "Let her into REALITI at startup"),
    "plugins.realiti.path": ("text", "Where the REALITI checkout lives"),
    "plugins.realiti.step_seconds": ("float", "Seconds of quiet before her next turn"),
    "plugins.realiti.max_steps": ("int", "Turns per /realiti visit before she rests"),
    "plugins.realiti.speak": ("bool", "Say each turn out loud"),
    "plugins.realiti.resident": ("text", "Her name in the world's memory"),
    "plugins.realiti.node": ("text", "Path to node if it's somewhere unusual"),
    "plugins.realiti.watch": ("bool", "Open the watch window with /realiti visit"),
    "plugins.realiti.terminal": ("text", "Terminal for the watch window, e.g. kitty; empty finds one"),
    "plugins.realiti.guide": ("bool", "Show her what agent/knowledge/realiti/ says about the room she's in"),
    "plugins.realiti.city": ("text", "A REALITI server whose shared city she stays joined to; empty for her own world"),

    # --- Plugins: chess -----------------------------------------------------
    "plugins.chess.enabled": ("bool", "Set up the chess board at startup"),
    "plugins.chess.side": ("choice", "Your colour in a new game", ("white", "black", "random")),
    "plugins.chess.speak": ("bool", "Say her chess comments out loud"),
    "plugins.chess.open": ("bool", "Open the board in your browser with /chess on"),
    "plugins.chess.think_seconds": ("float", "Pause in seconds before her move, so it doesn't snap in"),
    "plugins.chess.turn_seconds": ("float", "Longest one of her turns may run before it is cut short, in seconds"),
}

# The everyday settings: what the terminal's settings pane shows first
# (`a` there shows all of them), and what the web settings page opens on.
BASIC = (
    "voice", "tts.speed", "tts.volume",
    "stt.mode", "stt.sensitivity", "stt.silence_seconds", "stt.language", "wake_word.enabled",
    "mood.enabled", "mood.intensity", "mood.walk_away",
    "portrait.frame", "portrait.gestures", "portrait.touch_talk",
    "camera.presence.enabled", "people.voice",
    "vision.enabled", "knowledge.enabled", "reminders.enabled", "alarms.volume",
    "long_term_memory.enabled", "self.greet", "thoughts.enabled", "ui.mouse",
)
