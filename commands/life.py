"""Her own life: /mood, /coffee, /read, /situation.

Part of the commands package; see commands/__init__.py.
"""
from life import coffee
import config
from mind import mood
from life import reading
import ui


def handle(text):
    """True when text was one of these commands (and it ran)."""
    if text.startswith("/mood"):
        argument = text[5:].strip().lower()

        if argument == "reset":
            mood.reset()
            ui.add_message("system", f"Mood reset - she's {mood.label()}.")
            return True

        if not config.MOOD_ENABLED:
            ui.add_message(
                "system",
                "Moods are off - /set mood.enabled true switches them on.",
            )
            return True

        name, energy, warmth, why = mood.state()
        energy_word, warmth_word = mood.bands()
        lines = [
            f"She's {name}  "
            f"(energy {energy:+.2f} {energy_word}, "
            f"warmth {warmth:+.2f} {warmth_word})",
        ]

        if why:
            lines.append("Lately: " + "; ".join(why))

        extra = mood.layers()
        lines.append(f"Desire {extra['desire']:.2f} (lewd from {mood._extra('lewd').get('enter', 0.6)} at very warm)"
                     + (f" · holding a grudge, {extra['grudge'] / 60:.0f} min left" if extra["grudge"] else "")
                     + (f" · lewd held back while {', '.join(mood.tame())} is live" if mood.tame() else ""))

        if config.MOOD_AFFECTION:
            rating = mood.last_rating()
            feeling = mood.last_feeling()
            lines.append(
                "Reading the exchange: last message rated "
                + (f"{rating}/3" if rating is not None
                   else "nothing yet this session")
                + (f", she felt {feeling}" if feeling else "")
            )

        if config.MOOD_INTENSITY != 1.0:
            lines.append(f"Intensity {config.MOOD_INTENSITY:g} (0 flat, 1 normal, 2 very visible)")

        if getattr(mood, "_moods", {}).get("error"):
            lines.append("Moods file problem: " + mood._moods["error"])

        lines.append(
            "Drifts back on its own - /mood reset to force it, "
            "/set mood.recovery to change how fast."
        )
        ui.add_message("system", "\n".join(lines))
        return True

    if text == "/coffee" or text.startswith("/coffee "):

        word = text[len("/coffee"):].strip().lower()

        if word in ("", "on", "now"):
            ui.add_message("system", "Coffee time. She picks up her mug." if coffee.begin()
                           else "She already has her coffee.")
        elif word in ("off", "done"):
            ui.add_message("system", "She puts her mug down." if coffee.finish() else "She isn't holding one.")
        elif word == "sip":
            ui.add_message("system", "A sip." if coffee.sip() else "She has no coffee - /coffee first.")
        return True

    if text == "/read" or text.startswith("/read "):

        word = text[len("/read"):].strip().lower()

        if word in ("", "on", "now"):
            ui.add_message("system", "She picks up her book." if reading.begin() else "She's already reading.")
        elif word in ("off", "done", "stop"):
            ui.add_message("system", "She puts her book down." if reading.finish() else "She isn't reading.")
        elif word in ("page", "turn"):
            ui.add_message("system", "She turns a page." if reading.page(lookup=False) else "She isn't reading - /read first.")
        elif word in ("look", "up"):
            ui.add_message("system", "She looks up at you." if reading.page(lookup=True) else "She isn't reading - /read first.")
        return True

    if text == "/situation":
        from mind import situation

        found = situation.lines(fresh=True)
        state_word = "on" if situation.enabled() else "off (/set situation.enabled true)"
        ui.add_message("system", "\n".join(
            [f"Situation block: {state_word}. What she'd see this turn:"]
            + ([f"  - {line}" for line in found] or ["  (nothing to report)"])))
        return True

    return False
