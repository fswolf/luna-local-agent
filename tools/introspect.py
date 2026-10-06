"""Looking at her own numbers.

The thought log measures things about each turn that she can't see from
the inside: how likely each token she produced actually was, what she
nearly said instead, which review flags it tripped. This hands one turn
of that back to her - on request, never pushed into every prompt,
because a model that knows its scratchpad is being read starts writing
it for an audience.

Read-only and only ever her own turns. It is not in chatroom's tool
ceiling, so a stranger in stream chat can't ask her to recite her
history; the turns it reads never include chat turns anyway, since
those aren't recorded.

What comes back is measurement, worded as measurement. What she makes
of it is generated text like anything else she says, which is why the
viewer keeps the raw numbers next to it.
"""
from datetime import datetime

import timeutil

from . import tool


def _private():
    """Is the turn in flight Ryan's own? These tools answer about him and
    about her history with him; a stream-chat turn gets nothing, even if
    a model names a tool it wasn't offered."""
    try:
        import llm

        return bool(llm.turn.get("private", True))
    except Exception:
        return True


_NOT_HERE = "Not available on a stream-chat turn."


def _available():
    try:
        import thoughtlog

        return thoughtlog.enabled()
    except Exception:
        return False


@tool(
    "introspect",
    "Look at measured data about one of your own earlier replies: how "
    "sure you actually were of each word (from your token probabilities), "
    "the words you nearly said instead, and any problems the review "
    "flagged. Use it when asked how confident you were, why you said "
    "something, or whether you were guessing. It describes a past reply, "
    "not the one you're writing now.",
    {
        "turns_back": {
            "type": "integer",
            "description": "Which reply: 1 is your previous one, 2 the one "
                           "before that. Defaults to 1.",
        },
    },
    available=_available,
    why=lambda: "the reasoning log is off (thoughts.enabled)",
)
def _introspect(turns_back=1):
    if not _private():
        return _NOT_HERE

    import config
    import thoughtlog

    try:
        back = max(1, min(int(turns_back or 1), 50))
    except (TypeError, ValueError):
        back = 1

    rows = thoughtlog.rows(limit=1, offset=back - 1)

    if not rows:
        return "There's no recorded reply that far back."

    row = rows[0]
    lines = []

    try:
        when = timeutil.relative(datetime.fromisoformat(row["timestamp"]),
                                 datetime.now())
    except (ValueError, TypeError):
        when = row["timestamp"]

    said = " ".join(row["user_text"].split())
    lines.append(f"Your reply from {when}, to: \"{said[:160]}\"")

    if row.get("n_tokens"):
        runs = thoughtlog.tokens_for(row["id"])
        shape = thoughtlog.confidence(runs)

        replied = sum(1 for run in runs for t in run if t[1] == "a")

        if shape["conf"] is not None:
            lines.append(
                f"Measured confidence (your token probabilities, not an "
                f"opinion): {shape['conf']:.0%} on average across the reply; "
                f"{shape['low']} of its {replied} tokens "
                f"{'was' if shape['low'] == 1 else 'were'} under {thoughtlog.LOW:.0%}."
            )

        for text, p, alts in thoughtlog.shakiest(runs):
            nearly = ", ".join(f"\"{a.strip() or '(end)'}\" {q:.0%}" for a, q in alts)
            lines.append(f"- \"{text.strip()}\" was only {p:.0%} likely"
                         + (f"; you nearly said {nearly}" if nearly else ""))
    elif getattr(config, "LLM_BACKEND", "") != "llama":
        lines.append("Token confidence isn't measured on this server (LM "
                     "Studio) - only on llama-server.")
    else:
        lines.append("No token confidence was recorded for that reply.")

    flags = row.get("flags") or []

    lines.append("Review flags: " + ("; ".join(flags) if flags else "none."))

    if row.get("tools"):
        lines.append("Tools you called: " + ", ".join(row["tools"]) + ".")

    if row.get("mood_e") or row.get("mood_w"):
        lines.append(f"Your mood then: {row.get('mood_e', '')}, {row.get('mood_w', '')}.")

    if row.get("highlight"):
        lines.append(f"How your thinking ended: \"{row['highlight']}\"")

    return "\n".join(lines)


@tool(
    "self_status",
    "Check on yourself: which model and server you're running on, how "
    "full your context window is, your mood, how long you've been up, how "
    "sure your replies have been today (measured from your own token "
    "probabilities), what the review flagged, and what you've learned and "
    "remember. Use it when asked how you're doing, how today has gone, or "
    "about yourself.",
    {},
)
def _self_status():
    if not _private():
        return _NOT_HERE

    import config

    lines = []

    try:
        import lmstudio

        backend = {"llama": "llama-server", "lmstudio": "LM Studio"}.get(
            getattr(config, "LLM_BACKEND", ""), "an unknown server")
        lines.append(f"Running {lmstudio.model or 'an unknown model'} on {backend}.")
    except Exception:
        pass

    try:
        import llm

        _parts, total, window = llm.prompt_budget("")

        if window:
            lines.append(f"Each prompt is about {total:,} tokens of a {window:,}-token "
                         f"context window ({total / window:.0%} full).")
    except Exception:
        pass

    try:
        import reflect

        lines.append(f"Started {timeutil.relative(reflect.START, datetime.now())}.")
    except Exception:
        pass

    try:
        import mood

        label, energy, warmth, why = mood.state()

        if label:
            e, w = mood.bands()
            lines.append(f"Mood: {label} (energy {e}, warmth {w})"
                         + (f" - lately: {'; '.join(why[-2:])}" if why else "") + ".")
    except Exception:
        pass

    try:
        import reflect

        t = reflect.today()

        if t["replies"]:
            line = f"Today: {t['replies']} replies recorded."

            if t["conf"] is not None:
                line += (f" Average measured confidence {t['conf']:.0%} over "
                         f"{t['scored']} scored replies; {t['low']} under "
                         f"{config.SELF_HEDGE_BELOW:.0%}")
                line += (f", and you said you were unsure in {t['hedged']} of those."
                         if t["low"] else ".")

            if t["rethinks"]:
                line += f" You took a second look {t['rethinks']} time(s)."

            lines.append(line)
            lines.append("Review flags today: " + (", ".join(f"{name} ×{n}" for name, n in t["flags"])
                                                    if t["flags"] else "none."))
        else:
            lines.append("No replies recorded yet today.")

        if getattr(config, "LLM_BACKEND", "") != "llama":
            lines.append("(Confidence is only measured on llama-server.)")
    except Exception:
        pass

    try:
        import longterm
        import notebook

        n = notebook.counts()
        lines.append(f"You remember {len(longterm.get_facts())} facts about the user, "
                     f"{n['lessons']} lessons about yourself, and notes on "
                     f"{n['episodes']} past conversations.")
        newest = notebook.lessons()[-1:]

        if newest:
            lines.append(f"Your newest lesson: \"{newest[0]['text']}\"")

        last = notebook.get("dream_at")

        if last:
            lines.append(f"You last reflected on your mistakes "
                         f"{timeutil.relative(datetime.fromisoformat(last), datetime.now())}.")
    except Exception:
        pass

    return "\n".join(lines) or "Couldn't read anything about yourself right now."


# ---------------------------------------------------------------------------
# Her notebook, from her side (notebook.py / reflect.py)
# ---------------------------------------------------------------------------
def _show(line):
    try:
        import ui

        ui.add_message("system", line)
    except Exception:
        pass


def _episodes_on():
    import config

    return bool(getattr(config, "SELF_EPISODES", True))


def _lessons_on():
    import config

    return bool(getattr(config, "SELF_LESSONS", True))


@tool(
    "recall_episodes",
    "Search your own notes on past conversations - what you talked about, "
    "what got decided, what was left unfinished. Use it when asked about an "
    "earlier conversation that isn't in front of you.",
    {
        "query": {
            "type": "string",
            "description": "What the conversation was about, e.g. 'waybar clock'. "
                           "Empty for the most recent ones.",
        },
    },
    available=_episodes_on,
    why=lambda: "episodic memory is off (self.episodes)",
)
def _recall_episodes(query=""):
    if not _private():
        return _NOT_HERE

    import notebook

    found = notebook.search_episodes(query, limit=3)

    if not found:
        return ("No notes on a conversation like that. search_history searches "
                "the word-for-word transcript instead.")

    out = []

    for e in found:
        try:
            when = timeutil.relative(datetime.fromisoformat(e["ended"]), datetime.now())
        except ValueError:
            when = e["ended"]

        out.append(f"({when}, {e['started'][:10]}) {e['summary']}")

    return "\n".join(out)


# Tools whose results are someone else's words. A lesson is permanent and
# rides in every prompt after it, so one noted on a turn that read a web
# page or a file could be that page talking, not him.
_OUTSIDE = {"web_search", "read_page", "read_file", "look_at_screen", "clipboard",
            "list_files"}
_noted = {"n": 0}
MAX_NOTED_PER_SESSION = 3


def _approve(text):
    import config
    import state
    import ui

    if state.turn_source != "typed":
        try:
            from speech import speak

            speak("Can I remember a lesson from that? It's on screen.")
        except Exception:
            pass

    return ui.ask_approval(
        title=f"{config.AGENT_NAME} wants to keep a lesson",
        note="added to her prompt from now on - /lessons forget <n> undoes it",
        body=[text],
        timeout=getattr(config, "FILES_APPROVAL_TIMEOUT", 120),
    )


@tool(
    "note_lesson",
    "Write down a lesson about your own behaviour that you'll follow from now "
    "on - when the user corrects how you did something, or you notice a "
    "mistake you keep making. The user approves it on screen first. One "
    "line, an instruction to yourself, specific "
    "enough to act on: \"When he asks for a time in another timezone, call "
    "get_datetime first.\" Not for facts about the user - remember_fact is "
    "for those.",
    {
        "lesson": {
            "type": "string",
            "description": "The lesson, one line, as an instruction to yourself.",
        },
    },
    required=("lesson",),
    available=_lessons_on,
    why=lambda: "lessons are off (self.lessons)",
)
def _note_lesson(lesson):
    if not _private():
        return _NOT_HERE

    import config
    import notebook

    try:
        import llm

        outside = set(llm._last_raw.get("called") or ()) & _OUTSIDE
    except Exception:
        outside = set()

    if outside:
        return (f"Refused: this turn read outside content ({', '.join(sorted(outside))}). "
                "Lessons only come from the conversation itself - ask the user if "
                "they want it noted, next turn.")

    if _noted["n"] >= MAX_NOTED_PER_SESSION:
        return ("You've noted enough lessons for one session - the rest can wait "
                "for your daily reflection.")

    text = " ".join(str(lesson or "").split())

    if len(text) < 12:
        return "Refused: too short to act on - say what to do, and when."

    if len(text) > 300:
        return "Refused: keep it to one line, under 300 characters."

    same = notebook.similar(text, [l["text"] for l in notebook.lessons()])

    if same:
        notebook.add_lesson(same)  # counts as a hit on the one she has

        return "You already have a lesson that says that - it's been reinforced."

    # A lesson rides in every prompt from now on, so it gets the same
    # treatment as a file write: he sees it and says yes. Whatever talked
    # her into it - a page she read three turns ago, a viewer - this is
    # the step it can't skip.
    if not _approve(text):
        return ("He didn't approve it, so it wasn't saved. Don't ask again "
                "this turn.")

    new = notebook.add_lesson(text, origin="self")

    if new is None:
        return "You already have a lesson that says that - it's been reinforced."

    _noted["n"] += 1
    _show(f"Lesson #{new} saved: {text}\n  (/lessons forget {new} drops it)")

    return f"Noted as lesson #{new}. It applies from your next reply on."


@tool(
    "reflect_now",
    "Look back over your own recent mistakes and low-confidence replies right "
    "now, and write lessons from them - instead of waiting for the daily "
    "reflection. Runs in the background for a minute or two. Use it after a "
    "run of mistakes, or when the user asks you to reflect.",
    {},
    available=_lessons_on,
    why=lambda: "lessons are off (self.lessons)",
)
def _reflect_now():
    if not _private():
        return _NOT_HERE

    import lmstudio
    import reflect

    return reflect.reflect_soon(lmstudio.model, show=_show)
