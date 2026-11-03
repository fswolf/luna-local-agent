import os
import ui

from pynput import keyboard
from voice.ptt import toggle


def _escape():
    """Esc read globally. While the window is up it's the window's (close a
    pane, answer no, quit from the conversation); os._exit from here left
    the terminal in raw mode. Before the window exists it still quits."""
    if ui.view.app is not None:
        return
    os._exit(0)


def _handle_home(model):
    # The same HOME as every other input path (voice/ptt.py): start, finish a
    # manual recording, or stop - and hands-free in open mode.
    toggle(model)


def start_keyboard(model):
    # macOS requires the app reading global keypresses (this terminal /
    # Python process) to be granted Accessibility access:
    # System Settings -> Privacy & Security -> Accessibility.
    # Without it, pynput's listener runs but never receives events -
    # HOME/ESC will silently do nothing rather than error out.
    ui.add_message(
        "system",
        "If HOME/ESC don't respond, grant Accessibility access to this "
        "terminal in System Settings > Privacy & Security > Accessibility.",
    )

    def on_press(key):
        try:
            if key == keyboard.Key.home:
                _handle_home(model)
            elif key == keyboard.Key.esc:
                _escape()
        except Exception as e:
            ui.set_status(f"Keyboard error: {e}")

    with keyboard.Listener(on_press=on_press) as listener:
        listener.join()