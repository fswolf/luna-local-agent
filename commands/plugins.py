"""Any loaded plugin answers to its own name: /pomf on, /youtube off, /minecraft goal ...
Tried last, so a core command always wins over a plugin with the same name.

Part of the commands package; see commands/__init__.py.
"""
import config
import plugins
import ui

from . import ctx


def handle(text):
    """True when text was one of these commands (and it ran)."""
    if text.startswith("/"):
        word, _, argument = text[1:].strip().partition(" ")
        plugin = plugins.get(word)

        if plugin is not None:
            raw = argument.strip()
            argument = raw.lower()

            if argument in ("on", "start"):
                ok, message = plugin.start(ctx.model)
            elif argument in ("off", "stop"):
                from ui.tools_pane import _plugin_off

                ok, message = _plugin_off(plugin)   # saved off even if it never connected
            else:
                # Anything else is the plugin's own command, if it has any
                # ("/minecraft goal build a hut"); otherwise its status.
                answer = plugin.command(raw) if raw else None
                ui.add_message("system", answer if answer is not None else plugin.status())
                return True

            if ok:
                try:
                    config.set_plugin_enabled(
                        plugin.name, argument in ("on", "start")
                    )
                    message += " (saved)"
                except Exception:
                    pass

            ui.add_message("system", message)
            return True

    return False
