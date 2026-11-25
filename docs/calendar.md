# Calendar

Luna can read your calendars: Google Calendar, calcurse on your PC, and
anything else that publishes iCal. Read-only, for good. She can tell you
what's on and remind you about it, but she never adds, moves or deletes
an event.

```
> what's on tomorrow?
Tomorrow you've got the dentist at 15:00 on Main St, and the stream at 19:00.

> am I free friday afternoon?
Friday's clear after the 11:00 call.

> when's the vet?
Thursday December 3 at 10:30.
```

## Setting it up

**Google Calendar.** In Google Calendar on the web: Settings, then your
calendar under "Settings for my calendars", then **Integrate calendar**,
and copy the **Secret address in iCal format**. Paste it into
`calendar.google` on the settings page (Calendar). That link is a
password to your calendar: anyone who has it can read it, so it's kept
masked on the settings page, lives in your `config.json` (never in git),
and never appears in her logs or status lines. If it ever leaks, Google's
**Reset** button next to it makes a new one.

**calcurse.** Set `calendar.calcurse` to `true`. She reads it with
`calcurse --read-only --export=ical`, so whatever you add in calcurse shows up
for her on the next read.

**Anything else.** `calendar.ics` takes a list of iCal links or `.ics`
files: a holidays feed, a shared family calendar, a work calendar's
published link.

Then switch `calendar.enabled` on. It needs two Python packages,
`icalendar` and `recurring-ical-events`; `./update.sh` installs them.

```json
"calendar": {
    "enabled": true,
    "google": "https://calendar.google.com/calendar/ical/.../basic.ics",
    "ics": [],
    "calcurse": true,
    "refresh_minutes": 30
}
```

## What she does with it

- **Answers about it.** The `calendar` tool reads a day ("tomorrow",
  "friday", "december 3"), a stretch of days ("this week", "next week",
  "the weekend"), or finds an event by name over the next year ("the
  dentist"). A weekday that's today means today.
- **Knows the day.** What's still on today (or the next thing, when
  today's done) is one of the few live lines she gets each turn
  (`situation.calendar`), so "you've got the call at 3" comes without
  asking. Her hello when you come back sees it too.
- **Offers a reminder.** A timed event in the next two days with no
  reminder of yours before it gets offered one, once or twice, through
  [offers](offers.md). One with an alarm of its own (Google's, your
  phone's) is left alone, since you'll hear about it anyway, and so is an
  all-day event. "Don't bring that up again" mutes a repeating event for
  every time it comes round. `offers.calendar` switches this off.

Repeating events are expanded properly, every time comes out in your
local time, an all-day event counts as a date, and a cancelled one is
left out. The same event in two calendars shows once.

## Reading, and when it fails

Each calendar is read at most every `calendar.refresh_minutes` (30) in
the background and kept in memory, so a turn never waits on Google. Only
while you're using her: a read is started by a turn or the tool, so a
Luna nobody's talking to doesn't poll Google all night, and the first
turn after a quiet spell reads again. Only the
tool, asked outright before anything's been read, waits for a first
read. A calendar that fails (no network, a wrong link, calcurse not
installed) keeps its last good copy, and her answer says it couldn't be
read, so a server that's down for a minute doesn't read as an empty week.

```
/calendar           the next seven days, and how each calendar stands
/calendar refresh   read them all again now
```

## Whose calendar

Yours alone. On someone else's turn, a guest's, in stream chat, Discord
or a scheduled job, the tool says no and the live line isn't there.

Event titles are whoever made the event's words, and Google adds
invitations from anyone to your calendar unless you've turned that off.
So what the tool returns counts as outside content, like a web page:
after reading it, a turn asks before reading your files.
