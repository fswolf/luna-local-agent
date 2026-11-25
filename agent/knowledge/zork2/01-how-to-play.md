# Zork II: How to play
Audience: Luna, playing Zork II
Keywords: Zork II, commands, parser, directions, lamp, light
Summary: How Zork II understands you: the same parser as Zork I.

## Moving
Compass directions (N, S, E, W, NE, NW, SE, SW), UP, DOWN, IN and OUT. Some rooms play tricks with directions: when the game says you're not sure which way is which, a direction may not take you where you meant.

## Talking to the game
- Plain English, as if it began "I want to": TAKE LAMP, OPEN THE DOOR, LOOK UNDER THE BED, PUT THE SWORD IN THE CASE, ATTACK THE TROLL WITH THE SWORD.
- Several objects with AND or commas, and ALL: TAKE ALL, DROP ALL EXCEPT THE LAMP. Several sentences on a line with THEN or a period, but in your play turns send one command at a time.
- It reads only the first six letters of a word, and ignores words in descriptions it doesn't know: those are scenery.
- When it asks which one you mean, answer with just the missing words at the very next prompt.
- Talking to someone: their name, a comma, then what you want: WIZARD, HELLO.
- Short forms: N, S, E, W, NE, NW, SE, SW, U, D; L for LOOK, I for INVENTORY, Z for WAIT, G for AGAIN.
- Useful one-word commands: LOOK, INVENTORY, WAIT, SCORE, DIAGNOSE (how you are), VERBOSE (full room descriptions every time).
- Save with zork2_save before anything risky, and zork2_restore after a death (autosave is kept for you every few moves).

## When the game complains
- I don't know the word "...": not in its vocabulary. Try a synonym; if none works, the idea probably doesn't matter.
- I can't use the word "..." here: it knows the word as another part of speech. Rephrase.
- There was no verb in that sentence / I don't understand that sentence: say it more simply, verb first.
- There were too many nouns: split it into two commands.
- You can't see any ... here: it isn't visible. It may be elsewhere, or inside something closed.
- You can't go that way: no exit that way. Room descriptions list the exits.
- It's too dark to see / It is pitch black: you need light first.
