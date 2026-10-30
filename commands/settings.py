"""Settings and tools: /settings, /preset, /set, /tools, /tooltest, /context, /allow, /mcp,
/plugins.

Part of the commands package; see commands/__init__.py.
"""
import threading

import config
from core import logbook
import plugins
from web import portrait_window
import ui

from . import ctx


def handle(text):
    """True when text was one of these commands (and it ran)."""
    if text == "/settings":

        from web import settings_web

        if not config.MONITOR_ENABLED:
            ui.add_message("system", "The settings page needs the live monitor - set monitor.enabled "
                           "to true in config.json and restart. Tab three times has the everyday ones.")
            return True


        portrait_window.quiet_open(settings_web.url())     # its output kept off her screen
        ui.add_message("system", f"Settings: {settings_web.url()}")
        return True

    if text == "/preset" or text.startswith("/preset "):
        from web import settings_web
        from config.presets import PRESETS

        name = text[len("/preset"):].strip().lower()

        if not name:
            ui.add_message("system", "\n".join(
                ["Presets (/preset <name>):"]
                + [f"  {n}: {p['about']}" for n, p in PRESETS.items() if p.get("kind") != "size"]
                + ["Model size (one of these as well):"]
                + [f"  {n}: {p['about']}" for n, p in PRESETS.items() if p.get("kind") == "size"]))
            return True

        _ok, said, _entry = settings_web.preset(name)
        ui.add_message("system", said)
        return True

    if text == "/set" or text.startswith("/set "):
        parts = text.split(None, 2)

        if len(parts) == 1:
            grouped = {}

            for path in sorted(config.SETTINGS):
                section = path.split(".")[0] if "." in path else ""
                grouped.setdefault(section, []).append(path)

            lines = ["Change any of these with /set <name> <value> (the settings pane, "
                     "Tab three times, lists every setting with what it does):"]

            for section, paths in grouped.items():
                lines.append(f"  [{section or 'general'}]")

                for path in paths:
                    _name, live = config.SETTINGS[path]
                    lines.append("    {:32} {}{}".format(
                        path, config.current(path),
                        "" if live else "   (needs a restart)",
                    ))

            ui.add_message("system", "\n".join(lines))
            return True

        from config.schema import SCHEMA

        if len(parts) == 2:
            path = parts[1]

            if path not in config.SETTINGS and path not in SCHEMA:
                ui.add_message("system", f"No setting called {path!r}. /set lists them; "
                               "the settings pane (Tab three times) has every one.")
                return True

            ui.add_message("system", f"{path} = {config.current(path)}")
            return True

        path, value = parts[1], parts[2]

        try:
            # the table's settings may apply now; any other one the schema
            # knows (plugins, the theme...) is saved for the next start
            applied, live = (config.save_setting(path, value) if path in config.SETTINGS
                             else config.save_any(path, value) if path in SCHEMA
                             else config.save_setting(path, value))
        except ValueError as e:
            ui.add_message("system", f"Couldn't set that: {e}")
            return True
        except OSError as e:
            ui.add_message("system", f"Couldn't write config.json: {e}")
            return True

        # What the settings pane does after a change, the same here: stt.mode
        # tells the hands-free loop, the portrait's settings tell an open
        # portrait (background, framing, lights...). It says if that fails.
        from ui import settings_pane

        settings_pane._after(path, applied)

        ui.add_message(
            "system",
            "{} = {}{}".format(
                path, applied,
                " - saved" if live else " - saved, takes effect on restart",
            ),
        )
        return True

    if text == "/tools":
        import llm

        if not llm.tools_active():
            ui.add_message(
                "system",
                "Tool calling is off or unsupported by this model - "
                "keyword triggers are handling reminders and search.",
            )
            return True

        import tools as tool_registry

        live, possible = tool_registry.budget()
        saved = possible - live
        header = f"{live} tokens of tool schemas in every prompt"

        if saved:
            header += f" ({saved} saved by switches)"

        lines = [header + " - Tab twice to change them:"]

        # A tool that isn't offered is invisible otherwise, and "why
        # didn't she look at my screen" has exactly one answer worth
        # printing: because she wasn't told she could.
        for name, on, ready, why, cost in tool_registry.inventory():
            if not ready:
                lines.append(f"   -- {name:<16} {why}")
            else:
                lines.append(
                    f"  {'on ' if on else 'off'} {name:<16} {cost:>5} tok"
                )

        ui.add_message("system", "\n".join(lines))
        return True

    if text == "/tooltest":
        import diagnose

        ui.add_message(
            "system",
            "Running the tool-calling check - {} requests, a minute or "
            "two on a local model. Results appear as they finish. "
            "Nothing is scheduled or remembered.".format(len(diagnose.PROBES) * 2),
        )

        def check():
            import diagnose

            def show(line):
                # One message per line, as it happens - a local model
                # takes long enough that waiting for the whole report
                # looks identical to a hang.
                if line.strip():
                    ui.add_message("system", line)
                    logbook.info("diagnose", "%s", line)

            try:
                lines = diagnose.tool_calling(ctx.model, report=show)

                # A clean sweep is the interesting case: the model can
                # call tools, but doesn't when it matters. The only
                # thing left between the probe and a real turn is the
                # prompt, so bisect it.
                if any("healthy here" in line for line in lines):
                    show("")
                    diagnose.prompt_bisect(ctx.model, report=show)
            except Exception as e:
                logbook.exception("diagnose", "tool check failed")
                ui.add_message("system", f"Tool check failed: {e}")

        threading.Thread(target=check, daemon=True).start()
        return True

    if text.strip() in ("/plugins", "/plugin"):
        ui.add_message("system", plugins.overview())
        return True

    if text == "/context":
        import llm

        try:
            parts, total, window = llm.prompt_budget()
        except Exception as e:
            ui.add_message("system", f"Couldn't size the prompt: {e}")
            return True

        rows = "\n".join(f"  {v:6d}  {k}" for k, v in parts.items())
        verdict = (
            f"  {total:6d}  total, of a {window}-token context "
            f"({100 * total // window}% full)" if window else
            f"  {total:6d}  total (LM Studio didn't report the context length)"
        )
        warning = ""

        if window and total >= window * 0.8:
            warning = (
                "\nThat's too close. Options: /clear the conversation, lower "
                "history.max_raw_messages or long_term_memory.context_facts "
                "with /set, or raise the context length in LM Studio."
            )

        ui.add_message(
            "system",
            f"Roughly what every turn sends (tokens):\n{rows}\n{verdict}{warning}",
        )
        return True

    if text in ("/allow", "/allow off"):
        from tools import files as file_tools

        if text.endswith("off"):
            file_tools.allow_all(False)
            ui.add_message("system", "File changes ask again.")
        else:
            saved = str(getattr(config, "FILES_WRITE", "ask")).lower()
            ui.add_message("system", "File changes: " + (
                "allowed (Write is set to allow in the tools pane - space it back to ask)"
                if saved == "allow" else
                "allowed without asking until restart (her own folder, ~/.config and "
                "~/.local still ask) - /allow off" if file_tools.allow_all()
                else "every one asks. Press A on a file popup to stop asking this session.")
                + " Commands always ask.")
        return True

    if text == "/mcp":
        from core import mcpclient

        ui.add_message("system", mcpclient.status())
        return True

    return False
