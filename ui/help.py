"""What the help says: every command and key, in sections. Shown as a page
in the browser (web/help_web.py, /help, or Help in the launcher pane), not in
the terminal any more.

Part of the ui package (it was one ui.py); see ui/__init__.py.
"""
from .shared import state


# What HOME does depends on the recording mode, so the help says what
# it will actually do right now rather than something generic.
_HOME_BY_MODE = {
    "auto": "start listening; a pause ends it",
    "manual": "start recording; press again to stop",
    "open": "turn hands-free listening on or off",
}

# A row is (command, description); a bare string is a paragraph of its own
# (the help page shows each one as a line of text).
_HELP_SECTIONS = [
    ("Just ask", [
        "Most of what Luna does has no command: just ask. All of these work:",
        '"remind me in 20 minutes to stretch"',
        '"wake me up at 7:30" or "every weekday at 6"',
        '"remember that I stream on Tuesdays"',
        '"what do you remember about my GPU?"',
        '"search for the LM Studio 0.4 changelog"',
        '"what time is it?" or "how long until Friday?"',
        '"turn the music down" or "what\'s on my clipboard?"',
        '"how much VRAM have I got free?"',
        '"what\'s on my screen?" (needs vision on, and a model that can see)',
        '"write me a bash script in ~/scripts that backs up my configs"',
        '"open ~/notes.txt and fix the typo in the second line"',
    ]),
    ("Keys", [
        ("(HOME)", None),  # filled in from the current mode
        ("(Enter)", "send your message"),
        ("(PgUp/PgDn)", "scroll the conversation, or move around in a pane"),
        ("(wheel)", "scroll too, and so do the arrow keys"),
        ("(F2)", "switch the mouse between scrolling and selecting text"),
        ("(End)", "jump to the newest message"),
        ("(Tab)", "switch between the conversation, the pages list, tools and settings"),
        ("(ESC)", "close a pane or popup"),
        ("(Ctrl+Q)", "quit"),
    ]),
    ("Listening", [
        ("/mode", None),  # gets the (now: ...) suffix
        "auto: HOME starts listening, and a pause ends it. manual: HOME starts recording and HOME again stops it. open: hands-free, always listening.",
        ("/mic", "mic levels from your last recording, to check Luna can hear you"),
        ("/barge", "how talking over Luna is set up, with the thresholds"),
        ("/wake", "wake word status and live scores"),
        ("/hear", "whether the model gets the recording of what you said, not just the words"),
    ]),
    ("Voice", [
        ("/voice", "list the voices on the speech server, the current one first"),
        ("/voice bella", "switch voice (part of the name is enough, and it's saved)"),
        ("/voice luna", "blends work too, if the speech server has them"),
        "Pitch is a setting rather than a voice: /set tts.pitch 3 sounds younger, -3 older, from the next sentence.",
    ]),
    ("Reminders", [
        ("/reminders", "what's scheduled, numbered, with how long until each"),
        ("/cancel N", "cancel one by its number (alarms are in the same list)"),
        ("/when ...", "test how a time is understood, without scheduling anything"),
        ("/calendar", "the next seven days from your calendars, read-only (/calendar refresh reads them again)"),
        "Repeats work too: \"every Monday at 9\", \"daily at 7:30\", \"every 30 minutes\", \"weekdays at 8\". Say them or type them.",
    ]),
    ("Alarms", [
        ("/alarm 7:30am", "set an alarm (any way of saying a time works)"),
        ("/alarm every weekday at 6", "a repeating alarm"),
        ("/alarms", "list them (cancel with /cancel)"),
        ("/snooze [n]", "ring again in n minutes, or the usual snooze without a number"),
        ("/alarm off", "stop a ringing alarm (talking over it works too)"),
        ("/alarm test", "hear the tone at alarm volume"),
        ("/when alarm 6", "test how an alarm reads a time (a bare hour means morning)"),
        "An alarm says a line written for it, plays the tone, and keeps repeating until you stop it, a little louder each time. One that came due while Luna was closed is skipped, not rung late.",
    ]),
    ("Mood", [
        ("/mood", "the current mood, and what changed it"),
        ("/mood check [n]", "how the mood reader rates your last n exchanges, old prompt and new"),
        ("/mood reset", "back to normal for the next hour"),
        "The mood shows on the Status row (like \"Idle - sleepy\") and changes the voice slightly. It survives a restart, fading the longer you were away. It drifts with the time of day, how long you've been at it, errors, being talked over, and whether you're kind. It changes the tone only, never how much Luna helps. /set mood.enabled false turns it off.",
    ]),
    ("Patches", [
        ("/good", "keep the last reply as a good example"),
        ("/fix <reply>", "keep your better version of the last reply instead"),
        ("/unrate", "take back the thumbs or /good /fix on her last reply"),
        ("/examples", "how many examples there are, and the page to look through them"),
        ("/patches", "trained patches: loaded, waiting, or made for another model"),
        ("/patches <name> <0-1>", "change a loaded patch's strength while Luna runs"),
        "Examples are used to train patches: small add-ons that teach a habit, like where gestures go. The model never sees these commands, and the examples stay on your computer in agent/dataset/. Train one with training/train.sh gesture|habit (best overnight, with the graphics card free). More in docs/patches.md.",
    ]),
    ("Memory", [
        ("/facts", "what Luna remembers, newest first"),
        ("/facts all", "every fact, not just the newest"),
        ("/facts retired", "facts that were replaced (kept, but not used)"),
        ("/facts unsure", "facts heard once and not confirmed yet"),
        ("/facts log", "every change to Luna's memory, when, and who made it; /facts log 42 for one fact"),
        ("/facts pin 42", "keep fact #42 always in front of her; /facts unpin 42, /facts pinned lists them"),
        ("/memory", "the memory editor, in your browser"),
        "Facts are kept for good and searched when they're relevant. A new fact can replace an old one it contradicts.",
        ("/reflect", "tidy up now: lessons, conversation notes, facts, pages"),
        ("/lessons", "what Luna has learned (/lessons forget|restore <n>)"),
        ("/episodes", "notes on past conversations and games (/episodes forget <n>)"),
        ("/skills", "saved how-tos for bigger jobs (/skills show|forget|restore <n>)"),
        ("/projects", "ongoing work (/projects show|done|pause|resume|drop <n>)"),
        ("/pages", "summary pages per subject (/pages <subject>, rebuild, forget <subject>)"),
        ("/profile", "the short profile of you and each person Luna knows (/profile <name|me>, rebuild, forget <name>)"),
        ("/conclusions", "what Luna has concluded about each person from talking to them (<name|me>, why <n>, wrong <n>, restore <n>)"),
        ("/situation", "the live details the model sees each turn (window, music, load...)"),
        "The Learning group in the tools pane switches each of these on or off.",
    ]),
    ("Windows", [
        ("/chat", "the chat in a window of its own (the same conversation as here)"),
        ("/thoughts", "the model's thinking, turn by turn, in your browser"),
        ("/monitor", "watch Luna think live: stages, tokens, tools, mood"),
        ("/portrait", "open the avatar in its own window (again to close it)"),
        ("/pose", "the pose studio: make and try out gestures, touches and moods"),
        "/set thoughts.enabled false stops the thinking log.",
    ]),
    ("The avatar", [
        ("/portrait models", "list the models in portrait/models (/portrait use <n> switches)"),
        ("/portrait obs", "the see-through address for an OBS browser source"),
        ("/portrait wave", "play a gesture: wave hug jump bounce shrug stretch look_hand tuck_hair (3D models)"),
        ("/portrait gestures", "how replies trigger gestures: tags, meaning, keywords, or off"),
        ("/portrait sounds", "gesture sound effects: on, off, or a volume like 50%"),
        ("/portrait clothes", "how the conversation changes clothes: gestures, tags, keywords, or off"),
        ("/portrait frame", "bust (head and shoulders) or full. Click the avatar to touch it"),
        ("/holo", "hologram look on or off"),
        ("/lights", "light strips on the robot avatar on or off"),
        ("/outfit", "clothes on a human avatar: dressed, underwear, or one piece off or on"),
        ("/blanket", "a blanket round the avatar's shoulders, on or off"),
        ("/rave", "rave gear (a pacifier and glow sticks), on or off"),
        ("/coffee", "a coffee now (it also happens by itself in the morning; /coffee off, sip)"),
        ("/read", "read a book (it also happens by itself when you're quiet; /read off, page, look)"),
        ("/freetime", "what she did with her free time, and why she picked it (/freetime now for some now)"),
        ("/doze", "doze under a blanket (it also happens by itself late at night; /doze off wakes it)"),
        ("/plushie", "hug Mochi the plushie (it also happens by itself when the mood is low; /plushie off, squeeze)"),
    ]),
    ("Tools", [
        "Tab twice opens the tools pane: every tool, how much space it takes in each message, and space bar to switch it on or off. Every tool's description goes along with each message, so switching off ones you rarely use leaves more room for the conversation. Your choices are saved; a tool that's missing something it needs says so.",
        ("/tools", "the same list, in the conversation"),
        ("/tooltest", "test requests to check this model picks the right tools (run it after changing models)"),
        ("/repair", "redo old reminders that were set the old way, so the model learns the right way"),
    ]),
    ("Files", [
        "Luna can list and read anything in your home folder (except keys, passwords and shell startup files), and write or edit with your OK: every change pops up a window showing it first. Y or Enter allows, N or Esc says no, PgUp/PgDn scrolls.",
        "A allows all file changes until you restart (Luna's own folder, ~/.config and ~/.local still ask). /allow off ends it early. To set it for good, use Permissions at the top of the tools pane: allow, ask or off for reading, writing and running. No answer within files.approval_timeout seconds counts as no.",
    ]),
    ("Commands", [
        "Luna can run shell commands, like \"check if the kokoro service is running\" or \"what's using port 8080?\". Every one asks first, showing the command and the folder, and there's no allow-all. Output is limited, commands time out (shell.timeout), and sudo can't ask for a password here. /set shell.enabled false turns it off.",
    ]),
    ("Plugins", [
        ("/plugins", "add-ons and whether each is running"),
        ("/mcp", "MCP servers: connected or not, and their tools"),
        ("/pomf on", "stream chat (/<name> on|off|status works for any plugin)"),
        "Messages from stream chat get a limited set of tools and never go into your conversation history.",
    ]),
    ("Other", [
        ("/look", "list windows, or test a screenshot"),
        ("/camera", "webcam on or off, list cameras, take a test picture"),
        ("/presence", "notice who's at the desk: on, off, status"),
        ("/people", "who Luna knows: enroll face|voice <name>, forget <name>, check, guest <name>, keep <name>"),
        ("/offers", "things Luna noticed and wants to offer (/offers on, off, unmute, now)"),
        ("/music", "what's playing, with style and tempo (/music now listens again; needs music.url)"),
        ("/allow", "is allow-all on for file changes? (/allow off ends it)"),
        ("/log", "show the end of the debug log"),
        ("/log stderr", "what libraries printed (OpenCV, sound, a browser), kept off the screen"),
        ("/context", "how much of the model's context each message uses"),
        ("/scroll", "why the mouse wheel isn't scrolling, if it isn't"),
        ("/mouse", "the same as F2, and saves the choice"),
        ("/keys", "check the hotkey and control socket"),
        ("/clear", "clear the conversation and its history (not the memory)"),
        ("/retry", "throw away her last reply and have her answer your message again (not after a tool, a file or a guest)"),
        ("/quit", "quit"),
    ]),
    ("Settings", [
        ("/settings", "every setting in your browser: switches, sliders, search, presets"),
        ("/set", "list every setting and its value (/set a.b x changes one)"),
        ("/preset", "assistant, companion or streamer, and small, medium or large for the model: several settings at once"),
        "Changes are saved to config.json, and most apply straight away (↻ marks the ones that need a restart). The settings pane (Tab three times) has every setting too: space flips or steps, Enter edits, / searches, x resets one to its default.",
        "In the tools pane: up/down or the wheel picks, space switches, a does the whole group, r switches tool routing. The Mood, Thoughts and Learning groups at the bottom switch those features. While the pane is open the wheel moves one item per notch; F2 and selecting text go back to normal when you leave it.",
    ]),
]


def sections(mode=None):
    """[(title, [(command, description) | note string])] with the rows that
    depend on the voice mode filled in."""
    mode = mode or state.get("mode", "auto")
    out = []
    for title, rows in _HELP_SECTIONS:
        filled = []
        for entry in rows:
            if isinstance(entry, str):
                filled.append(entry)
                continue
            key, description = entry
            if key == "(HOME)":
                description = _HOME_BY_MODE.get(mode, _HOME_BY_MODE["auto"])
            elif key == "/mode":
                description = f"auto | manual | open   (now: {mode})"
            filled.append((key, description or ""))
        out.append((title, filled))
    return out
