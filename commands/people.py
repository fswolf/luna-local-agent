"""Who's there: /camera, /presence, /people.

Part of the commands package; see commands/__init__.py.
"""
import threading

import config
from senses import facecheck
from senses import presence
import ui


def handle(text):
    """True when text was one of these commands (and it ran)."""
    if text == "/camera" or text.startswith("/camera "):
        from senses import camera
        import tools

        word = text[len("/camera"):].strip().lower()

        if word in ("on", "off"):
            tools.set_enabled("look_at_camera", word == "on")
            ui.add_message("system", f"Camera {word}." + (
                "" if word == "off" or camera.available() else f" (not usable yet: {camera.why_unavailable()})"))
        elif word == "list":
            ui.set_status("Looking for cameras...")
            found = camera.cameras()
            ui.set_status("")
            ui.add_message("system", "\n".join(
                ["Cameras that open:"] + [f"  {i}: {size}" + ("  <- in use" if i == config.CAMERA_DEVICE else "")
                                          for i, size in found]
                + ["  /set camera.device <n> picks one (or a camera server's URL)"] if found else
                ["No camera opened." + (f" ({camera.why_unavailable()})" if camera._cv2() is None else "")]))
        elif word == "test":
            data, what = camera.grab()
            ui.add_message("system", f"Camera works: {what}. Nothing was sent or saved." if data
                           else f"Camera test failed: {what}")
        else:
            on = tools.enabled("look_at_camera")
            usable = camera.available()
            ui.add_message("system", "\n".join([
                f"Camera: {'on' if on else 'off'} (tools pane, Camera group, or /camera on|off)",
                f"  device {config.CAMERA_DEVICE}, width {config.CAMERA_WIDTH}",
                "  ready" if usable else f"  not usable: {camera.why_unavailable()}",
                "  /camera list | /camera test"]))
        return True

    if text == "/presence" or text.startswith("/presence "):

        word = text[len("/presence"):].strip().lower()

        if word in ("on", "off"):
            config.save_setting("camera.presence.enabled", "true" if word == "on" else "false")
            if word == "on":
                started = presence.start()
                ui.add_message("system", "Presence on: she'll notice when someone's in front of the camera."
                               if started else "Presence saved as on, but it didn't start: "
                               + " ".join(presence.status()))
            else:
                presence.stop()
                ui.add_message("system", "Presence off. The camera is free.")
        else:
            ui.add_message("system", "\n".join(presence.status()))
        return True

    if text == "/people" or text.startswith("/people "):
        from senses import people
        from senses import voices

        words = text.split()

        if len(words) >= 4 and words[1] == "enroll" and words[2] in ("face", "voice"):
            name = " ".join(words[3:])

            if name.strip().lower() == people.STRANGER:
                ui.add_message("system", f"\"{people.STRANGER}\" is what she calls someone she doesn't know: pick a name.")
                return True

            if not config.USER_NAME:
                ui.add_message("system", "Put your own name in agent.json's user block first "
                               "(\"user\": {\"name\": ...}): it's how she knows which enrolled person is you.")

            if words[2] == "voice":
                _ok, said = voices.enroll(name)
                ui.add_message("system", said)
                return True

            def _enroll():
                ui.add_message("system", f"Look at the camera, {name}. Turn your head a little "
                               "now and then (up to 20 seconds)...")
                ok, said = presence.enroll(name)
                ui.add_message("system", said)

            threading.Thread(target=_enroll, daemon=True, name="people-enroll").start()
            return True

        if len(words) >= 3 and words[1] in ("guest", "meet"):
            _ok, said = people.meet(" ".join(words[2:]))
            ui.add_message("system", said)
            return True

        if len(words) >= 3 and words[1] == "keep":
            _ok, said = people.keep(" ".join(words[2:]))
            ui.add_message("system", said)
            return True

        if len(words) == 2 and words[1] == "check":
            if not facecheck.enabled():
                ui.add_message("system", "The face check is off: /set people.face_check true to try it.")
                return True

            def _look():
                name = facecheck.check("asked", force=True)
                ui.add_message("system", f"Face check: {name}." if name else facecheck.status())

            threading.Thread(target=_look, daemon=True, name="facecheck-asked").start()
            return True

        if len(words) == 2 and words[1] == "cancel":
            job = voices.cancel()
            ui.add_message("system", f"Stopped taking {job['name']}'s voice prints." if job
                           else "No voice enrolment running.")
            return True

        if len(words) >= 3 and words[1] == "forget":
            kind = words[-1] if words[-1] in ("face", "voice") and len(words) >= 4 else None
            name = " ".join(words[2:-1] if kind else words[2:])
            gone = people.forget(name, kind) or (kind is None and people.forget_guest(name))
            ui.add_message("system", (f"Forgot {name}'s {kind} prints." if kind else f"Forgot {name}.")
                           if gone else f"Nobody called {name} (or no {kind} prints).")
            return True

        found = people.everyone()
        ui.add_message("system", "\n".join(
            (["People she knows:"] + [f"  {n}{' (' + p['pronouns'] + ')' if p.get('pronouns') else ''}: "
                                       f"{len(p.get('face') or [])} face, {len(p.get('voice') or [])} voice prints, "
                                       f"{len(p.get('facts') or [])} facts"
                                       for n, p in found.items()] if found else ["Nobody enrolled yet."])
            + (["Met this session (forgotten on restart; /people keep <name> to keep): "
                + ", ".join(f"{g['name']} ({', '.join(k for k in ('face', 'voice') if g.get(k)) or 'no prints'}, "
                            f"{len(g.get('facts') or [])} facts)" for g in people.session_guests())]
               if people.session_guests() else [])
            + ["  " + voices.status(), "  " + presence.status()[0], "  " + facecheck.status(),
               "  /people enroll face|voice <name> | /people forget <name> [face|voice] | /people cancel"
               " | /people check | /people guest <name> | /people keep <name>"]))
        return True

    return False
