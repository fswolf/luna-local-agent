"""Reading an exchange: the short side question that asks her model how a
turn landed (a rating, energy, warmth, a feeling, flirting) and the parser
for its answer.

Part of mind/mood.py, which re-exports all of this.
"""
import re
import config
from core import logbook
from mind.mood_files import moods


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
# answer - and returns four small things on one line, which a 9B model
# manages reliably where a free-form "how does she feel?" would not:
#
#   warmth of YOUR message, 0-3      the old rating, same rules
#   energy  - = +                    did the exchange liven her up or wear her down
#   warmth  - = +                    "-" only for real hostility: bluntness is not it
#   a feeling from moods.json        shown on her face for a few seconds
#
# Still one call, still off the turn's path, still off with
# mood.affection false.
_APPRAISE_PROMPT = (
    "Read this moment from a conversation between {user} and {their} assistant, {name}.\n\n"
    "User: {said}\n{name}: {answer}\n\n"
    "Answer with one line of four fields separated by spaces, nothing else:\n"
    "1. how warm or affectionate the USER's message is toward her: 0 neutral, businesslike "
    "or blunt (swearing is not unfriendly by itself), 1 polite warmth (thanks, a friendly "
    "greeting), 2 clear affection or praise of her, 3 strong affection\n"
    "2. how the exchange leaves her energy: - (draining), = (no change), + (lively, fun)\n"
    "3. how it leaves her warmth toward {them}: - (only if the user was clearly hostile or hurtful "
    "to her), =, +\n"
    "4. the one feeling she shows right now, from: none {feelings}\n"
    "5. how flirtatious or intimate the USER's message is: 0 not at all, 1 flirting or "
    "suggestive, 2 openly intimate or sexual\n"
    "When unsure: 0 = = none 0\n"
    "Example: 2 + + laughing 1"
)


def _appraise(said, answer, model):
    """(rating 0-3, energy -1/0/1, warmth -1/0/1, feeling or None, flirt 0-2).
    (0, 0, 0, None, 0) on anything unexpected - a mood is never worth an error."""
    import requests

    from config import LM_URL, LLM_HEADERS

    feelings = list((moods().get("feelings") or {}).keys())

    try:
        from core import lmstudio

        name = getattr(config, "AGENT_NAME", "the assistant")
        prompt = _APPRAISE_PROMPT.format(name=name, said=str(said)[:600],
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
        reply = response.json()["choices"][0]["message"]["content"]
    except Exception as e:
        logbook.info("mood", "couldn't read the exchange: %s", e)

        return 0, 0, 0, None, 0

    return _parse_appraisal(reply, feelings)


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
