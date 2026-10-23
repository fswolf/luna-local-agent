# Seasonal backgrounds

Pictures for `portrait.background: seasonal` (in `/settings`, Portrait, background).
The portrait picks one by date and time of day: a holiday wins on its days, then the
season. Night pictures take over after dark. It changes on its own with a slow fade.

| Files | When |
|---|---|
| `winter-day`, `winter-night` | December to February |
| `spring-day`, `spring-night` | March to May |
| `summer-day`, `summer-night` | June to August |
| `fall-day`, `fall-night` | September to November |
| `halloween-day`, `halloween-night` | October 24 to 31 |
| `christmas-day`, `christmas-night` | December 15 to 26 |
| `new-years-eve-day`, `new-years-eve-night` | December 31 and January 1 |
| `valentines-day`, `valentines-night` | February 13 and 14 |

Any picture type (`.png`, `.jpg`, `.webp`). `-day` can be left off (`winter.png`), and
`newyear`, `xmas`, `autumn` work as names too. Missing ones are fine: night falls back
to day and the other way round, a holiday to its season, nothing to her gradient.

`generation-prompts.json` has the prompts the pictures were made with.
