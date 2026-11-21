"""Luna's icon in the system tray, beside the clock: open her chat, the
portrait or the settings, switch her voice, push to talk, quit.

Started by her web UI (ui/headless.py, monitor.tray) as a process of its
own, and it talks to her the way her pages do: over her own pages' port on
127.0.0.1 (/chat/state, /chat/tray, /chat/talk, /chat/stop). It ends by
itself when she does.

    python app/tray.py --url http://127.0.0.1:8792

Linux: a StatusNotifierItem over D-Bus (dbus-fast), what KDE, waybar,
GNOME's AppIndicator extension, XFCE and the rest show; a tray that starts
later, or restarts, gets her icon too. Windows and macOS: pystray. Without
the packages it says why and exits 3. Until an icon is showing, closing
her window quits her as before.
"""
import json
import os
import struct
import sys
import threading
import time
import urllib.request
import zlib

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
LOGO = os.path.join(ROOT, "web", "luna-logo.png")
POLL = 2.0          # seconds between looks at her status
GONE = 15           # seconds without an answer before the tray decides she's gone
NO_HOST = 3         # exit code: nowhere to show an icon


# ---------------------------------------------------------------------------
# Talking to her
# ---------------------------------------------------------------------------
class Luna:
    def __init__(self, url):
        self.url = url.rstrip("/")
        self.state = {}
        self.seen = time.monotonic()
        self.lock = threading.Lock()
        self.up = False          # the icon is showing: then she's told so, with each look

    def _call(self, method, path, data=None, timeout=4):
        body = json.dumps(data).encode() if data is not None else None
        req = urllib.request.Request(self.url + path, data=body, method=method,
                                     headers={"Content-Type": "application/json"} if body else {})
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return json.loads(r.read() or b"{}")

    def refresh(self):
        """Her status now. False when she didn't answer."""
        try:
            st = self._call("GET", "/chat/state?head=1" + ("&tray=1" if self.up else ""))
        except Exception:
            return False
        with self.lock:
            self.state = st
            self.seen = time.monotonic()
        return True

    def gone(self):
        return time.monotonic() - self.seen > GONE

    def get(self, key, default=None):
        with self.lock:
            return self.state.get(key, default)

    def act(self, action):
        try:
            if action in ("talk", "stop"):
                self._call("POST", f"/chat/{action}", {})
            else:
                self._call("POST", "/chat/tray", {"action": action})
        except Exception:
            pass
        self.refresh()

    def open_chat(self):
        """Her chat in a window of its own: she opens it, the way /chat and
        her own start do (web/chat_web.open_window, portrait.browser and all)."""
        self.act("chat")


def items(luna):
    """The menu as it should look now: [(id, label, kind, enabled, checked)].
    kind: "label" (status, greyed), "item", "check" or "sep"."""
    name = luna.get("name") or "Luna"
    status = luna.get("status") or "starting"
    model = dict(luna.get("rows") or []).get("Model", "")
    out = [("status", f"{name}: {status}", "label", False, False)]
    if model:
        out.append(("model", f"Model: {model}", "label", False, False))
    out += [("sep1", "", "sep", True, False),
            ("chat", "Open chat", "item", True, False),
            ("portrait", "Portrait", "item", True, False),
            ("settings", "Settings", "item", True, False),
            ("sep2", "", "sep", True, False)]
    if luna.get("can_talk"):
        out.append(("talk", "Done talking" if luna.get("mic") else "Talk (push to talk)", "item", True, False))
    out.append(("stop", "Stop her", "item", bool(luna.get("busy")), False))
    out.append(("voice", "Her voice", "check", True, bool(luna.get("voice_on", True))))
    out += [("sep3", "", "sep", True, False),
            ("quit", f"Quit {name}", "item", True, False)]
    return out


def tooltip(luna):
    name = luna.get("name") or "Luna"
    model = dict(luna.get("rows") or []).get("Model", "")
    return name, f"{luna.get('status') or 'starting'}" + (f" · {model}" if model else "")


def run_action(luna, key):
    if key == "chat":
        luna.open_chat()
    elif key in ("portrait", "settings", "voice", "quit", "talk", "stop"):
        luna.act(key)


# ---------------------------------------------------------------------------
# The icon's pixels, without Pillow: her logo is an 8-bit RGBA PNG
# ---------------------------------------------------------------------------
def read_png(path):
    """(width, height, RGBA bytes) of a non-interlaced 8-bit RGBA or RGB PNG."""
    with open(path, "rb") as f:
        data = f.read()
    if data[:8] != b"\x89PNG\r\n\x1a\n":
        raise ValueError("not a PNG")
    pos, idat, w = 8, b"", 0
    while pos < len(data):
        length, kind = struct.unpack(">I4s", data[pos:pos + 8])
        chunk = data[pos + 8:pos + 8 + length]
        if kind == b"IHDR":
            w, h, depth, color, _c, _f, interlace = struct.unpack(">IIBBBBB", chunk)
            if depth != 8 or color not in (2, 6) or interlace:
                raise ValueError("only 8-bit RGB/RGBA, not interlaced")
            bpp = 4 if color == 6 else 3
        elif kind == b"IDAT":
            idat += chunk
        elif kind == b"IEND":
            break
        pos += 12 + length
    raw, stride = zlib.decompress(idat), w * bpp
    rows, prev = [], bytearray(stride)
    for y in range(h):
        f, line = raw[y * (stride + 1)], bytearray(raw[y * (stride + 1) + 1:(y + 1) * (stride + 1)])
        for i in range(stride):
            a = line[i - bpp] if i >= bpp else 0
            b, c = prev[i], prev[i - bpp] if i >= bpp else 0
            if f == 1:
                line[i] = (line[i] + a) & 255
            elif f == 2:
                line[i] = (line[i] + b) & 255
            elif f == 3:
                line[i] = (line[i] + (a + b) // 2) & 255
            elif f == 4:
                p = a + b - c
                pa, pb, pc = abs(p - a), abs(p - b), abs(p - c)
                line[i] = (line[i] + (a if pa <= pb and pa <= pc else b if pb <= pc else c)) & 255
        rows.append(bytes(line))
        prev = line
    pixels = b"".join(rows)
    if bpp == 3:
        pixels = b"".join(pixels[i:i + 3] + b"\xff" for i in range(0, len(pixels), 3))
    return w, h, pixels


# Her logo is a disc that fills its square, so at the same size it looks bigger
# than the tray icons beside it, which leave a margin: drawn at this much of the
# square, centred, it matches them.
FILL = 0.78


def resize(w, h, rgba, size):
    """An area-averaged size x size copy of a square RGBA image, colours weighted
    by alpha so the soft edge doesn't go dark."""
    out = bytearray(size * size * 4)
    scale = w / size
    for y in range(size):
        y0, y1 = int(y * scale), max(int(y * scale) + 1, int((y + 1) * scale))
        for x in range(size):
            x0, x1 = int(x * scale), max(int(x * scale) + 1, int((x + 1) * scale))
            r = g = b = a = n = 0
            for sy in range(y0, min(y1, h)):
                row = sy * w
                for sx in range(x0, min(x1, w)):
                    i = (row + sx) * 4
                    al = rgba[i + 3]
                    r += rgba[i] * al
                    g += rgba[i + 1] * al
                    b += rgba[i + 2] * al
                    a += al
                    n += 1
            o = (y * size + x) * 4
            if a:
                out[o:o + 4] = bytes((r // a, g // a, b // a, a // n))
    return bytes(out)


def padded(w, h, rgba, size, fill=FILL):
    """The image at fill of a size x size square, centred on transparency."""
    inner = max(1, round(size * fill))
    small = resize(w, h, rgba, inner)
    out = bytearray(size * size * 4)
    off = (size - inner) // 2
    for y in range(inner):
        o = ((y + off) * size + off) * 4
        out[o:o + inner * 4] = small[y * inner * 4:(y + 1) * inner * 4]
    return bytes(out)


def argb_pixmaps(path=LOGO):
    """[(w, h, ARGB32 big-endian)] at a few sizes: what a StatusNotifierItem
    wants (the tray picks the nearest and scales it)."""
    w, h, rgba = read_png(path)
    out = []
    for size in (16, 22, 24, 32, 48, 64):
        px = padded(w, h, rgba, size)
        argb = bytearray(len(px))
        argb[0::4], argb[1::4], argb[2::4], argb[3::4] = px[3::4], px[0::4], px[1::4], px[2::4]
        out.append((size, size, bytes(argb)))
    return out


# ---------------------------------------------------------------------------
# Linux: StatusNotifierItem + com.canonical.dbusmenu
# ---------------------------------------------------------------------------
def run_sni(luna):
    import asyncio

    from dbus_fast import BusType, Variant
    from dbus_fast.aio import MessageBus
    from dbus_fast.service import PropertyAccess, ServiceInterface, dbus_property, method, signal

    loop_ref = {}

    def later(fn, *args):
        """Run a blocking call (HTTP, opening a window) off the bus loop."""
        loop_ref["loop"].run_in_executor(None, fn, *args)

    class Menu(ServiceInterface):
        def __init__(self):
            super().__init__("com.canonical.dbusmenu")
            self.revision = 1
            self.shown = items(luna)
            self.ids = {}

        def _props(self, entry):
            key, label, kind, enabled, checked = entry
            if kind == "sep":
                return {"type": Variant("s", "separator")}
            p = {"label": Variant("s", label.replace("_", "__")), "enabled": Variant("b", enabled and kind != "label"),
                 "visible": Variant("b", True)}
            if kind == "check":
                p["toggle-type"] = Variant("s", "checkmark")
                p["toggle-state"] = Variant("i", 1 if checked else 0)
            return p

        def layout(self):
            self.ids = {i + 1: e[0] for i, e in enumerate(self.shown)}
            children = [Variant("(ia{sv}av)", [i + 1, self._props(e), []]) for i, e in enumerate(self.shown)]
            return [0, {"children-display": Variant("s", "submenu")}, children]

        def update(self):
            now = items(luna)
            if now != self.shown:
                self.shown = now
                self.revision += 1
                self.LayoutUpdated(self.revision, 0)

        @method()
        def GetLayout(self, parent_id: "i", depth: "i", names: "as") -> "u(ia{sv}av)":
            return [self.revision, self.layout()]

        @method()
        def GetGroupProperties(self, ids: "ai", names: "as") -> "a(ia{sv})":
            self.layout()
            return [[i, self._props(self.shown[i - 1])] for i in (ids or self.ids) if 0 < i <= len(self.shown)]

        @method()
        def GetProperty(self, id: "i", name: "s") -> "v":
            props = self._props(self.shown[id - 1]) if 0 < id <= len(self.shown) else {}
            return props.get(name, Variant("s", ""))

        @method()
        def Event(self, id: "i", event_id: "s", data: "v", timestamp: "u"):
            if event_id == "clicked" and id in self.ids:
                later(run_action, luna, self.ids[id])

        @method()
        def EventGroup(self, events: "a(isvu)") -> "ai":
            for id, event_id, _data, _ts in events:
                if event_id == "clicked" and id in self.ids:
                    later(run_action, luna, self.ids[id])
            return []

        @method()
        def AboutToShow(self, id: "i") -> "b":
            return False

        @method()
        def AboutToShowGroup(self, ids: "ai") -> "aiai":
            return [[], []]

        @signal()
        def LayoutUpdated(self, revision, parent) -> "ui":
            return [revision, parent]

        @signal()
        def ItemsPropertiesUpdated(self, updated, removed) -> "a(ia{sv})a(ias)":
            return [updated, removed]

        @dbus_property(access=PropertyAccess.READ)
        def Version(self) -> "u":
            return 3

        @dbus_property(access=PropertyAccess.READ)
        def TextDirection(self) -> "s":
            return "ltr"

        @dbus_property(access=PropertyAccess.READ)
        def Status(self) -> "s":
            return "normal"

        @dbus_property(access=PropertyAccess.READ)
        def IconThemePath(self) -> "as":
            return []

    pixmaps = [list(p) for p in argb_pixmaps()]

    class Item(ServiceInterface):
        def __init__(self):
            super().__init__("org.kde.StatusNotifierItem")
            self.tip = tooltip(luna)

        def update(self):
            tip = tooltip(luna)
            if tip != self.tip:
                self.tip = tip
                self.NewToolTip()
                self.NewTitle()

        @dbus_property(access=PropertyAccess.READ)
        def Category(self) -> "s":
            return "ApplicationStatus"

        @dbus_property(access=PropertyAccess.READ)
        def Id(self) -> "s":
            return "luna"

        @dbus_property(access=PropertyAccess.READ)
        def Title(self) -> "s":
            return f"{self.tip[0]}: {self.tip[1]}"

        @dbus_property(access=PropertyAccess.READ)
        def Status(self) -> "s":
            return "Active"

        @dbus_property(access=PropertyAccess.READ)
        def WindowId(self) -> "i":
            return 0

        @dbus_property(access=PropertyAccess.READ)
        def IconName(self) -> "s":
            return ""

        @dbus_property(access=PropertyAccess.READ)
        def IconPixmap(self) -> "a(iiay)":
            return pixmaps

        @dbus_property(access=PropertyAccess.READ)
        def ToolTip(self) -> "(sa(iiay)ss)":
            return ["", [], self.tip[0], self.tip[1]]

        @dbus_property(access=PropertyAccess.READ)
        def ItemIsMenu(self) -> "b":
            return False             # a left click opens her chat; the menu is a right click

        @dbus_property(access=PropertyAccess.READ)
        def Menu(self) -> "o":
            return "/MenuBar"

        @method()
        def Activate(self, x: "i", y: "i"):
            later(luna.open_chat)

        @method()
        def SecondaryActivate(self, x: "i", y: "i"):
            later(luna.act, "portrait")

        @method()
        def ContextMenu(self, x: "i", y: "i"):
            pass

        @method()
        def Scroll(self, delta: "i", orientation: "s"):
            pass

        @signal()
        def NewTitle(self):
            pass

        @signal()
        def NewIcon(self):
            pass

        @signal()
        def NewToolTip(self):
            pass

        @signal()
        def NewStatus(self) -> "s":
            return "Active"

    WATCHER = "org.kde.StatusNotifierWatcher"

    async def owner(dbus):
        """The watcher's unique bus name now, or None: there's no tray (yet)."""
        try:
            return await dbus.call_get_name_owner(WATCHER)
        except Exception:
            return None

    async def register(bus, name):
        intro = await bus.introspect(WATCHER, "/StatusNotifierWatcher")
        watcher = bus.get_proxy_object(WATCHER, "/StatusNotifierWatcher", intro)
        await watcher.get_interface(WATCHER).call_register_status_notifier_item(name)

    async def main():
        loop_ref["loop"] = asyncio.get_running_loop()
        try:
            bus = await MessageBus(bus_type=BusType.SESSION).connect()
        except Exception as e:
            print(f"No D-Bus session to show a tray icon on ({e.__class__.__name__}: {e})", file=sys.stderr)
            return NO_HOST
        menu, item = Menu(), Item()
        bus.export("/MenuBar", menu)
        bus.export("/StatusNotifierItem", item)
        name = f"org.kde.StatusNotifierItem-{os.getpid()}-1"
        await bus.request_name(name)
        intro = await bus.introspect("org.freedesktop.DBus", "/org/freedesktop/DBus")
        dbus = bus.get_proxy_object("org.freedesktop.DBus", "/org/freedesktop/DBus", intro) \
            .get_interface("org.freedesktop.DBus")
        shown_to, said = None, False
        while True:
            await loop_ref["loop"].run_in_executor(None, luna.refresh)
            if luna.gone():
                bus.disconnect()
                return 0
            # A tray that starts after her (waybar a moment after login) or
            # restarts (plasmashell, waybar reloaded) is a new watcher: the
            # icon is registered with it again, or it would quietly be gone.
            now = await owner(dbus)
            if now != shown_to:
                luna.up = False
                if now:
                    try:
                        await register(bus, name)
                        shown_to, luna.up = now, True
                        print("tray icon up", flush=True)
                    except Exception as e:
                        print(f"The tray wouldn't take her icon ({e.__class__.__name__}: {e})", file=sys.stderr)
                else:
                    shown_to = None
                    if not said:
                        print("No system tray to put her icon in yet (KDE, waybar's tray, XFCE and GNOME with "
                              "the AppIndicator extension all have one); waiting for one.", file=sys.stderr, flush=True)
                        said = True
            menu.update()
            item.update()
            await asyncio.sleep(POLL)

    return asyncio.run(main())


# ---------------------------------------------------------------------------
# Windows and macOS: pystray
# ---------------------------------------------------------------------------
def run_pystray(luna):
    import pystray
    from PIL import Image

    def entry(key):
        def text(_item):
            return next((e[1] for e in items(luna) if e[0] == key), "")

        def shown(_item):
            return any(e[0] == key for e in items(luna))

        def enabled(_item):
            e = next((e for e in items(luna) if e[0] == key), None)
            return bool(e and e[3] and e[2] != "label")

        def checked(_item):
            e = next((e for e in items(luna) if e[0] == key), None)
            return bool(e and e[4])

        kind = {e[0]: e[2] for e in items(luna)}.get(key, "item")
        return pystray.MenuItem(text, lambda _i, _m: threading.Thread(target=run_action, args=(luna, key),
                                                                      daemon=True).start(),
                                checked=checked if key == "voice" else None, enabled=enabled,
                                visible=shown, default=(key == "chat"))

    menu = pystray.Menu(entry("status"), entry("model"), pystray.Menu.SEPARATOR,
                        entry("chat"), entry("portrait"), entry("settings"), pystray.Menu.SEPARATOR,
                        entry("talk"), entry("stop"), entry("voice"), pystray.Menu.SEPARATOR, entry("quit"))
    logo = Image.open(LOGO).convert("RGBA")
    picture = Image.new("RGBA", logo.size, (0, 0, 0, 0))           # the same margin as on Linux
    inner = round(logo.width * FILL)
    picture.paste(logo.resize((inner, inner), Image.LANCZOS), ((logo.width - inner) // 2,) * 2)
    icon = pystray.Icon("luna", picture, "Luna", menu=menu)

    def watch():
        while True:
            luna.refresh()
            if luna.gone():
                icon.stop()
                return
            name, tip = tooltip(luna)
            try:
                icon.title = f"{name}: {tip}"[:120]     # Windows caps a tooltip at 127 characters
                icon.update_menu()
            except Exception:
                pass
            time.sleep(POLL)

    def setup(ic):
        ic.visible = True
        print("tray icon up", flush=True)
        luna.up = True
        threading.Thread(target=watch, daemon=True).start()

    icon.run(setup=setup)          # macOS wants this on the main thread
    return 0


def main():
    args = sys.argv[1:]
    url = args[args.index("--url") + 1] if "--url" in args else "http://127.0.0.1:8792"
    luna = Luna(url)
    deadline = time.monotonic() + 60
    while not luna.refresh():            # she may still be starting
        if time.monotonic() > deadline:
            print(f"Luna isn't answering at {url}", file=sys.stderr)
            return 1
        time.sleep(1)
    if sys.platform.startswith("linux"):
        try:
            import dbus_fast  # noqa: F401
        except ImportError:
            print("The tray icon needs dbus-fast: pip install dbus-fast", file=sys.stderr)
            return NO_HOST
        return run_sni(luna)
    try:
        import pystray  # noqa: F401
        from PIL import Image  # noqa: F401
    except ImportError:
        print("The tray icon needs pystray and pillow: pip install pystray pillow", file=sys.stderr)
        return NO_HOST
    return run_pystray(luna)


if __name__ == "__main__":
    sys.exit(main())
