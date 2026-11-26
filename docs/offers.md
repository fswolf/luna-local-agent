# Offers: things she notices on her own

Luna keeps an eye on a few things while you're away, and when one needs
attention she offers to help, the next time you talk to her. She never
acts on her own: she offers, and does it only if you say yes.

```
You:  morning
Luna: Morning! Coffee's on. Oh, and your home disk is down to 6% free,
      want me to find what's eating it?
You:  sure
```

## What she watches

| Watcher | What she notices | What she offers |
|---|---|---|
| Machine | A disk nearly full, a service that failed | To look into it: `system_health`, then a command to find what's using the space |
| Dates | Something she remembers about you with a date coming up in the next two weeks ("Shannon's birthday is November 2"), with no reminder near it | To set a reminder, maybe the day before |
| Calendar | An event on your [calendar](calendar.md) in the next two days with no reminder of yours before it and no alarm of its own | To remind you beforehand |

Dates come from her memory: anything with a month and a day ("March 3",
"the 2nd of Nov") or a full date ("2026-11-30"). One without a year, or
with a year long gone ("born May 3, 1990"), is the next time it comes
round, like a birthday.

### Right when she saves it

A date doesn't have to wait until it's two weeks away. When she saves
or updates a fact with a date coming up, and nothing reminds you of it
yet, she asks then and there:

```
You:  Shannon's birthday is March 3
Luna: Got it, March 3. Want a reminder the day before?
```

Yes sets the reminder; no means not now. That question counts as one of
the date's two asks, so after a no she brings it up at most once more,
when it's close, and only if there's still no reminder. "Don't ask me
about that again" mutes it for good, every year. Same rules as the
rest, with one difference: your own turns only, never a guest's fact,
never in a heavy moment or while she's walked away, but the lewd row
doesn't hold it back (it's a follow-up to what you just said, not an
interruption). `offers.dates` switches it off with the watcher.

## When she brings it up

- One thing per turn, on your own turns only: typed, spoken, from a
  relay station, or her hello when you come back. Never to a guest
  (not even in a hello), in stream chat, Discord, a job or a game.
- Never in the lewd row, during a [heavy moment](moods.md#heavy-moments),
  or while she's walked away.
- Only if it fits. If you're in the middle of something, she leaves it.
- At most 3 a day and 2 hours apart. Each thing waits before she mentions
  it again: half a day for the machine, a day for a date. A date is
  offered at most twice, and something that stays wrong (a disk that
  stays full) comes up every three days once she's raised it three times.

Yes means she does it with her normal tools, and anything that changes
your machine still asks first. "Don't bring that up again" mutes it for
good (her `stop_offering` tool); for a date, that's the date every year,
not just this one, and for a repeating calendar event, every time it comes round. Saying no just means not now.

## Commands and settings

```
/offers           what she's noticed, and how many offers today
/offers now       look again right now
/offers off | on  stop offering, or start again
/offers unmute    bring back everything you've muted
```

| Setting | Default | |
|---|---|---|
| `offers.enabled` | `true` | the whole thing |
| `offers.per_day` | `3` | offers a day |
| `offers.gap_minutes` | `120` | minutes between offers |
| `offers.machine` | `true` | watch disks and services |
| `offers.dates` | `true` | watch dates in what she remembers |
| `offers.days_ahead` | `14` | how far ahead a date gets an offer |
| `offers.calendar` | `true` | watch your calendar's next two days |

The watchers look every ten minutes in the background, so a turn never
waits for them. What she's offered and what you've muted is kept in her
notebook (`agent/notebook.db`).
