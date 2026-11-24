"""Reading an exchange: the short side question that asks her model how a
turn landed (a rating, energy, warmth, a feeling, flirting) and the parser
for its answer.

Part of mind/mood (see mind/mood/__init__.py).
"""
import re
import config
from core import logbook
from mind.mood.files import moods


# ---------------------------------------------------------------------------
# Being nice to her
#
# The one signal that asks the model rather than reading the session,
# and the only one that costs anything. It started as a word list and
# that was the wrong shape for a project other people clone: the
# vocabulary of affection is personal. "good kitty" is one household's
# phrase, "awsome" is one person's spelling, and neither belongs baked
# into someone else's assistant. A model knows warmth in any wording
# and any language, which is the whole job.
#
# It reports a 0-3 rating of how warm the *user's message* was. Not the
# exchange - whether she was nice back is not the question.
#
# Nothing here darkens her. Bluntness rates 0 and 0 does nothing. An
# assistant that cools when you're terse is one you have to manage, and
# she drifts back to warm on her own regardless - you never have to be
# nice to her to get a pleasant assistant, it just registers when you
# are.
# ---------------------------------------------------------------------------
# These were an order of magnitude too small. At a resting warmth of
# +0.63 the drift pull takes -0.045 off every turn, and a rating of 2
# used to put +0.045 back: a clear compliment moved the dial by
# +0.0002 and the header never budged. A kind word should be worth
# more than one turn of drift, or the signal is decorative.
_RATING = {1: 0.08, 2: 0.18, 3: 0.30}

# The one model call moods make. It used to rate only how warm your
# message was; it now reads the whole exchange - your message and her
# answer - and returns six small things on one line, which a 9B model
# manages reliably where a free-form "how does she feel?" would not:
#
#   warmth of YOUR message, 0-3      the old rating, same rules
#   energy  - = +                    did the exchange liven her up or wear her down
#   warmth  - = +                    "-" only for real hostility: bluntness is not it
#   a feeling from moods.json        shown on her face for a few seconds
#   flirt 0-2                        the lewd row's desire
#   heaviness normal/rough/heavy     heavy moments (mind/mood/heavy.py)
#
# Still one call, still off the turn's path, still off with
# mood.affection false.
#
# Fields 1, 3, 5 and 6 are about YOUR message alone. Her answer is there
# for 2 and 4 (how it left her, what her face shows) and nothing else: read
# side by side, her flirting back pulled your score up with it, and with
# an example line of "2 + + laughing 1" to copy, nearly every exchange in
# Ryan's log came back affectionate and flirty - a web search for a game,
# "watch your GPU spin up", all of it - so she never wound down. The only
# sample line now is the everyday one. /mood check compares a prompt
# against your last real exchanges (check() below).
_APPRAISE_PROMPT = (
    "Rate one moment from a conversation between {user} and {their} assistant, {name}.\n\n"
    "{user} said: {said}\n"
    "{name} answered: {answer}\n\n"
    "Answer with one line of six fields separated by spaces, nothing else. Fields 1, 3, 5 and 6 "
    "rate {user}'s message alone: {name}'s answer never raises them. She may be warm or flirt on "
    "her own; that's her, not {them}.\n"
    "1. how warm or affectionate {user}'s message is toward her: 0 for ordinary messages "
    "(questions, requests, tasks, talk about anything else, a friendly tone, swearing), 1 polite "
    "warmth aimed at her (thanks, a friendly greeting, saying sorry), 2 clear affection or praise "
    "of her, or a heartfelt apology to her, 3 strong affection\n"
    "2. how the exchange leaves her energy: = for most, + only if it was clearly lively or fun, "
    "- if it was draining\n"
    "3. how it leaves her warmth toward {them}: - if {user}'s message insults, belittles or "
    "attacks her (name-calling, calling her worthless or stupid, telling her to get lost), however "
    "she answered and even if it might be a joke or a test; + only if it was clearly kind to her "
    "or an apology; = otherwise, which is most messages\n"
    "4. the one feeling her answer shows, from: none {feelings}\n"
    "5. how flirtatious or intimate {user}'s own words are: 0 unless they flirt, 1 flirting or "
    "suggestive, 2 openly intimate or sexual\n"
    "6. how heavy {user}'s message is: normal (everyday, even annoyed or joking), rough (a bad "
    "day, stress, feeling down), heavy (really not okay: despair, can't cope, wanting to hurt "
    "themselves). The heaviest thing in the message counts, even said in passing\n"
    "An everyday message reads: 0 = = none 0 normal"
)


# The prompt before 2026-11-24, for /mood check's side by side only.
# Remove it (and check()'s "before" column) once the new one has proven
# itself on Ryan's model.
_BEFORE_PROMPT = (
    "Read this moment from a conversation between {user} and {their} assistant, {name}.\n\n"
    "User: {said}\n{name}: {answer}\n\n"
    "Answer with one line of six fields separated by spaces, nothing else:\n"
    "1. how warm or affectionate the USER's message is toward her: 0 neutral, businesslike "
    "or blunt (swearing is not unfriendly by itself), 1 polite warmth (thanks, a friendly "
    "greeting, saying sorry), 2 clear affection or praise of her, or a heartfelt apology to her, "
    "3 strong affection\n"
    "2. how the exchange leaves her energy: - (draining), = (no change), + (lively, fun)\n"
    "3. how it leaves her warmth toward {them}: - if the USER's message insults, belittles or "
    "attacks her (name-calling, calling her worthless or stupid, telling her to get lost), however "
    "she answered and even if it might be a joke or a test; = otherwise; + if it was kind or "
    "an apology\n"
    "4. the one feeling she shows right now, from: none {feelings}\n"
    "5. how flirtatious or intimate the USER's message is: 0 not at all, 1 flirting or "
    "suggestive, 2 openly intimate or sexual\n"
    "6. how heavy the USER's message is: normal (everyday, even annoyed or joking), rough (a bad "
    "day, stress, feeling down), heavy (really not okay: despair, can't cope, wanting to hurt "
    "themselves). The heaviest thing in the message counts, even said in passing\n"
    "When unsure: 0 = = none 0 normal\n"
    "Example: 2 + + laughing 1 normal"
)


def _ask(template, said, answer, model):
    """The model's raw answer to one appraisal prompt (raises on failure)."""
    import requests

    from config import LM_URL, LLM_HEADERS
    from core import lmstudio

    feelings = list((moods().get("feelings") or {}).keys())
    name = getattr(config, "AGENT_NAME", "the assistant")
    prompt = template.format(name=name, said=str(said)[:600],
                             user=getattr(config, "USER", "the user"),
                             them=getattr(config, "USER_THEM", "them"),
                             their=getattr(config, "USER_THEIR", "their"),
                             answer=str(answer or "(no answer)")[:600],
                             feelings=" ".join(feelings))
    response = requests.post(LM_URL, headers=LLM_HEADERS, json=lmstudio.chore({
        "model": model,
        "messages": [{"role": "user", "content": prompt}],
        "temperature": 0,
    }, max_tokens=200), timeout=30)
    return response.json()["choices"][0]["message"]["content"]


def _appraise(said, answer, model):
    """(rating 0-3, energy -1/0/1, warmth -1/0/1, feeling or None, flirt 0-2).
    (0, 0, 0, None, 0) on anything unexpected - a mood is never worth an error."""
    feelings = list((moods().get("feelings") or {}).keys())
    from mind.mood import heavy
    yours = heavy.owner_turn()      # read now: the next turn may be someone else's

    try:
        reply = _ask(_APPRAISE_PROMPT, said, answer, model)
    except Exception as e:
        logbook.info("mood", "couldn't read the exchange: %s", e)

        return 0, 0, 0, None, 0

    if yours:
        try:
            heavy.note(_parse_heaviness(reply))
        except Exception:
            pass

    read = _parse_appraisal(reply, feelings)
    # One line a turn, so "she didn't react" can be told apart from "the
    # reading never saw it": the model's own answer, and what it became.
    line = " ".join(re.sub(r"<think>.*?</think>", "", str(reply or ""), flags=re.DOTALL).split())
    logbook.info("mood", "read the exchange: %r -> warmth of message %d, her warmth %+d",
                 line[:80], read[0], read[2])
    return read


def _parse_heaviness(reply):
    """"normal", "rough", "heavy", or None when the line didn't say."""
    reply = re.sub(r"<think>.*?</think>", "", str(reply or ""), flags=re.DOTALL)
    found = re.findall(r"\b[0-3]\s+[-=+]\s+[-=+]\s+[A-Za-z_]+(?:\s+[0-2])?\s+(normal|rough|heavy)\b", reply, re.I)
    return found[-1].lower() if found else None


def _parse_appraisal(reply, feelings):
    # A reasoning model thinks out loud first; the answer is the last
    # line that has the right shape, not the first thing it mentions.
    reply = re.sub(r"<think>.*?</think>", "", str(reply or ""), flags=re.DOTALL)
    signs = {"-": -1, "=": 0, "+": 1}
    shape = re.compile(r"\b([0-3])\s+([-=+])\s+([-=+])\s+([A-Za-z_]+)(?:\s+([0-2])\b)?")
    found = shape.findall(reply)

    if found:
        rating, energy, warmth, feeling, flirt = found[-1]
        feeling = feeling.lower()

        return (int(rating), signs[energy], signs[warmth],
                feeling if feeling in feelings else None, int(flirt or 0))

    # A model that only managed the digit still gets its warmth counted.
    digits = re.findall(r"\b([0-3])\b", reply)

    return (int(digits[-1]) if digits else 0), 0, 0, None, 0


# ---------------------------------------------------------------------------
# /mood check: the prompt against your own last exchanges
# ---------------------------------------------------------------------------
def recent_exchanges(n=20):
    """Your last n messages with her answer to each, from history:
    [(said, answer)]. Tool rounds skipped, her last words in a turn kept."""
    from core import history

    pairs, said, answer = [], None, ""
    for m in history.get_messages_full():
        role, content = m.get("role"), m.get("content")
        text = content if isinstance(content, str) else " ".join(
            p.get("text", "") for p in content or [] if isinstance(p, dict))
        if role == "user":
            if said is not None:
                pairs.append((said, answer))
            said, answer = text.strip(), ""
        elif role == "assistant" and text.strip():
            answer = text.strip()
    if said is not None:
        pairs.append((said, answer))
    return [(s, a) for s, a in pairs if s][-max(1, int(n)):]


def _short(reply, feelings):
    r = _parse_appraisal(reply, feelings)
    flirt = r[4]
    return f"{r[0]} {'-=+'[r[1] + 1]} {'-=+'[r[2] + 1]} {r[3] or 'none'} {flirt}"


def check(model, n=20, say=print):
    """Each of your last n exchanges read by the old prompt and the new,
    side by side, and the totals: what the reader actually does on your
    model. Nothing is changed; nothing about her mood moves."""
    feelings = list((moods().get("feelings") or {}).keys())
    pairs = recent_exchanges(n)
    if not pairs:
        say("No exchanges in history to check.")
        return
    say(f"Reading your last {len(pairs)} exchanges both ways (affection energy warmth feeling flirt):")
    totals = {"before": [0, 0, 0], "now": [0, 0, 0]}       # affection>0, warmth +, flirt>0
    for said, answer in pairs:
        row = {}
        for key, template in (("before", _BEFORE_PROMPT), ("now", _APPRAISE_PROMPT)):
            try:
                reply = _ask(template, said, answer, model)
                r = _parse_appraisal(reply, feelings)
                row[key] = _short(reply, feelings)
                totals[key][0] += r[0] > 0
                totals[key][1] += r[2] > 0
                totals[key][2] += r[4] > 0
            except Exception as e:
                row[key] = f"failed: {e}"[:40]
        words = " ".join(said.split())
        say(f"  {row['before']:<22} -> {row['now']:<22} {words[:70]}{'...' if len(words) > 70 else ''}")
    for key in ("before", "now"):
        a, w, f = totals[key]
        say(f"{key:>6}: affectionate {a}/{len(pairs)}, warmed her {w}/{len(pairs)}, flirty {f}/{len(pairs)}")
