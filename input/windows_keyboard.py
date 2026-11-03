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


def on_press(key, model):
    try:
        if key == keyboard.Key.home:
            # The same HOME as every other input path (voice/ptt.py): start,
            # finish a manual recording, or stop - and hands-free in open mode.
            toggle(model)

        elif key == keyboard.Key.esc:
            _escape()

    except Exception as e:
        ui.set_status(f"Keyboard error: {e}")


def start_keyboard(model):
    with keyboard.Listener(on_press=lambda key: on_press(key, model)) as listener:
        listener.join()