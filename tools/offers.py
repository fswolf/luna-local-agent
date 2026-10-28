"""stop_offering: "don't bring that up again" about something she offered
on her own (life/offers.py). Only offered when she's offered something lately."""
from . import tool


def _recent():
    try:
        from life import offers
        return offers.recently_offered()
    except Exception:
        return False


@tool(
    "stop_offering",
    "The user said not to bring up again the thing you offered on your own (a full disk, a "
    "date coming up...). Mutes it for good. Only when they say so, not when they just say no "
    "this time.",
    {},
    available=_recent,
    why=lambda: "she hasn't offered anything lately",
)
def stop_offering():
    from life import offers

    key = offers.stop()
    return "Done: you won't bring that up again." if key else "There was nothing to stop offering."
