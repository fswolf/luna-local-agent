import os
import ui

from pynput import keyboard
from ptt import toggle


def on_press(key, model):
    try:
        if key == keyboard.Key.home:
            # The same HOME as every other input path (ptt.py): start,
            # finish a manual recording, or stop - and hands-free in open mode.
            toggle(model)

        elif key == keyboard.Key.esc:
            os._exit(0)

    except Exception as e:
        ui.set_status(f"Keyboard error: {e}")


def start_keyboard(model):
    with keyboard.Listener(on_press=lambda key: on_press(key, model)) as listener:
        listener.join()