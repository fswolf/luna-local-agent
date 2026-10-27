"""When you touch her portrait, she knows.

The portrait reacts on its own the instant you click her (touch.js, a
gesture and a face). This is the second half: the touch comes here
(livefeed, POST /portrait/touch) and she answers it out loud, in
character, with one short line - knowing her mood and what you were
just talking about, so a poke mid-argument and one mid-scene play
differently.

Kept quick and small, so it never feels like waiting:

  - pokes within a moment of each other are one touch ("on the head, 3 times")
  - one short line: a hard token cap, no tools, no thinking, cut at the
    first line break
  - at most one every portrait.touch_talk_cooldown seconds; touches in
    between get the portrait's reaction only
  - never while you're talking, while she's answering, or when she's
    walked away
  - into her history and transcript as one short exchange, so she
    remembers it, her mood reads it like any exchange, and her idle
    notes pick it up

portrait.touch_talk (the settings pane's "touch talk") turns it off.
"""
import re
import threading
import time

import config
from core import logbook

# The zones touch.js names, and how she's told where
PLACES = {
    "head": "on the head", "nose": "on the nose", "mouth": "on the lips", "chest": "on the chest",
    "tummy": "on the tummy", "groin": "between the legs", "legs": "on the leg", "neck": "on the neck",
    "arms": "on the arm", "back": "on the back", "butt": "on the butt", "tail": "on the tail",
    "spank": "with a spank on the butt",     # the portrait's spank (warm and up): mood.note_spank
}
WINDOW = 1.5          # seconds of pokes gathered into one touch
MAX_TOKENS = 40       # her line, not a paragraph

_lock = threading.Lock()
_pending = {}         # zone -> times, since the last touch she answered
_state = {"model": None, "timer": None, "last": 0.0}


def start(model):
    """main.py, at startup: the model her lines come from."""
    _state["model"] = model


def enabled():
    return bool(getattr(config, "PORTRAIT_TOUCH_TALK", True))


def cooldown():
    try:
        return max(0.0, float(getattr(config, "PORTRAIT_TOUCH_TALK_COOLDOWN", 12)))
    except (TypeError, ValueError):
        return 12.0


def note(zone):
    """A touch on the portrait. True if it was taken (she may still not
    answer it: too soon after the last, or she's busy)."""
    if zone == "spank":
        # counted whether or not she talks about it: too many is a punishment
        try:
            from mind import mood

            mood.note_spank()
        except Exception:
            pass
    if zone not in PLACES or not enabled() or not _state["model"]:
        return False
    with _lock:
        _pending[zone] = _pending.get(zone, 0) + 1
        if _state["timer"] is None:
            timer = threading.Timer(WINDOW, _fire)
            timer.daemon = True
            _state["timer"] = timer
            timer.start()
    return True


def describe(touches):
    """{zone: times} -> "on the head, 3 times, and on the nose"."""
    parts = [PLACES[z] + (f", {n} times" if n > 1 else "") for z, n in touches.items() if z in PLACES]
    return parts[0] if len(parts) == 1 else ", ".join(parts[:-1]) + " and " + parts[-1] if parts else ""


def _fire():
    with _lock:
        _state["timer"] = None
        touches = dict(_pending)
        _pending.clear()
        too_soon = time.monotonic() - _state["last"] < cooldown()
    if not touches or too_soon or not enabled():
        return
    try:
        _answer(touches)
    except Exception:
        logbook.exception("touches", "touch turn failed")


def _quiet_now():
    """Is anything else going on? Then the portrait's reaction is enough."""
    try:
        from core import assistant
        from core import interrupts
        from mind import mood

        return not (assistant.busy() or interrupts.recording() or mood.away())
    except Exception:
        return False


def _note(where):
    who = getattr(config, "USER", "the user")
    return (f"(Not words from {who}: {who} just touched you {where} on your portrait. React to it in "
            "character, out loud, in one short line - under 12 words. Don't narrate the touch back.)")


def _request(messages, model):
    import requests

    from core import lmstudio

    gen = getattr(config, "GENERATION", None) or {}
    body = lmstudio.chore({"model": model, "messages": messages,
                           "temperature": gen.get("temperature", 0.8)}, max_tokens=MAX_TOKENS, think=0)
    r = requests.post(config.LM_URL, headers=config.LLM_HEADERS, json=body, timeout=60)
    r.raise_for_status()
    return r.json()["choices"][0]["message"].get("content") or ""


def clean(reply):
    """Her line: thinking cut, the first line only, no quotes around it."""
    text = re.sub(r"<think>.*?(</think>|$)", "", str(reply or ""), flags=re.DOTALL)
    line = next((ln.strip() for ln in text.splitlines() if ln.strip()), "")
    return line.strip('"“” ')[:200]


def _answer(touches):
    from core import assistant
    from core import history
    from core import interrupts
    from voice import speech
    from core import transcript
    from core import turnctx
    import ui
    from llm import _replay, _timing_note, build_system_prompt

    if not _quiet_now() or not assistant._turn.acquire(blocking=False):
        return
    model = _state["model"]
    where = describe(touches)
    note = _note(where)
    if "qwen3" in str(model).lower() and getattr(config, "LLM_BACKEND", "") != "llama":
        note += " /no_think"      # LM Studio has no thinking budget; Qwen3 listens for this

    try:
        with interrupts.using(kind="touch") as stop, turnctx.begin(source="touch"):
            assistant._hold(stop)
            _state["last"] = time.monotonic()
            past = history.get_messages_full()
            messages = [{"role": "system", "content": build_system_prompt(note, _timing_note(past))}]
            for m in past:
                messages.extend(_replay(m))
            messages.append({"role": "user", "content": note})

            ui.set_status("Touched...")
            reply = _request(messages, model)
            try:
                from life import gestures

                gestures.new_turn()
                gestures.from_tags(reply)        # a [tag] she writes plays as well
                reply = gestures.strip(reply)
            except Exception:
                pass
            said = clean(reply)
            if not said:
                return

            ui.add_message("system", f"(you touched her {where})")
            ui.begin_message(config.AGENT_NAME.lower())
            ui.extend_message(said)
            ui.end_message()

            remembered = f"*touches you {where}*"
            history.add_message("user", remembered)
            history.add_message("assistant", said)
            history.save()
            transcript.add("user", remembered)
            transcript.add("assistant", said)
            try:
                from mind import mood

                mood.note_exchange(remembered, said, model)
            except Exception:
                pass

            if not stop.speaking.is_set():
                player = speech.Player()
                player.say(said)
                player.wait()
    finally:
        assistant._hold(None)
        assistant._turn.release()
        ui.set_status("Idle")
