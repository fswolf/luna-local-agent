"""Hearing, speaking and seeing: /look, /mic, /voice, /barge, /wake.

Part of the commands package; see commands/__init__.py.
"""
import requests

import config
from voice import speech
import ui
from senses import vision
from voice import wakeword


def handle(text):
    """True when text was one of these commands (and it ran)."""
    if text.startswith("/look"):
        argument = text[5:].strip()

        if not vision.available():
            ui.add_message("system", f"Can't look: {vision.why_unavailable()}")
            return True

        if argument in ("", "list", "windows"):
            # What she'd pick, and what else she could have picked.
            open_windows = vision.windows()

            if not open_windows:
                listing = "  (hyprctl listed nothing she can look at)"
            else:
                listing = "\n".join(
                    "  {} {} - {}".format(
                        "*" if index == 0 else " ",
                        (w.get("class") or "?"),
                        (w.get("title") or "")[:48],
                    )
                    for index, w in enumerate(open_windows[:10])
                )

            ui.add_message(
                "system",
                "Typed at her, \"my screen\" means the whole screen.\n"
                "By voice, it means the focused window (* below).\n"
                "She can also be asked for one by name:\n"
                f"{listing}\n"
                "Try: /look full | /look select | /look <name>",
            )
            return True

        if argument in ("full", "active", "select"):
            region, window = argument, None
        else:
            region, window = "auto", argument

        image, detail = vision.capture(region, window=window)

        if image is None:
            ui.add_message("system", f"Screenshot failed: {detail}")
            return True

        # Thrown away again - this is a check that grim works and that
        # it grabbed the right thing, not a turn.
        vision.take()

        ui.add_message("system", f"Captured {detail}. That's what she'd see.")
        return True

    if text == "/mic":
        levels = speech.levels

        if levels.get("backend") == "silero":
            ui.add_message(
                "system",
                "vad=silero | speech above {:.2f}, ends below {:.2f} | "
                "last peak={:.4f} | triggered={} | captured={:.1f}s | mode={}".format(
                    levels["start"], levels["continue"], levels["peak"],
                    levels["triggered"], levels["speech_seconds"],
                    levels.get("mode", "?"),
                ),
            )
        else:
            ui.add_message(
                "system",
                "vad=energy | noise floor={:.4f} | start>{:.4f} | "
                "continue>{:.4f} | last peak={:.4f} | triggered={} | "
                "captured={:.1f}s | mode={}".format(
                    levels["noise_floor"], levels["start"], levels["continue"],
                    levels["peak"], levels["triggered"], levels["speech_seconds"],
                    levels.get("mode", "?"),
                ),
            )
        return True

    if text.startswith("/voice"):
        wanted = text[6:].strip()

        def show():
            """Ask the server what it has. It is the only thing that
            knows - a blend named in the server's blends.json is real to
            it and invisible from here, so listing a hardcoded set would
            be wrong the moment anyone added one."""
            try:

                data = requests.get(
                    f"{config.TTS_URL}/voices", timeout=5
                ).json()
            except Exception as e:
                return f"Couldn't ask {config.TTS_URL} what voices it has: {e}"

            offered = data.get("voices") or []
            recipes = data.get("blends") or {}
            lines = [f"Voice: {config.VOICE}", ""]

            if recipes:
                lines.append("  blends")

                for name in sorted(recipes):
                    mark = "*" if name == config.VOICE else " "
                    lines.append(f"  {mark} {name:<16} {recipes[name]}")

                lines.append("")

            plain = [v for v in offered if v not in recipes]

            if plain:
                lines.append("  voices")
                # Four to a row; thirty of them one per line is a wall.
                for index in range(0, len(plain), 4):
                    row = plain[index:index + 4]
                    lines.append("    " + "  ".join(f"{v:<14}" for v in row))

            lines.append("")
            lines.append("  /voice <name>            switch, and save it")
            lines.append("  /voice af_bella:6,af_sky:4   blend inline")

            return "\n".join(lines)

        if not wanted:
            ui.add_message("system", show())
            return True

        was = config.VOICE

        try:
            # Not validated against the list on purpose: an inline blend
            # is a perfectly good voice and will never appear in it.
            config.save_setting("voice", wanted)
        except Exception as e:
            ui.add_message("system", f"Couldn't save that: {e}")
            return True

        ui.set_voice(wanted)
        ui.add_message(
            "system",
            f"Voice: {was} -> {wanted}. Applies to the next thing she says.",
        )
        return True

    if text == "/barge":
        if not speech.barge_in_available():
            ui.add_message(
                "system",
                "Barge-in is off - it needs Silero ({}), and stt.barge_in "
                "in agent.json set to true.".format(speech.vad_backend),
            )
            return True

        levels = speech.levels
        ui.add_message(
            "system",
            "barge-in on | her level at your mic={:.4f} | you need "
            "{:.4f} to cut in | loudest you hit={:.4f} | best speech "
            "score={:.2f}\nToo eager: raise stt.barge_in_margin. Won't "
            "trigger: lower it, or wear headphones.".format(
                levels["barge_baseline"],
                levels["barge_baseline"] * config.STT_BARGE_IN_MARGIN,
                levels["barge_peak"],
                levels["barge_probability"],
            ),
        )
        return True

    if text == "/wake":
        if not wakeword.enabled():
            ui.add_message(
                "system",
                'Wake word is off. Turn it on with a "wake_word" block in '
                "agent.json - see voice/wakeword.py for how to get a model.",
            )
            return True

        if not wakeword.available():
            ui.add_message("system", f"Wake word not loaded: {wakeword.label()}")
            return True

        ui.add_message(
            "system",
            'listening for "{}" | fires above {:.2f} | best score so far '
            "{:.2f} | last frame {:.2f} | detections this session {}".format(
                wakeword.label(), config.WAKE_WORD_THRESHOLD,
                wakeword.scores["best"], wakeword.scores["last"],
                wakeword.scores["detections"],
            ),
        )
        return True

    return False
