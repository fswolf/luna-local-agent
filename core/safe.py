"""Numbers that are safe to wait on, sleep on or count with.

Most settings are numbers someone can type: `/set`, the settings page, a
card from a friend, a hand-edited config.json. Python's sleep and wait
raise OverflowError past about 292 years, ValueError on a negative or
NaN value, and int() refuses infinity - each of which, in a thread or a
redraw, used to end in a traceback or a loop. Read such a number through
here and it comes back finite and inside its range, or as the default.

    from core import safe
    time.sleep(safe.seconds(config.STT_SETTLE_SECONDS, 0.6))
    timer = threading.Timer(safe.seconds(limit, 150, hi=3600), stop)
"""
import math

DAY = 24 * 3600


def number(value, default, lo=None, hi=None):
    """value as a finite float inside [lo, hi]; default when it isn't a
    number at all (None, "1.5s", NaN). Infinity clamps to the bound."""
    try:
        n = float(value)
    except (TypeError, ValueError, OverflowError):
        return float(default)
    if math.isnan(n):
        return float(default)
    if math.isinf(n):
        if n > 0 and hi is not None:
            return float(hi)
        if n < 0 and lo is not None:
            return float(lo)
        return float(default)
    if lo is not None and n < lo:
        n = float(lo)
    if hi is not None and n > hi:
        n = float(hi)
    return n


def whole(value, default, lo=None, hi=None):
    """number(), as an int."""
    return int(number(value, default, lo, hi))


def seconds(value, default, lo=0.0, hi=DAY):
    """A duration to sleep or wait on: never negative, never longer than
    a day unless asked, never NaN."""
    return number(value, default, lo, hi)
