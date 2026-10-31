# Cards

A card is a picture of her that is also her whole look. In any image viewer it's
a trading card with her on it; in Luna's Cards tab it's a look she can put on.
Save one for each look you like (her robot body, her human model in white, a
room for the season) and switch between them with a click, or send one to
someone and their Luna can wear it too.

<img width="1210" alt="Saving a card: the control panel's Cards tab on the left with the new card in its grid, and the saved card open in an image viewer on the right, framed in pink and purple with its name on a plate underneath" src="https://raw.githubusercontent.com/fswolf/luna-local-agent/main/assets/cards-saved.jpg" />

## Where to find them

On the debug viewer, in the control panel's **Cards** tab. Open the viewer with
`./studio.sh`, or with Luna running at `http://127.0.0.1:8792/portrait/?debug=1`
(the browser tab says "Studio"). The control panel is on the left, the
[pose studio](portrait.md#the-pose-studio-making-gestures-without-code) on the
right.

<img width="1210" alt="The debug viewer: the control panel on the left open on its Cards tab, her model in the middle, and the pose studio on the right" src="https://raw.githubusercontent.com/fswolf/luna-local-agent/main/assets/cards-panel.jpg" />

## What a card carries

You tick what goes on a card when you save it:

| Part | What | Ticked at first |
|---|---|---|
| model | the model file itself, as big as the model (Luna's are 16-22 MB). Untick it for a light card, for someone who has the model already | yes |
| look | background, framing, light from the room, hologram, and the light strip settings for Luna's robot model (the only model that has strips) | yes |
| clothes map | the model's `<model>.outfits.json`, if it has one | yes |
| voice | her Kokoro voice and speed | no |
| your gestures | any you tick, from the ones you made yourself | none |

**Gestures:** only the ones you made are listed, since everyone has the ones that
come with Luna already. "Yours" means a file in `portrait/gestures/` that isn't
in Luna's git. In a copy of Luna that didn't come from git, every gesture is
listed and you pick the ones you made.

**Never on a card:** who she is. Her personality, moods and memory stay yours
whatever she's wearing. A card also can't hold what she knows about you or other
people, people's prints, keys or tool settings: only the parts in the table can
be on one, and only those are put on.

## Saving one

1. Pose and frame her. The picture is what you see, background included.
2. In the **Cards** tab, give the card a name and tick what it carries.
3. Press **save card** (or Enter).

The middle of the view is framed as a trading card, with the name you gave it on
a plate underneath. The card is kept in `portrait/cards/<name>.png`; saving over
one asks first.

Which model goes on is the one on screen, even one you're only previewing from
the model menu. The look and voice are the ones saved in your settings, though:
something you only tried in the control panel (a background preview, say) shows
in the picture but isn't carried. Save it in settings first.

## Putting one on

Click it. It asks first and says what the card carries. Then its model, look and
voice replace your saved ones, its gestures are added, and the portrait reloads
as that look. Anything left out is listed:

- **The model:** if you have the same file (checked by its fingerprint), yours is
  used. Otherwise the card's copy goes in `portrait/models/cards/<card>/`, so a
  model you've changed since is never overwritten.
- **Gestures and clothes maps** you already have under the same name are kept,
  not replaced.
- **A light card** on a machine without its model sets the look and gestures and
  leaves the model as it is.

Hover a card for **⤓** (the card file, to share it) and **✕** (delete it, after
asking; a model it brought in stays in `portrait/models/cards/`, since she may be
wearing it).

## Sharing

Send the card file (**⤓**, or straight from `portrait/cards/`). Send it as a file
(a chat app's file upload, a drive link) rather than posting it as an image:
sites that shrink or re-save pictures drop everything under the picture, and
what's left is only a picture.

To add one, drop it on the cards grid (several at once is fine), or use
**add a card…**. Each one is checked before it's kept: a card is a PNG of at most
96 MB, gestures go in as data through the same checks as the pose studio's own
save, never as code, and nothing outside the table above is read from it.

## When something's off

| What you see | Why, and what to do |
|---|---|
| "not saved" or "not added" with a network error, or every gesture listed as yours, after updating Luna | The server is still the old one: restart Luna (or `./studio.sh`) and reload the page |
| "a picture, but not a Luna card" | Only the picture made it: it was re-saved on the way. Ask for the file itself |
| "clothes map: this model doesn't have one" | Nothing's wrong: its clothes are found by where they sit on her, so there's no map to carry |
| Her new look has the old background | The card carries the background saved in settings, not a preview: save it there and make the card again |

## Where things are kept

| What | Where |
|---|---|
| Your cards | `portrait/cards/` |
| Models that came with a card | `portrait/models/cards/<card>/` |

## For developers

A card is a PNG with a zip on the end. A picture viewer reads from the start and
stops at the PNG's end; a zip reader reads from the end, so `unzip` opens a card.
Inside, `card.json` says what it carries, with the look and voice settings;
`model.vrm`, `outfits.json` and `gestures/*.json` are the rest. Packing, checking
and putting one on are in `web/cards.py`; the Cards tab is
`portrait/viewer/cards.js`.
