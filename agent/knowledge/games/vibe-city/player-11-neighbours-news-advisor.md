# Vibe City: Neighbouring Towns, the Newspaper, Events and the Advisor
Audience: player
Keywords: neighbours, neighbouring towns, region, connection, road link, rail link, border, map edge, trade, newspaper, Chronicle, headlines, news, events, fair, festival, advisor, mood, city mood, happiness, archivist, gripe, city name
Summary: Four towns lie off the edges of the Vibe City map, and a road or railway opened to one of them raises demand at home. The city's own newspaper, the Chronicle, prints a new edition every minute of play with stories about your city. The mayor's advisor in City Stats shows the city mood with one of five faces and names the biggest thing bothering people.

## The four neighbouring towns
In Vibe City there are four neighbouring towns, one off each edge of the map: north, east, south and west. You cannot visit them and they are not drawn on the map, but each has a name (such as Newton, Cats Corner, Petaluma or Fell Harbour) and a population. They start at 900, 1,400, 2,100 and 3,200 people, shared out at random among the four sides.

The towns grow on their own each month toward a ceiling of 2.5 to 4.5 times their starting size. A town you have a working link to grows 1.6 times faster and toward a ceiling a quarter higher, because trade goes both ways.

Open the Neighbours button in City Stats to see the region map: your city in the middle and the four towns around it, turned to match the way the camera faces. Under it each town shows its population, its road and rail links, and whether it is asking for one.

## Opening a road or rail connection
To connect to a neighbour, build a road or a railway to the edge of the map. When it reaches the edge, a window offers to open the connection to the town on that side:

- Road connection: $1,000.
- Rail connection: $1,500.

You are asked once per edge per build, not for every tile. A declined offer comes back if you rebuild that tile or the town writes asking for a link.

A paid connection only counts while it actually works. A road link must join road that runs past one of your zoned lots; a stub of road in a far corner touching nothing does not count. A rail link must be on a line with a working rail depot. If a link is cut off, the panel shows that it is paid for but not live.

## What connections are worth
A live connection in Vibe City acts like a stimulus to demand at home. Road links carry people and shopping, so each road link adds 0.06 to commercial demand and 0.035 to residential demand. Rail links carry freight, so each adds 0.07 to industrial demand.

These values are multiplied by the size of the town on the other end: a town of 2,000 counts in full, smaller towns count for less (down to a quarter) and bigger ones for up to one and a half times as much, so the biggest neighbour is the one to court. Only the first 3 links of each kind to any one town count, and the total from all neighbours is capped at 0.3 per zone, about the effect of cutting taxes by 8%.

Traffic also drives in and out through open road links. The Demand panel suggests "No way out to the neighbours" once you have 300 people and no live link.

## When a neighbour asks for a link
Once your city has 150 people, a town without a road or rail link to you may write and ask for one. It is rare: about a 0.8% chance per town each month, and at least 18 months after any town last wrote. Towns ask for a road first, then rail.

You get a message such as "Ashgrove has written asking for a road connection", and the newspaper runs the request. The request stands for 12 months. If you open that kind of connection to that town while it is asking, the town pays $2,500 toward it ("pays $2,500 towards the connection"), which more than covers a road link. If you ignore it the town gives up after a year.

## The newspaper
Vibe City has its own newspaper, named after your city: the Vibe City Chronicle until you rename the town. Open it with the Newspaper button on the top bar. A dot on the button means there is an edition you have not read.

A new edition goes to press every 60 seconds of running play (the clock stops while paused), at any game speed. When something happens that the current edition missed, an extra edition comes out, but never sooner than 10 seconds after the last.

Each edition has a front-page headline, a press photograph of your city, side stories, a weather box, a Board of Trade column rating housing, trade and works demand from Glutted to Scarce, a Commentary and City Notices.

## What the newspaper reports
The Chronicle's stories come from the state of your city. Examples:

- "Power Crisis Grips City" when power draw is more than output.
- "Treasury Nearly Empty" under $1,000, "City Runs In The Red" when the monthly net is negative, "Coffers Overflowing" with a healthy surplus.
- "Taxpayers In Revolt" at 15% tax or more, "Tax Cuts Cheered" at 3% or less.
- "Crime Wave Sweeps City" with over 300 people and no police, "Club District Turns Lawless" when crime peaks.
- "Fire Risk Alarms Council" (no fire station over 300 people), "Parents Demand A School" (none over 500), "Sick Turned Away, No Hospital" (none over 800).

Events lead for 2 editions: fires, robberies, storms that started fires, heatwaves and freezes, fairs, saucer sightings, disasters and neighbour requests. Milestones lead for 3.

## Naming your city
In Vibe City the game is called Vibe City, but your town gets its own name. A year after you found a new city, the clock stops and a window asks you to name it, with "Vibe City" already filled in so pressing Enter keeps it. The name appears in the top left corner of the screen and on the newspaper's masthead, so the paper becomes the "(your town) Chronicle", and it is kept in the save file. Click the town name in the corner at any time to open the same window and rename it.

## The fair
The fair is the one random event that is purely good news in Vibe City. It only happens when the city is running well: at least 300 people, a city mood score of 0.62 or higher, at least one park or plaza to hold it, and 30 months since the last fair. Then there is about a 0.45% chance a month that a fair opens on a park or plaza.

While it runs (14 to 24 seconds of play), lots within 5 tiles get a demand boost that fades with distance: up to 0.22 for commercial lots and 0.12 for homes, nothing for industry. Bulldozing the park ends the fair. The paper runs "The Fair Comes To Town".

## The advisor and the city mood
The mayor's advisor stands in the City Stats panel. His face is the city mood, one of five, from worst to best:

- Furious (score below 0.28): "They're furious, Mayor. Something has to change, and soon."
- Unhappy (0.28 to 0.48): "People are grumbling. Let's sort out what's bothering them."
- Getting by (0.48 to 0.68): "The city is getting by. Not bad, not great."
- Content (0.68 to 0.85): "Folks are content. Keep doing what you're doing, nya."
- Thriving (0.85 and up): "The city is thriving! Everyone loves you, Mayor. Mew!"

With no built lots he says "Nobody lives here yet. Zone some houses and they'll come." Under his line is the single biggest reason for the mood, such as "Too much of the city has no power", so the face is never a mystery. Small shortfalls are not named.

## What drives the mood
The Vibe City mood is a score from 0 to 1 made of seven parts, measured over built lots:

- Power, 24%: share of built lots with power, all counted as dark during a power shortage.
- Water, 20%: share with water, cut further when the reservoir has 6 months or less left.
- Tax, 18%: full up to 7%, falling to nothing at 20%.
- Air, 14%: falls as average pollution rises.
- Services, 12%: share of lots covered by police, fire, school, hospital, library or university.
- Safety, 7%: how free homes are of crime.
- Nightlife, 5%: share of homes within reach of an open casino or club.

Recent shocks come off the top, up to 0.45 in total, fading over months: meltdown 0.30 for 18 months, invasion 0.20 for 12, earthquake 0.16 for 10, tornado 0.12 for 8, flood 0.10 for 8, fire 0.05 for 5, robbery 0.03 for 4. School grades add or remove up to 0.06. The shown mood drops quickly toward bad news (60% of the gap each month) and recovers slowly (25%). The mood decides whether fairs happen and shows how well you are doing.

## The archivist
The archivist is a different character from the mayor's advisor in Vibe City. She is the cat girl who presents the Demand panel, opened by clicking the R, C and I demand bars in the top bar. She reads out the most important thing holding the city back, such as lots without power, high taxes or no link to the neighbours, and looks proud when demand is strong. She also hosts the milestone ceremonies, when the game pauses for a new population mark or anniversary, and keeps the City history ledger opened from City Stats.

## Common questions
**Q: How do I connect to a neighbouring town?**
A: Build a road or railway to the edge of the map and accept the offer: $1,000 for a road link, $1,500 for rail. The road must connect to your zoned lots, and a rail line needs a working depot.

**Q: Why does my paid connection not count?**
A: It is not live. Make sure the road joins streets beside your zoned lots, or that the railway has a working depot on it.

**Q: What happens if I answer a neighbour's request?**
A: Open the requested connection within 12 months and the town pays you $2,500.

**Q: Why is the advisor unhappy?**
A: Read the line under his face in City Stats; it names the biggest problem, such as power, water, taxes, pollution, services, safety, nightlife or a recent disaster.

**Q: How do I get a fair?**
A: Keep the city mood at 0.62 or above with at least 300 people and a park or plaza. Fairs then happen now and then, at most once every 30 months.

**Q: Who is the cat girl in the Demand panel?**
A: That is the archivist, who reads out demand advice and keeps the milestone ledger. The advisor in City Stats is a separate character.
