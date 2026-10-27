"""Her portrait: /monitor, /holo, /lights, /portrait and its subcommands.

Part of the commands package; see commands/__init__.py.
"""
import config
from web import livefeed
from web import portrait_window
import ui


def handle(text):
    """True when text was one of these commands (and it ran)."""
    if text == "/monitor":


        if not config.MONITOR_ENABLED:
            ui.add_message("system", "The live monitor is off - set monitor.enabled "
                           "to true in config.json and restart.")
            return True


        portrait_window.quiet_open(livefeed.url())
        ui.add_message("system", f"Live monitor: {livefeed.url()}")
        return True

    if text in ("/holo", "/holo on", "/holo off"):

        word = text.split()[1] if " " in text else ("off" if config.PORTRAIT_HOLOGRAM_ENABLED else "on")
        config.save_setting("portrait.hologram.enabled", "true" if word == "on" else "false")
        livefeed.emit("holo", on=word == "on")
        ui.add_message("system", f"Portrait hologram {word} (saved; an open portrait switches now).")
        return True

    if text in ("/lights", "/lights on", "/lights off"):

        word = text.split()[1] if " " in text else ("off" if config.PORTRAIT_LIGHTS_ENABLED else "on")
        config.save_setting("portrait.lights.enabled", "true" if word == "on" else "false")
        livefeed.lights_changed()
        ui.add_message("system", f"Light strips {word} (saved; an open portrait switches now).")
        return True

    if text == "/portrait models" or text.startswith("/portrait use"):

        found = livefeed.portrait_models()
        want = text[len("/portrait use"):].strip().lower() if text.startswith("/portrait use") else ""

        if not want:
            ui.add_message("system", "\n".join(
                ["Portrait models (in portrait/models):"]
                + [f"  {i}. {m}" + ("  <- in use" if m == config.PORTRAIT_MODEL else "")
                   for i, m in enumerate(found, 1)]
                + ["  /portrait use <number or name> switches"] if found else
                ["No models in portrait/models - drop a Live2D folder or a .vrm in there."]))
            return True

        pick = (found[int(want) - 1] if want.isdigit() and 0 < int(want) <= len(found)
                else next((m for m in found if want in m.lower()), None))

        if not pick:
            ui.add_message("system", f"No model matching {want!r} - /portrait models lists them.")
            return True

        config.save_setting("portrait.model", pick)
        livefeed.emit("reload")
        ui.add_message("system", f"Portrait model: {pick} (saved; an open portrait reloads now).")
        return True

    if text == "/portrait gestures" or text.startswith("/portrait gestures "):
        from life import gestures

        want = text[len("/portrait gestures"):].strip().lower()
        if want in gestures.MODES:
            config.save_setting("portrait.gestures", want)
            livefeed.gesture_mode_changed()
        elif want:
            ui.add_message("system", f"Gesture modes: {', '.join(gestures.MODES)}.")
            return True
        ui.add_message("system", f"Portrait gestures: {gestures.mode()} "
                       f"(tags: she picks / meaning: embedding model / keywords / off). "
                       f"Chat gestures {'on' if config.PORTRAIT_CHAT_GESTURES else 'off'}.")
        return True

    if text == "/portrait frame" or text.startswith("/portrait frame "):

        want = text[len("/portrait frame"):].strip().lower()
        if want in config.FRAMES or want == "face":
            config.save_setting("portrait.frame", want)
            livefeed.emit("frame", frame=want)
        elif want:
            ui.add_message("system", "Framing: bust (head and shoulders) or full (all of her).")
            return True
        ui.add_message("system", f"Portrait framing: {config.PORTRAIT_FRAME} "
                       "(bust: head and shoulders / full: all of her). The tools pane switches it too.")
        return True

    if text.startswith("/portrait meaning "):
        from life import gestures

        pick, scores = gestures.classify(text[len("/portrait meaning "):])
        ui.add_message("system", "No embedding server answering." if scores is None else
                       f"{pick or 'no gesture'}: " + ", ".join(
                           f"{k} {v:.3f}" for k, v in sorted(scores.items(), key=lambda kv: -kv[1]))
                       + f"  (margin over none: {config.PORTRAIT_MEANING_MARGIN})")
        return True

    if text.startswith("/portrait ") and len(text.split()) == 2 and text.split()[1] not in (
            "models", "obs", "gestures"):
        from life import gestures as _g

        _GESTURES = tuple(_g.all_names())
        name = text.split()[1].replace("-", "_")
        if name not in _GESTURES and name not in {c["name"] for c in livefeed.portrait_clips()}:
            ui.add_message("system", f"No gesture or clip called {name!r} - built in: "
                           f"{', '.join(_GESTURES)}; clips go in portrait/animations.")
            return True
        livefeed.emit("gesture", name=name)
        ui.add_message("system", f"Portrait: {name} (3D models only).")
        return True

    if text in ("/portrait", "/portrait obs"):
        portrait_window.toggle(obs=text.endswith("obs"))
        return True

    return False
