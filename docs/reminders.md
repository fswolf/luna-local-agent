# Reminders

```
Ask in plain language:

> "Remind me in 10 minutes to clean the desk."
> "Every morning at 8 remind me to take my meds."
> "Nudge me next friday at 4 about the invoice."
> "Every 30 minutes remind me to fix my posture."

The model passes your timing words through untouched. It does not
convert them, and it does not calculate a date - all of that happens in
Python, because a small model is bad at "what is two days in minutes"
and perfectly fine at repeating "two days".
```

That division of labour is the whole design. `timeutil.parse_when()`
understands delays, clock times, weekdays, calendar dates and repeats:

| You say | It schedules |
|---------|--------------|
| `in ten minutes` | 10 minutes from now |
| `in a couple hours` | 2 hours |
| `at 8` *(said at 2pm)* | 20:00 today, not tomorrow morning |
| `tonight at 11` | 23:00, not 11:00 |
| `tomorrow morning` | 09:00 tomorrow |
| `next friday at 4pm` | 16:00 on the Friday after this one |
| `december 25` | that date, rolling to next year if it's passed |
| `every monday at 9` | weekly |
| `every morning at 8` | daily, and still 08:00 after the clocks change |
| `every weekday at 7:30` | Mon-Fri, skipping the weekend |
| `mon, wed, fri at 6am` | any set of days, with or without "every" |

`/when <phrase>` shows how anything is read without scheduling it:

```
> /when every other tuesday
'every other tuesday' -> Tuesday 09:00 (in 3 days), repeats every 2 weeks
```

Each reminder confirms itself the moment it's scheduled, in words rather
than timestamps, because these get read aloud:

```
sys  │ Scheduled: tomorrow 09:00 - take the bins out (in 18 hours)
```

If it looked like a reminder but the time couldn't be read, it says that
too, rather than failing silently.

Reminders live in `reminders/reminders.json` and survive restarts.
Anything that came due while the app was closed is delivered in one
message on next launch. A reminder is removed only once delivery
succeeds: if LM Studio is down when it fires, it retries rather than
vanishing. The scanner sleeps until the next one is actually due, so "in
one minute" means one minute.

Repeats are measured from when the reminder was *due*, not when it was
delivered, so one that goes out four minutes late doesn't drag the whole
schedule later every day. Daily times are rebuilt from the wall clock
rather than by adding 24 hours, which is the difference between "every
morning at 8" staying at 8 and quietly becoming 7 for the winter. And if
the app was closed for a week, the daily reminder is due tomorrow, not
seven times at once.

---

# Alarms

A reminder is polite. It says its piece once, at whatever volume you left
her on, and if you were asleep it's gone. That's right for "take the bins
out" and useless at seven in the morning.

```
> "Wake me up at 7:30."
> "Set an alarm for every weekday at 6."
> "Get me up in an hour."

> /alarm 7:30am
> /alarm every weekday at 6
```

An alarm is the same schedule with a different delivery. It's stored as a
reminder with `"kind": "alarm"`, so repeats, persistence and the one
scanner all come for free. The only thing that differs is what happens
when it fires:

* **She says something first**, written for that alarm by the model, then
  a tone plays. Speech alone doesn't wake anybody: it's exactly the
  thing your brain has spent years learning to fold into a dream.
* **It repeats until dismissed**, five times by default, and it stops
  being charming about it around the third:

  ```
  luna │ Morning, disaster. The gym is not going to attend itself.
  luna │ Still in bed.
  luna │ I can keep doing this.
  luna │ Seriously. Up.
  ```
* **It has its own volume**, because the point is to be louder than the
  setting you chose for a conversation at midnight.
* **Talking over it dismisses it**, same as barge-in anywhere else.

`/snooze` puts it back nine minutes; `/snooze 20` for twenty. `/alarm
off` stops it properly. A snoozed alarm is scheduled as a one-off, so
snoozing a weekday alarm doesn't disturb tomorrow's.

Two details worth knowing:

**A bare hour means morning.** "Wake me at 6" is 06:00, where "remind me
at 6" is still 18:00; six in the evening has never once been what an
alarm meant. An explicit `6pm` wins either way, and `/when alarm 6` shows
you which reading you'll get.

**An alarm that's more than ten minutes late doesn't ring.** Being woken
at 11am for a 7am alarm is worse than missing it, so one that came due
while the app was shut is reported and skipped. Ten minutes of grace
means starting the app at 7:29 still works.

```json
"alarms": {
    "enabled": true,
    "volume": 1.0,
    "repeats": 5,
    "gap_seconds": 25,
    "snooze_minutes": 9,
    "tone": ""
}
```

| Key | Default | Purpose |
|-----|---------|---------|
| `enabled` | `true` | Off delivers alarms as ordinary spoken reminders: you still get told, the room doesn't get woken |
| `volume` | `1.0` | Independent of `tts.volume` |
| `repeats` | `5` | How many times before it gives up |
| `gap_seconds` | `25` | Between rounds |
| `snooze_minutes` | `9` | What a bare `/snooze` means |
| `tone` | `""` | Path to your own 16-bit WAV; empty uses `assets/alarm.wav` |

The tone is reloaded when you change the path, so `/set alarms.tone
foghorn.wav` then `/alarm test` works without a restart. If the file is
missing or unreadable it falls back to a generated tone rather than
ringing silently: an alarm that fails quietly is worse than no alarm,
because you were relying on it.
