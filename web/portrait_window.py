"""The window /portrait opens: her portrait on its own, with no address bar.

A Chromium-style browser's --app window does that (on the PATH, then as a
Flatpak). Firefox has no app mode, so it gets a profile of her own whose
userChrome.css hides every toolbar. Each runs on its own profile, so it's
a process of its own that /portrait can close again, never a tab handed to
a browser that's already open. portrait.browser overrides all of it.

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
    with open(os.path.join(base, "user.js"), "w") as f:
        f.write(_FIREFOX_PREFS)
    with open(os.path.join(base, "chrome", "userChrome.css"), "w") as f:
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


def toggle(obs=False):
    """/portrait opens her portrait in a small window of its own, and
    closes it again. /portrait obs prints the URL for a browser source."""
    import shlex
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
        proc.terminate()
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
            cmd = shlex.split(config.PORTRAIT_BROWSER.format(url=url, w=w, h=h))
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
    """Close the portrait window if this run opened one (Luna quitting)."""
    proc = _window["proc"]
    if proc and proc.poll() is None:
        proc.terminate()

