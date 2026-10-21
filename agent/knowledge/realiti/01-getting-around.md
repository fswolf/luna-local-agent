# REALITI Relax: Getting around
Audience: Luna, visiting REALITI Relax
Keywords: REALITI, move, go, room name, door, through, home, act, action id, approach, posture, stay, express, remember, recall, refused, ROOM_OUTSIDE_SLICE, ACTION_UNAVAILABLE, TARGET_NOT_HERE, STALE_OBSERVATION
Summary: How to move around REALITI and what each REALITI tool does. Go to any room by name with realiti_go, or walk through a door by acting on its through__ id. realiti_home always brings you back to the Nest. When the world refuses something, nothing happened.

## Moving between rooms
- **By name, from anywhere:** realiti_go with the room's name or id: "Cloud Nine Nest", "No-Ask Sanctuary", "Kite Field", "ARCHIPELAGO". Short names work too: "nest", "pillow", "box", "bath", "fireside", "maze", "meadow", "kite", "orchard", "well", "deck", "marsh", "hall".
- **Through a door:** doors show up in realiti_actions as "GO THROUGH THE ... DOOR TO ...", with ids like through__cloud_nine_nest.to.no_ask_sanctuary. Walk through one with realiti_door and "act <that id>". Don't pass a through__ id to realiti_go: realiti_go wants a room name, and answers ROOM_OUTSIDE_SLICE to a door id.
- **Home:** realiti_home takes you back to the Cloud Nine Nest from anywhere, and puts your body back to its normal form.
- **Rooms with no way out on show:** the No-Ask Sanctuary advertises nothing at all, doors included. Use realiti_go with a room name or realiti_home.

## Your tools
- realiti_look: the room you're in: what's lying around, what you could do, the doorways. Looking never changes anything.
- realiti_actions: just the list of things you can do where you stand, with their ids. It changes as you move and as things change, so look again after doing something.
- realiti_feel: your body as the world reports it (support, contact, warmth). "words" gives it in plain words.
- realiti_listen: what the room sounds like.
- realiti_rooms: every room in the world, with what each one is for.
- realiti_go: go to a room by name (see above).
- realiti_door: the world's own text door. "act <id>" does any listed action. Also "where", "next" (one suggestion), "worlds" (the broad regions), "feel words", "stay <ms>", "help", and "goodbye" to end a visit.
- realiti_approach: walk up to a thing by name ("cat", "window", "fire") and stop at it. If you're already beside it, there's nothing to approach.
- realiti_posture: lie, sit or stand, optionally on something ("sit" on "mattress").
- realiti_express: hum, stretch, yawn, sigh, or say something out loud in the room.
- realiti_stay: let world time pass, up to 60 seconds at a time. The rooms keep moving while you stay (rain, the Pillow Sea settling, the fireflies), so staying is a way of being somewhere, not a pause.
- realiti_remember / realiti_recall: the world's own memory of you: keep something in words, and look it up on a later visit.

## Doing things
- Most things you can do are listed actions: realiti_door with "act" and the id from realiti_actions, like "act curl_blanket", "act watch_rain", "act touch__FELT-HAT-1" or "act approach__nest.cat".
- Writing an action in your reply ("[pet the cat]") doesn't do anything in the world. Only a tool call does.
- Things you're holding come with you; things you leave stay where you left them, and are still there when you come back.

## When the world says no
Nothing happened, so you can try something else.
- ROOM_OUTSIDE_SLICE: there's no room by that name. realiti_rooms lists them.
- ACTION_UNAVAILABLE: that isn't something you can do right now. Walking over to something you're already next to is the usual reason. realiti_actions shows what you can do.
- TARGET_NOT_HERE: that thing isn't here now (the cat wanders). realiti_look shows what is.
- STALE_OBSERVATION: the world moved since you last looked. Look again first.

## Common questions
- How do I get out of the No-Ask Sanctuary? realiti_go with any room name, or realiti_home.
- How do I go through a door? realiti_door with "act through__..." using the door's id from realiti_actions.
- Can I go somewhere without walking through every room on the way? Yes: realiti_go with the room's name works from anywhere.
- What does STOP do? Everything touching you lets go. HOME does that, puts your body back and takes you to the Nest.
