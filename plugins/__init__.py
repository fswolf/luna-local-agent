"""Optional add-ons, loaded from this directory at startup.

A plugin connects her to something the core has no business knowing
about - a stream chat, a game, a piece of hardware. Drop a .py file in
here and it is found; delete it and it is gone. Nothing in the core
names a plugin, which is what makes them droppable.

## Writing one

A plugin is a module with a NAME and whichever of these it needs:

    NAME            str    what /<name> on|off calls it. Required.
    SUMMARY         str    one line for /plugins
    available()     bool   can it run right now?
    why_unavailable() str  if not, the reason a person can act on
    start(model)    (ok, message)
    stop()          (ok, message)
    running()       bool
    status()        str    the block /<name> prints with no argument
    command(text)   str    anything else after /<name> - "/minecraft goal
                           build a hut" calls command("goal build a hut")
    prompt_line(private) str  a line for her system prompt while running
                           ("a toy is connected"); private is False for
                           stream chat and Discord without memory
    on_user_text(text)     sees each of your messages before she does
    panic()                you interrupted her (HOME): stop anything physical
    on_camera_open(device) she's about to open the webcam (a picture, the
                           face check, presence starting); keep it quick
    on_camera_close(device) she's done with it, even when the picture failed

Only NAME is required; anything missing gets a sensible default, so a
plugin that only needs start() is four lines long. `plugins/example.py`
is a working one to copy.

Settings live under "plugins" in config.json, keyed by NAME, and the
plugin reads its own with config.plugin_settings(NAME). The core never
learns what those keys mean.

## What a plugin is not allowed to do

A chat plugin hands messages to chatroom.ChatRoom, which caps the tool
list against a ceiling defined in the core. A plugin asking for a wider
one gets the ceiling. That is deliberate: a plugin is a file in a
folder, and a permission a plugin can grant itself is not a permission.

## Loading is defensive on purpose

A plugin that fails to import, or explodes on start, is reported and
skipped. It is an add-on - the assistant works without it, and a broken
one must not be the reason the app won't launch.
"""
import importlib
import os
import pkgutil
import traceback

import logbook

PLUGIN_DIR = os.path.dirname(os.path.abspath(__file__))

_loaded = {}
_broken = {}


def _default(module, attribute, fallback):
    value = getattr(module, attribute, None)

    return value if callable(value) else fallback


class Plugin:
    """One loaded module, with the gaps filled in."""

    def __init__(self, module):
        self.module = module
        self.name = str(getattr(module, "NAME", module.__name__.split(".")[-1]))
        self.summary = str(getattr(module, "SUMMARY", "")).strip()

        self._available = _default(module, "available", lambda: True)
        self._why = _default(module, "why_unavailable", lambda: "")
        self._start = _default(
            module, "start", lambda model: (False, f"{self.name} can't be started")
        )
        self._stop = _default(
            module, "stop", lambda: (False, f"{self.name} can't be stopped")
        )
        self._running = _default(module, "running", lambda: False)
        self._status = _default(module, "status", None)
        self._command = _default(module, "command", None)
        self._prompt_line = _default(module, "prompt_line", None)
        self._on_user_text = _default(module, "on_user_text", None)
        self._panic = _default(module, "panic", None)
        self._on_camera_open = _default(module, "on_camera_open", None)
        self._on_camera_close = _default(module, "on_camera_close", None)

    def available(self):
        try:
            return bool(self._available())
        except Exception:
            return False

    def why_unavailable(self):
        try:
            return str(self._why() or "")
        except Exception as e:
            return str(e)[:120]

    def running(self):
        try:
            return bool(self._running())
        except Exception:
            return False

    def start(self, model):
        try:
            return self._start(model)
        except Exception as e:
            logbook.exception("plugins", "%s failed to start", self.name)

            return False, f"{self.name} failed to start: {e}"

    def stop(self):
        try:
            return self._stop()
        except Exception as e:
            return False, f"{self.name} failed to stop: {e}"

    def command(self, text):
        """None when the plugin has no commands of its own."""
        if self._command is None:
            return None

        try:
            return str(self._command(text))
        except Exception as e:
            logbook.exception("plugins", "%s command failed", self.name)

            return f"{self.name}: that failed ({e})"

    def status(self):
        if self._status is not None:
            try:
                return str(self._status())
            except Exception as e:
                return f"{self.name}: status unavailable ({e})"

        if self.running():
            return f"{self.name}: running"

        problem = self.why_unavailable()

        return f"{self.name}: off ({problem})" if problem else f"{self.name}: off"


def _each_running(attribute):
    for plugin in list(_loaded.values()):
        hook = getattr(plugin, attribute)

        if hook is not None and plugin.running():
            yield plugin, hook


def prompt_lines(private=True):
    """What running plugins want in her system prompt."""
    out = []

    for plugin, hook in _each_running("_prompt_line"):
        try:
            out.append(str(hook(private) or ""))
        except Exception as e:
            logbook.warn("plugins", "%s prompt_line failed: %s", plugin.name, e)

    return "".join(out)


def user_text(text):
    """Your message, to every running plugin that wants it, before the model."""
    for plugin, hook in _each_running("_on_user_text"):
        try:
            hook(text)
        except Exception as e:
            logbook.warn("plugins", "%s on_user_text failed: %s", plugin.name, e)


def _camera(attribute, device):
    for plugin, hook in _each_running(attribute):
        try:
            hook(device)
        except Exception:
            logbook.exception("plugins", "%s %s failed", plugin.name, attribute.lstrip("_"))


def camera_open(device):
    """The webcam is about to open (camera.hooks calls this, with a time limit)."""
    _camera("_on_camera_open", device)


def camera_close(device):
    """The webcam has closed again."""
    _camera("_on_camera_close", device)


def panic():
    """You interrupted her. Anything physical stops."""
    for plugin, hook in _each_running("_panic"):
        try:
            hook()
        except Exception as e:
            logbook.warn("plugins", "%s panic failed: %s", plugin.name, e)


def load():
    """Import every plugin in this directory. Returns the names found."""
    _loaded.clear()
    _broken.clear()

    for entry in sorted(pkgutil.iter_modules([PLUGIN_DIR])):
        # Leading underscore is the convention for shared helpers that
        # live alongside plugins without being one.
        if entry.name.startswith("_"):
            continue

        try:
            module = importlib.import_module(f"{__name__}.{entry.name}")
            plugin = Plugin(module)
            _loaded[plugin.name.lower()] = plugin
        except Exception as e:
            _broken[entry.name] = f"{type(e).__name__}: {e}"
            logbook.warn(
                "plugins", "%s failed to load: %s", entry.name,
                traceback.format_exc(limit=3).replace("\n", " | ")[:400],
            )

    return sorted(_loaded)


def get(name):
    return _loaded.get(str(name or "").strip().lower())


def names():
    return sorted(_loaded)


def broken():
    return dict(_broken)


def start_enabled(model):
    """Start every plugin its config marks enabled. Returns report lines.

    Silent about plugins that are simply off - but never silent about
    one that is switched on and didn't come up. "Why isn't she
    answering chat" should be answerable from the first screen.
    """
    import config

    lines = []

    for name, reason in sorted(_broken.items()):
        lines.append(f"Plugin {name} didn't load: {reason}")

    for name in names():
        plugin = _loaded[name]

        if not config.plugin_settings(plugin.name).get("enabled"):
            continue

        ok, message = plugin.start(model)
        lines.append(message if ok else f"{plugin.name}: {message}")

    return lines


def stop_all():
    for plugin in _loaded.values():
        if plugin.running():
            try:
                plugin.stop()
            except Exception:
                pass


def overview():
    """The /plugins block."""
    if not _loaded and not _broken:
        return "No plugins installed. Drop a .py file in plugins/ to add one."

    lines = []

    for name in names():
        plugin = _loaded[name]

        if plugin.running():
            mark, detail = "on ", plugin.summary
        elif plugin.available():
            mark, detail = "off", plugin.summary or "ready - /%s on" % plugin.name
        else:
            mark, detail = "--", plugin.why_unavailable() or "unavailable"

        lines.append(f"  [{mark}] {plugin.name:12} {detail}")

    for name, reason in sorted(_broken.items()):
        lines.append(f"  [!!] {name:12} didn't load: {reason}")

    return "\n".join(["Plugins:"] + lines)
