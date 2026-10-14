"""One turn, from text to speech.

Both input paths end here - typed lines from the TUI and spoken turns
from push-to-talk - so the two behave identically. That matters more
than it sounds: before this they each had their own copy of "ask, then
print, then speak", and the copies drifted.
"""
import threading

from config import AGENT_NAME
from llm import ask
from speech import record_audio, transcribe

import interrupts
import logbook
import speech
import turnctx
import ui

# One turn at a time. Every Enter spawns its own worker, so without
# this a second message sent while she's still speaking would run
# alongside the first: two replies generating at once, both feeding the
# same audio device, and history written in whatever order they
# happened to finish.
_turn = threading.Lock()

# The Stop of whichever turn holds _turn: a new message from you cuts its
# reply short (and only its).
_holder = {"stop": None}


def _hold(stop):
    """Inside `with _turn`: this turn is the one a new message cuts off."""
    _holder["stop"] = stop


def _plugins_hear(text):
    """Your message reaches running plugins first - so a stop word stops a
    toy now, not after she's finished thinking about it."""
    try:
        import plugins

        plugins.user_text(text)
    except Exception:
        pass


def _note_mood(text, answer, model):
    """Her mood hears what Ryan says and what she answered. Deliberately
    not wired into respond_to_chat: a stranger in stream chat being sweet
    to her shouldn't move the same dial he does."""
    try:
        import mood

        mood.note_exchange(text, answer, model)
    except Exception:
        pass  # decoration; never the reason a turn fails


def _gone(text=None, model=None):
    """mood.walk_away: has she walked away? None if she's here. Otherwise
    what she says: her one leaving line the first time, then "".

    By the time this runs, stop words have been heard (_plugins_hear
    comes first), and alarms and reminders never come through here, so
    those keep working. Your own message (text and model given) gets one
    small check for making up, which brings her back to answer it."""
    try:
        import mood

        if not mood.away():
            return None

        if text is not None and mood.heard_while_away(text, model):
            return None

        return mood.leaving_line()
    except Exception:
        return None     # a sulk is never the reason a turn breaks


def _say_away(said):
    """Her leaving line at the desk, shown and spoken; after that, quiet."""
    if not said:
        ui.set_status(f"{AGENT_NAME} isn't talking right now")
        return

    ui.begin_message(AGENT_NAME.lower())
    ui.extend_message(said)
    ui.end_message()
    player = speech.Player()
    player.say(said)
    player.wait()
    ui.set_status("Idle")


def respond(text, model, source="typed"):
    """Send a turn to the model and speak the reply as it arrives.

    Nothing here waits for the whole answer. Text appears on screen as
    it is generated and each finished sentence goes to the speaker
    immediately, so Luna starts talking about a sentence in rather than
    after the entire reply has been written.

    Turns are serialized. Sending a second message while she's still
    talking means you've moved on, so the previous reply stops being
    spoken - but it is still allowed to finish generating and stays on
    screen, the same bargain barge-in makes. Interrupting should cost
    you the audio, never the answer.

    source: "typed" or "voice". Runs as the caller's Stop (interrupts)
    if it opened one - ptt does, at the key press - else its own, opened
    now, before waiting: a HOME pressed while it waits still reaches it.
    """
    _plugins_hear(text)

    with interrupts.ensure(source) as stop:
        running = _holder["stop"]

        if _turn.locked() and running is not None:
            logbook.info("turn", "new message while speaking - cutting the last one short")
            running.stop(speaking=True)

        with _turn:
            _hold(stop)

            try:
                said = _gone(text, model)

                if said is not None:
                    _say_away(said)
                    return said

                return _respond(text, model, source, stop)
            finally:
                _hold(None)


def busy():
    """Is a turn in flight? Stream chat waits rather than barging in."""
    return _turn.locked()


def respond_to_chat(prompt, model, source, who, said,
                    context=None, tools_allowed=None, speak=True):
    """A turn that came from stream chat rather than from Ryan.

    Same speaking path - answering out loud is the whole point on a
    stream - but it waits for the lock instead of cutting the current
    reply short. Ryan interrupting her is him changing his mind; a
    viewer interrupting her is a stranger talking over him.

    speak=False makes it a silent turn: still thought about, still shown
    on screen, just never sent to the voice. That is for a room she
    answers in writing - IRC, where the reply is posted as text and
    reading it aloud would mean every stranger in the channel can make
    noise in the room he is sitting in.

    The prompt, the context and the tool list are built by the plugin,
    and nothing here is stored: remember=False keeps a stranger's words
    out of history and out of the transcript.
    """
    # Its own Stop (interrupts), opened once it holds the lock, so HOME
    # cancels the reply it was pressed during and nothing after it: one
    # press used to leave a global flag set, and every stream-chat and IRC
    # message after came back empty with "you interrupted it" - which
    # looks exactly like the chat plugin having died.
    with _turn, interrupts.using(kind="chat") as stop:
        _hold(stop)

        if _gone() is not None:
            _hold(None)
            return ""       # walked away: strangers get nothing either

        # Not constructed at all when silent. A Player opens an output
        # stream on the sound device; one made and never spoken to is a
        # device handle held for the length of the turn for nothing.
        player = speech.Player() if speak else None

        # What they said, not just that somebody said something. The
        # first version showed only the name, which made the one thing
        # you actually want to read - the question she is about to
        # answer on stream - the one thing that wasn't on screen.
        ui.add_message(f"chat:{source}", f"{who}: {said}")
        ui.set_status("Chat..." if speak else "Chat (silent)...")
        ui.begin_message(AGENT_NAME.lower())

        def on_sentence(sentence):
            if not stop.speaking.is_set():
                player.say(sentence)

        try:
            answer = ask(
                prompt, model,
                on_text=ui.extend_message,
                # None is the documented "don't speak" path through
                # ask() - the same one the reminder scanner uses.
                on_sentence=on_sentence if speak else None,
                context=context, tools_allowed=tools_allowed, remember=False,
            )

            ui.replace_message(answer)
            ui.end_message()

            if player is not None:
                player.wait()

            return answer
        except Exception:
            ui.end_message()
            raise
        finally:
            _hold(None)
            ui.set_status("Idle")


def respond_to_job(prompt, model, job, tools_allowed, speak=True, max_rounds=None,
                   project_id=None):
    """A scheduled job firing (plugins/cron.py).

    Waits its turn like chat does. Fresh context and nothing stored, so a
    job's tool output never lands in history. The turn is begun here and
    only here with the job's name (turnctx) - that's what lets files.py
    tell a job's write from yours, and it ends with the turn.
    """
    with _turn, interrupts.using(kind="job") as stop:
        _hold(stop)

        if _gone() is not None:
            _hold(None)
            return ""       # walked away: jobs and games wait

        player = speech.Player() if speak else None

        ui.add_message("system", f"Job: {job}")
        ui.set_status(f"Job {job}...")
        ui.begin_message(AGENT_NAME.lower())

        def on_sentence(sentence):
            if not stop.speaking.is_set():
                player.say(sentence)

        try:
            # max_rounds None: the usual tools.max_rounds; project_id: a
            # game's notes, for game_note.
            with turnctx.begin(source=f"job:{job}", private=False, job=job,
                               max_rounds=max_rounds, project_id=project_id):
                answer = ask(prompt, model, on_text=ui.extend_message,
                             on_sentence=on_sentence if speak else None,
                             context=[], tools_allowed=tools_allowed,
                             remember=False, source=f"job:{job}")
            ui.replace_message(answer)
            ui.end_message()

            if player is not None:
                player.wait()

            return answer
        except Exception:
            ui.end_message()
            raise
        finally:
            _hold(None)
            ui.set_status("Idle")


def respond_remote(text, model, source, who, tools_allowed=None,
                   speak=False, remember=True, approver=None):
    """The owner talking to her from somewhere else - Discord.

    A normal private turn (his history, his tools) that waits for the
    lock rather than cutting you off. Its turn is begun here with the
    source and approver (turnctx), so files.py can apply
    files.auto_approve_sources to it and to nothing else.
    """
    _plugins_hear(text)

    with _turn, interrupts.using(kind="remote") as stop:
        _hold(stop)
        said = _gone(text, model) if remember else _gone()

        if said is not None:
            _hold(None)
            return said or "(She isn't talking right now.)"

        player = speech.Player() if speak else None

        # As "user", tagged: ui.py labels any speaker it doesn't know
        # (not user/system/chat:) as her, so "discord:Ryan" rendered
        # your message under her name.
        ui.add_message("user", f"[{source}] {text}")
        ui.set_status(f"{source.title()}...")
        ui.begin_message(AGENT_NAME.lower())

        def on_sentence(sentence):
            if not stop.speaking.is_set():
                player.say(sentence)

        try:
            # approver: who answers permission questions for this turn,
            # if not the desk popup - approver(kind, title, body, guarded) -> bool.
            with turnctx.begin(source=source, private=remember, remote=source, approver=approver):
                answer = ask(text, model, on_text=ui.extend_message,
                             on_sentence=on_sentence if speak else None,
                             context=None if remember else [],
                             tools_allowed=tools_allowed, remember=remember,
                             source=source)
            ui.replace_message(answer)
            ui.end_message()

            if player is not None:
                player.wait()

            return answer
        except Exception:
            ui.end_message()
            raise
        finally:
            _hold(None)
            ui.set_status("Idle")


def _respond(text, model, source, stop):
    player = speech.Player()

    ui.set_status("Thinking...")
    ui.begin_message(AGENT_NAME.lower())

    def on_sentence(sentence):
        # HOME during generation means "don't bother speaking this" -
        # the reply still finishes and stays on screen.
        if not stop.speaking.is_set():
            player.say(sentence)

    try:
        # Your own turn, typed or spoken: ask() leaves source None for
        # those (it's what turns on the second-look checks), so how it
        # reached her is set on the turn itself.
        with turnctx.begin(source=source):
            answer = ask(
                text, model, on_text=ui.extend_message, on_sentence=on_sentence
            )

        ui.replace_message(answer)
        ui.end_message()
        # Read now, while she's still speaking, so a laugh or a blush
        # lands with the words rather than after them.
        _note_mood(text, answer, model)
        player.wait()

        return answer
    except Exception:
        ui.end_message()
        raise


def assistant_task(model, mode=None):
    """A spoken turn: record, transcribe, answer.

    Returns True if there was actually something to answer, which is
    how the hands-free loop knows whether to hold the follow-up window
    open or go back to waiting for the wake word.

    Runs as the caller's Stop (ptt opens one at the key press), or its own.
    """
    with interrupts.ensure("voice") as stop:
        return _spoken_turn(model, mode, stop)


def _spoken_turn(model, mode, stop):
    if not speech.ready():
        ui.add_message("system", "Still loading the speech models - one moment.")
        ui.set_status("Loading...")

        return False

    ui.set_status("Listening..." if mode != "manual" else "Recording...")

    try:
        stop.recording = True

        try:
            filename = record_audio(mode)
        finally:
            stop.recording = False

        # Cancelled rather than finished - throw the audio away instead
        # of transcribing it and then refusing to answer.
        if stop.generating.is_set():
            ui.set_status("Idle")
            return False

        # None means the detector never heard speech, or heard a blip too
        # short to be a sentence. Don't bother Whisper with it.
        if filename is None:
            ui.set_status("Idle")
            return False

        ui.set_status("Transcribing...")
        text = transcribe(filename)

        if not text:
            ui.set_status("Idle")
            return False

        logbook.info("turn", "heard: %s", text[:200])
        ui.add_message("user", text)
        respond(text, model, source="voice")
        ui.set_status("Idle")

        return True
    except Exception as e:
        logbook.exception("turn", "spoken turn failed")
        ui.set_status(f"Error: {e}")

        return False
