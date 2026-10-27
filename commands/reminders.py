"""Time: /reminders, /cancel, /alarms, /alarm, /snooze, /when, /repair.

Part of the commands package; see commands/__init__.py.
"""
import threading

import config
from core import logbook
from life import reminders
from core import timeutil
import ui

from . import ctx


def handle(text):
    """True when text was one of these commands (and it ran)."""
    if text == "/reminders":
        items = reminders.pending()

        if not items:
            ui.add_message("system", "No reminders pending.")
        else:
            listing = "\n".join(
                f"  {i}. {reminders.describe(r)}" for i, r in enumerate(items, 1)
            )
            ui.add_message("system", f"{len(items)} pending:\n{listing}")
        return True

    if text.startswith("/cancel"):
        parts = text.split()

        if len(parts) != 2 or not parts[1].isdigit():
            ui.add_message("system", "Usage: /cancel <number from /reminders>")
            return True

        removed = reminders.cancel(int(parts[1]))
        ui.add_message(
            "system",
            f"Cancelled: {removed['text']}" if removed else "No reminder with that number.",
        )
        return True

    if text == "/alarms":
        items = [r for r in reminders.pending() if reminders.is_alarm(r)]

        if not items:
            ui.add_message(
                "system",
                "No alarms set. /alarm <time> sets one - /alarm 7:30am, "
                "/alarm every weekday at 6.",
            )
        else:
            # Numbered against the full pending list, not this filtered
            # one, so the number you read here is the number /cancel
            # takes. Two numbering schemes for one store is how you end
            # up cancelling the wrong thing at half six in the morning.
            everything = reminders.pending()
            listing = "\n".join(
                f"  {everything.index(r) + 1}. {reminders.describe(r)}"
                for r in items
            )
            ui.add_message(
                "system",
                f"{len(items)} alarm(s):\n{listing}\n"
                "/cancel <number> removes one.",
            )
        return True

    if text.startswith("/snooze") or text.startswith("/alarm"):
        from life import alarm

        if text.startswith("/snooze"):
            argument = text[7:].strip()
            minutes = int(argument) if argument.isdigit() else config.ALARM_SNOOZE_MINUTES

            if not alarm.dismiss(minutes):
                ui.add_message("system", "Nothing is ringing.")
            return True

        argument = text[6:].strip()

        # "off" while it is ringing means stop; "off" at any other time
        # would have to mean something about the schedule, and guessing
        # between those two at 7am is not a risk worth taking.
        if argument in ("off", "stop", "dismiss"):
            if not alarm.dismiss(0):
                ui.add_message("system", "Nothing is ringing.")
            return True

        if argument == "test":
            ui.add_message("system", "Playing the alarm tone once.")
            threading.Thread(target=alarm.play_tone, daemon=True).start()
            return True

        if not argument:
            ui.add_message(
                "system",
                "Usage: /alarm <time> - e.g. /alarm 7:30am, "
                "/alarm every weekday at 6.\n"
                "  /alarm off    stop one that's ringing\n"
                "  /alarm test   hear the tone\n"
                "  /alarms       list them\n"
                "  /snooze [n]   ring again in n minutes "
                f"(default {config.ALARM_SNOOZE_MINUTES})",
            )
            return True

        due, repeat = timeutil.parse_when(argument, morning=True)

        if due is None:
            ui.add_message(
                "system",
                f"{argument!r} -> not a time I can read. Try /when {argument} "
                "to see how the parser reads it.",
            )
            return True

        ui.add_message(
            "system",
            "Alarm set: " + reminders.describe(
                reminders.add("wake up", due, repeat, kind="alarm")
            ),
        )
        return True

    if text.startswith("/when"):
        phrase = text[5:].strip()

        # "/when alarm 6" reads it the way an alarm would, where a bare
        # 6 is the morning. Without this the check disagrees with the
        # thing it is supposed to be checking.
        morning = phrase.lower().startswith("alarm ")

        if morning:
            phrase = phrase[6:].strip()

        if not phrase:
            ui.add_message(
                "system",
                "Usage: /when <phrase> - e.g. /when next friday at 4pm. "
                "Shows how the reminder parser reads it, without "
                "scheduling anything. /when alarm <phrase> reads it as "
                "an alarm would.",
            )
            return True

        due, repeat = timeutil.parse_when(phrase, morning=morning)

        if due is None:
            ui.add_message("system", f"{phrase!r} -> not a time I can read.")
        else:
            ui.add_message(
                "system",
                "{!r} -> {} ({}){}".format(
                    phrase, timeutil.friendly(due), timeutil.relative(due),
                    f", repeats {timeutil.describe_repeat(repeat)}" if repeat else "",
                ),
            )
        return True

    if text == "/repair":
        ui.add_message(
            "system",
            "Looking for past reminders that were set by the fallback and "
            "never recorded as tool calls. Nothing new gets scheduled and "
            "nothing she said is changed.",
        )

        def repair():

            def show(line):
                if line.strip():
                    ui.add_message("system", line)
                    logbook.info("repair", "%s", line)

            try:
                fixed = reminders.repair_history(ctx.model, report=show)

                if fixed:
                    ui.add_message(
                        "system",
                        f"Repaired {fixed} turn{'s' if fixed != 1 else ''}. "
                        "History now shows the tool being used instead of "
                        "talked about - run /tooltest to see the difference.",
                    )
                else:
                    ui.add_message(
                        "system",
                        "Nothing to repair - every reminder turn in history "
                        "already records what it called.",
                    )
            except Exception as e:
                logbook.exception("repair", "history repair failed")
                ui.add_message("system", f"Repair failed: {e}")

        threading.Thread(target=repair, daemon=True).start()
        return True

    return False
