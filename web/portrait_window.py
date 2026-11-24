"""The window /portrait opens: her portrait on its own, with no address bar.

A Chromium-style browser's --app window does that (on the PATH, then as a
Flatpak). Firefox has no app mode, so it gets a profile of her own whose
userChrome.css hides every toolbar. Each runs on its own profile, so it's
a process of its own that /portrait can close again, never a tab handed to
a browser that's already open. portrait.browser overrides all of it. Every
window opened here (open_app: her chat, the pose studio, the live monitor)
is closed with her when she quits (close()).

Each profile is one window: asking again while it's open (the tray's Open
chat, the launcher run a second time) brings that window to the front
instead of starting the browser again on a profile it already holds,
which Firefox refuses ("already running, but is not responding").

Whatever starts here starts with its output thrown away: a browser started
from Luna's process would otherwise print its warnings ("Safe Browsing
server returned a 400...") straight over her screen.
"""
import os
import sys

_APP_BROWSERS = ("chromium", "chromium-browser", "chromium-freeworld", "google-chrome-stable",
                 "google-chrome", "brave-browser", "brave-browser-stable", "brave",
                 "microsoft-edge", "vivaldi", "thorium-browser")
# The same browsers installed as a Flatpak (not on the PATH)
_APP_FLATPAKS = ("com.brave.Browser", "org.chromium.Chromium", "com.google.Chrome",
                 "io.github.ungoogled_software.ungoogled_chromium", "com.microsoft.Edge",
                 "com.vivaldi.Vivaldi")
_FIREFOX_FLATPAK = "org.mozilla.firefox"

# Where macOS and Windows put them, since there they're seldom on the PATH:
# (folder under /Applications or ~/Applications, the program inside it) on a
# Mac, and a path under Program Files or the user's own AppData on Windows.
# Edge comes with Windows, so a Windows machine always has an app window.
_MAC_APPS = (("Google Chrome.app", "Google Chrome"), ("Brave Browser.app", "Brave Browser"),
             ("Chromium.app", "Chromium"), ("Microsoft Edge.app", "Microsoft Edge"),
             ("Vivaldi.app", "Vivaldi"))
_MAC_FIREFOX = ("Firefox.app", "firefox")
_WIN_APPS = (r"Google\Chrome\Application\chrome.exe", r"BraveSoftware\Brave-Browser\Application\brave.exe",
             r"Chromium\Application\chrome.exe", r"Vivaldi\Application\vivaldi.exe",
             r"Microsoft\Edge\Application\msedge.exe")
_WIN_FIREFOX = r"Mozilla Firefox\firefox.exe"

# A Firefox profile of her own with every toolbar hidden: the nearest Firefox
# gets to Chromium's --app window (it has no app mode of its own)
_FIREFOX_PREFS = """user_pref("toolkit.legacyUserProfileCustomizations.stylesheets", true);
user_pref("browser.shell.checkDefaultBrowser", false);
user_pref("browser.startup.homepage_override.mstone", "ignore");
user_pref("browser.aboutwelcome.enabled", false);
user_pref("browser.sessionstore.resume_from_crash", false);
user_pref("browser.tabs.inTitlebar", 0);
user_pref("datareporting.policy.dataSubmissionEnabled", false);
user_pref("browser.safebrowsing.malware.enabled", false);
user_pref("browser.safebrowsing.phishing.enabled", false);
user_pref("browser.safebrowsing.downloads.enabled", false);
"""
_FIREFOX_CSS = """#TabsToolbar, #nav-bar, #PersonalToolbar, #titlebar, #sidebar-header,
#notifications-toolbar, .browserContainer > findbar { visibility: collapse !important; }
"""


def _flatpak_has(app):
    import shutil
    import subprocess

    if not sys.platform.startswith("linux") or not shutil.which("flatpak"):
        return False
    try:
        return subprocess.run(["flatpak", "info", app], stdout=subprocess.DEVNULL,
                              stderr=subprocess.DEVNULL, timeout=3).returncode == 0
    except (OSError, subprocess.SubprocessError):
        return False


def _installed(firefox=False):
    """A browser where macOS or Windows installs it, or None (and None on Linux,
    where they're on the PATH or a Flatpak)."""
    home = os.path.expanduser("~")
    if sys.platform == "darwin":
        for folder in ("/Applications", os.path.join(home, "Applications")):
            for app, exe in ((_MAC_FIREFOX,) if firefox else _MAC_APPS):
                path = os.path.join(folder, app, "Contents", "MacOS", exe)
                if os.path.isfile(path):
                    return path
    elif sys.platform.startswith("win"):
        roots = [os.environ.get(v) for v in ("PROGRAMFILES", "PROGRAMFILES(X86)", "LOCALAPPDATA")]
        for rel in ((_WIN_FIREFOX,) if firefox else _WIN_APPS):
            for root in filter(None, roots):
                path = os.path.join(root, rel)
                if os.path.isfile(path):
                    return path
    return None


def _firefox_profile(base):
    """A profile folder with the prefs and the toolbar-hiding CSS in it."""
    os.makedirs(os.path.join(base, "chrome"), exist_ok=True)
    with open(os.path.join(base, "user.js"), "w", encoding="utf-8") as f:
        f.write(_FIREFOX_PREFS)
    with open(os.path.join(base, "chrome", "userChrome.css"), "w", encoding="utf-8") as f:
        f.write(_FIREFOX_CSS)
    return base


def command(url, w, h, profile="luna-portrait"):
    """The command that opens the portrait in a window of its own, with no
    address bar, or None. A Chromium-style browser's --app window first (on
    the PATH, then as a Flatpak), else Firefox with a profile that hides
    its toolbars. Each gets its own profile, so it's its own process: one
    /portrait can close again, not a tab in a browser that's already open.
    profile names that profile: the studio (./studio.sh) has its own, so
    it's a window of its own beside the portrait's."""
    import shutil

    home = os.path.expanduser("~")
    app = [f"--app={url}", f"--window-size={w},{h}", "--no-first-run", "--no-default-browser-check"]

    found = next((b for b in _APP_BROWSERS if shutil.which(b)), None) or _installed()
    if found:
        return [found, f"--user-data-dir={os.path.join(home, '.cache', profile)}"] + app

    for flatpak in _APP_FLATPAKS:
        if _flatpak_has(flatpak):
            # inside the sandbox it can always write its own ~/.var/app folder
            folder = os.path.join(home, ".var", "app", flatpak, "cache", profile)
            return ["flatpak", "run", flatpak, f"--user-data-dir={folder}"] + app

    firefox = shutil.which("firefox") or _installed(firefox=True)
    if firefox:
        folder = _firefox_profile(os.path.join(home, ".cache", profile + "-firefox"))
        return [firefox, "--new-instance", "--no-remote", "--profile", folder,
                "--width", str(w), "--height", str(h), url]
    if _flatpak_has(_FIREFOX_FLATPAK):
        folder = _firefox_profile(os.path.join(home, ".var", "app", _FIREFOX_FLATPAK,
                                               "cache", profile))
        return ["flatpak", "run", _FIREFOX_FLATPAK, "--new-instance", "--no-remote",
                "--profile", folder, "--width", str(w), "--height", str(h), url]
    return None


def _profile_dirs(profile):
    """Where command() keeps this profile, for each browser it may have used."""
    home = os.path.expanduser("~")
    return [os.path.join(home, ".cache", profile), os.path.join(home, ".cache", profile + "-firefox")]


def _alive(pid):
    try:
        os.kill(pid, 0)
        return True
    except PermissionError:
        return True
    except (OSError, ValueError):
        return False


def _holder(profile):
    """The pid of a browser that has this profile open, or None: one this run
    didn't start (left by a Luna that was killed, not quit). Firefox and
    Chromium each leave a lock naming it while they run: Firefox's "lock"
    (ip:+pid), Chromium's "SingletonLock" (host-pid). Linux and macOS only;
    a Flatpak's sandbox has its own pids, so its folders aren't looked at."""
    if os.name == "nt":
        return None
    for folder in _profile_dirs(profile):
        for name, sep in (("lock", "+"), ("SingletonLock", "-")):
            try:
                target = os.readlink(os.path.join(folder, name))
            except OSError:
                continue
            tail = target.rsplit(sep, 1)[-1]
            if tail.isdigit() and _alive(int(tail)):
                return int(tail)
    return None


def _group(pid):
    """The pid and every process in its group: a browser's windows can belong
    to a child it started (open_app gives each its own session)."""
    pids = {pid}
    try:
        for entry in os.listdir("/proc"):
            if entry.isdigit():
                try:
                    with open(f"/proc/{entry}/stat", encoding="utf-8", errors="replace") as f:
                        fields = f.read().rsplit(")", 1)[1].split()
                    if int(fields[2]) == pid:          # its process group
                        pids.add(int(entry))
                except (OSError, ValueError, IndexError):
                    continue
    except OSError:
        pass
    return pids


def _raise(pid):
    """Bring the window of this process (or its group) to the front:
    (done, how it went, for the log). Hyprland, Sway, X11 (xdotool or
    wmctrl) or Windows; GNOME and KDE on Wayland offer no way."""
    import json
    import shutil
    import subprocess

    def run(*cmd):
        return subprocess.run(cmd, capture_output=True, text=True, timeout=3)

    try:
        if os.name == "nt":
            return (True, "windows") if _raise_windows(pid) else (False, f"windows: no window for pid {pid}")
        pids = _group(pid)
        if os.environ.get("HYPRLAND_INSTANCE_SIGNATURE") and shutil.which("hyprctl"):
            clients = json.loads(run("hyprctl", "-j", "clients").stdout or "[]")
            for c in clients:
                if c.get("pid") in pids:
                    done = run("hyprctl", "dispatch", "focuswindow", f"address:{c['address']}").returncode == 0
                    return done, f"hyprland: focuswindow {c['address']} " + ("done" if done else "failed")
            return False, (f"hyprland: none of {len(clients)} windows belongs to pids {sorted(pids)[:8]} "
                           f"(window pids: {sorted({c.get('pid') for c in clients})[:12]})")
        if os.environ.get("SWAYSOCK") and shutil.which("swaymsg"):
            stack = [json.loads(run("swaymsg", "-t", "get_tree").stdout or "{}")]
            while stack:
                node = stack.pop()
                if node.get("pid") in pids:
                    done = run("swaymsg", f"[con_id={node['id']}]", "focus").returncode == 0
                    return done, "sway: focus " + ("done" if done else "failed")
                stack += node.get("nodes", []) + node.get("floating_nodes", [])
            return False, f"sway: no window for pids {sorted(pids)[:8]}"
        if os.environ.get("DISPLAY") and not os.environ.get("WAYLAND_DISPLAY"):
            if shutil.which("xdotool"):
                for p in pids:
                    found = run("xdotool", "search", "--onlyvisible", "--pid", str(p)).stdout.split()
                    if found:
                        done = run("xdotool", "windowactivate", found[-1]).returncode == 0
                        return done, "x11: xdotool " + ("done" if done else "failed")
            if shutil.which("wmctrl"):
                for line in run("wmctrl", "-lp").stdout.splitlines():
                    parts = line.split()
                    if len(parts) > 2 and parts[2].isdigit() and int(parts[2]) in pids:
                        done = run("wmctrl", "-ia", parts[0]).returncode == 0
                        return done, "x11: wmctrl " + ("done" if done else "failed")
            return False, "x11: no window found (xdotool or wmctrl needed)"
        desktop = os.environ.get("XDG_CURRENT_DESKTOP") or "this desktop"
        return False, (f"{desktop} gives apps no way to bring a window to the front "
                       f"(Hyprland seen: {bool(os.environ.get('HYPRLAND_INSTANCE_SIGNATURE'))}, "
                       f"hyprctl found: {bool(shutil.which('hyprctl'))})")
    except (OSError, ValueError, KeyError, subprocess.SubprocessError) as e:
        return False, f"couldn't ask the window manager: {e}"


def _raise_windows(pid):
    import ctypes
    from ctypes import wintypes

    user32 = ctypes.windll.user32
    found = []

    @ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)
    def each(hwnd, _):
        owner = wintypes.DWORD()
        user32.GetWindowThreadProcessId(hwnd, ctypes.byref(owner))
        if owner.value == pid and user32.IsWindowVisible(hwnd):
            found.append(hwnd)
            return False
        return True

    user32.EnumWindows(each, 0)
    if not found:
        return False
    user32.ShowWindow(found[0], 9)                  # SW_RESTORE, if it's minimised
    return bool(user32.SetForegroundWindow(found[0]))


def _front(pid, profile):
    from core import logbook

    done, how = _raise(pid)
    logbook.info("window", "the %s window is already open: %s", profile,
                 "brought to the front" if done else f"left where it is ({how})")


def open_app(url, w, h, profile):
    """A page in a window of its own (command(); portrait.browser, when set,
    picks the browser): the process, or None when it went to a browser tab.
    Already open on this profile: that window comes to the front instead."""
    import subprocess

    import config

    mine = _mine.get(profile)
    if mine is not None and mine.poll() is None:
        _front(mine.pid, profile)
        return mine
    held = _holder(profile)
    if held is not None:               # a window this run didn't open, still on its profile
        _front(held, profile)
        return None

    try:
        if getattr(config, "PORTRAIT_BROWSER", ""):
            from core.machine import split_command

            cmd = split_command(config.PORTRAIT_BROWSER.format(url=url, w=w, h=h))
        else:
            cmd = command(url, w, h, profile=profile)
    except (OSError, ValueError, KeyError):
        cmd = None
    if cmd:
        try:
            proc = subprocess.Popen(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                                    stdin=subprocess.DEVNULL, start_new_session=True)
            _opened[:] = [p for p in _opened if p.poll() is None] + [proc]   # closed with her (close())
            _mine[profile] = proc
            return proc
        except OSError:
            pass
    quiet_open(url)
    return None


def quiet_open(url):
    """webbrowser.open, but with the browser's output thrown away: started
    from Luna's process it would otherwise print over her screen."""
    import subprocess
    import webbrowser

    if sys.platform.startswith("linux"):
        import shutil

        opener = shutil.which("xdg-open")
        if opener:
            try:
                subprocess.Popen([opener, url], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                                 stdin=subprocess.DEVNULL, start_new_session=True)
                return
            except OSError:
                pass
    webbrowser.open(url)


# ---------------------------------------------------------------------------
# /portrait: open and close it
# ---------------------------------------------------------------------------
_window = {"proc": None}
# Every window open_app started this run (her chat, the pose studio, the live
# monitor...): close() shuts them when she quits. A page that went to a browser
# tab instead isn't hers to close.
_opened = []
_mine = {}            # profile -> the window open_app started on it, to bring back rather than start twice


def _stop(proc):
    """Close a window process and what it started (a Flatpak's sandbox, a
    browser's helpers): its own session's process group, where there is one."""
    if not proc or proc.poll() is not None:
        return
    try:
        if os.name != "nt":
            import signal

            os.killpg(proc.pid, signal.SIGTERM)
        else:
            proc.terminate()
    except (OSError, ProcessLookupError):
        try:
            proc.terminate()
        except OSError:
            pass


def toggle(obs=False):
    """/portrait opens her portrait in a small window of its own, and
    closes it again. /portrait obs prints the URL for a browser source."""
    import subprocess

    import config
    from web import livefeed
    import ui

    if not config.MONITOR_ENABLED:
        ui.add_message("system", "The portrait is served by the live monitor, which is off - "
                       "set monitor.enabled to true in config.json and restart.")
        return

    if obs:
        ui.add_message("system", "For OBS: add a Browser source with this URL, any size "
                       f"you like - the background is see-through:\n{livefeed.portrait_url(True)}")
        return

    proc = _window["proc"]

    if proc and proc.poll() is None:
        _stop(proc)
        _window["proc"] = None
        ui.add_message("system", "Portrait closed.")
        return

    url = livefeed.portrait_url()

    try:
        w, h = (int(x) for x in config.PORTRAIT_SIZE.lower().split("x"))
    except ValueError:
        w, h = 420, 560

    try:
        if config.PORTRAIT_BROWSER:
            from core.machine import split_command

            cmd = split_command(config.PORTRAIT_BROWSER.format(url=url, w=w, h=h))
        else:
            cmd = command(url, w, h)
    except (OSError, ValueError, KeyError) as e:
        ui.add_message("system", f"Couldn't set up the portrait window ({e}).")
        cmd = None

    if not cmd:
        quiet_open(url)
        ui.add_message("system", f"Portrait: {url} (no browser found for a window of its own "
                       "- set portrait.browser to choose one)")
        return

    try:
        # its output goes nowhere: a browser's warnings written to Luna's
        # terminal land on top of the screen (and in the input line)
        _window["proc"] = subprocess.Popen(cmd, stdout=subprocess.DEVNULL,
                                             stderr=subprocess.DEVNULL, stdin=subprocess.DEVNULL,
                                             start_new_session=True)
        ui.add_message("system", f"Portrait open - /portrait again closes it. ({url})")
    except OSError as e:
        ui.add_message("system", f"Couldn't start {cmd[0]}: {e} - opening it in your browser.")
        quiet_open(url)


def close():
    """Luna quitting: close every window this run opened, the portrait and the
    rest (open_app)."""
    _stop(_window["proc"])
    _window["proc"] = None
    while _opened:
        _stop(_opened.pop())
    _mine.clear()

