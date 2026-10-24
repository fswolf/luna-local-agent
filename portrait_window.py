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


def _firefox_profile(base):
    """A profile folder with the prefs and the toolbar-hiding CSS in it."""
    os.makedirs(os.path.join(base, "chrome"), exist_ok=True)
    with open(os.path.join(base, "user.js"), "w") as f:
        f.write(_FIREFOX_PREFS)
    with open(os.path.join(base, "chrome", "userChrome.css"), "w") as f:
        f.write(_FIREFOX_CSS)
    return base


def command(url, w, h):
    """The command that opens the portrait in a window of its own, with no
    address bar, or None. A Chromium-style browser's --app window first (on
    the PATH, then as a Flatpak), else Firefox with a profile that hides
    its toolbars. Each gets its own profile, so it's its own process: one
    /portrait can close again, not a tab in a browser that's already open."""
    import shutil

    home = os.path.expanduser("~")
    app = [f"--app={url}", f"--window-size={w},{h}", "--no-first-run", "--no-default-browser-check"]

    found = next((b for b in _APP_BROWSERS if shutil.which(b)), None)
    if found:
        return [found, f"--user-data-dir={os.path.join(home, '.cache', 'luna-portrait')}"] + app

    for flatpak in _APP_FLATPAKS:
        if _flatpak_has(flatpak):
            # inside the sandbox it can always write its own ~/.var/app folder
            profile = os.path.join(home, ".var", "app", flatpak, "cache", "luna-portrait")
            return ["flatpak", "run", flatpak, f"--user-data-dir={profile}"] + app

    firefox = shutil.which("firefox")
    if firefox:
        profile = _firefox_profile(os.path.join(home, ".cache", "luna-portrait-firefox"))
        return [firefox, "--new-instance", "--no-remote", "--profile", profile,
                "--width", str(w), "--height", str(h), url]
    if _flatpak_has(_FIREFOX_FLATPAK):
        profile = _firefox_profile(os.path.join(home, ".var", "app", _FIREFOX_FLATPAK,
                                                "cache", "luna-portrait"))
        return ["flatpak", "run", _FIREFOX_FLATPAK, "--new-instance", "--no-remote",
                "--profile", profile, "--width", str(w), "--height", str(h), url]
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
