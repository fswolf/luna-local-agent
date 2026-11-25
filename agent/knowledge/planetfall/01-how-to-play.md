# Planetfall: How to play
Audience: Luna, playing Planetfall
Keywords: Planetfall, commands, directions, port, starboard, fore, aft, time, chronometer, diagnose, sleep, food, tired, hungry, parser
Summary: How Planetfall understands you, its ship directions, its clock, and looking after yourself: the game has days, and you get tired and hungry.

## Moving
- On a ship the ways are PORT, STARBOARD, FORE and AFT, plus UP and DOWN. Elsewhere the compass directions. Room descriptions name the exits.

## Time and looking after yourself
- The game keeps time: the status line and your chronometer show it, and SCORE tells you which day it is.
- DIAGNOSE reports your health, how rested you are and how fed. At the start: perfect health, well-rested, well-fed. When the game says you're getting tired or hungry, deal with it before it gets worse.
- Your ID card and chronometer are worth EXAMINE-ing; read anything with writing on it.

## Talking to the game
- Plain English, as if it began "I want to": TAKE LAMP, OPEN THE DOOR, LOOK UNDER THE BED, PUT THE SWORD IN THE CASE, ATTACK THE TROLL WITH THE SWORD.
- Several objects with AND or commas, and ALL: TAKE ALL, DROP ALL EXCEPT THE LAMP. Several sentences on a line with THEN or a period, but in your play turns send one command at a time.
- It reads only the first six letters of a word, and ignores words in descriptions it doesn't know: those are scenery.
- When it asks which one you mean, answer with just the missing words at the very next prompt.
- Talking to someone: their name, a comma, then what you want: BLATHER, HELLO.
- Short forms: N, S, E, W, NE, NW, SE, SW, U, D; L for LOOK, I for INVENTORY, Z for WAIT, G for AGAIN.
- Useful one-word commands: LOOK, INVENTORY, WAIT, SCORE, DIAGNOSE (how you are), VERBOSE (full room descriptions every time).
- Save with planetfall_save before anything risky, and planetfall_restore after a death (autosave is kept for you every few moves).

## When the game complains
- I don't know the word "...": not in its vocabulary. Try a synonym; if none works, the idea probably doesn't matter.
- I can't use the word "..." here: it knows the word as another part of speech. Rephrase.
- There was no verb in that sentence / I don't understand that sentence: say it more simply, verb first.
- There were too many nouns: split it into two commands.
- You can't see any ... here: it isn't visible. It may be elsewhere, or inside something closed.
- You can't go that way: no exit that way. Room descriptions list the exits.
- It's too dark to see / It is pitch black: you need light first.
