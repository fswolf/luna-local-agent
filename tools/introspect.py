"""Looking at her own numbers.

The thought log measures things about each turn that she can't see from
the inside: how likely each token she produced actually was, what she
nearly said instead, which review flags it tripped. This hands one turn
of that back to her - on request, never pushed into every prompt,
because a model that knows its scratchpad is being read starts writing
it for an audience.

Read-only and only ever her own turns. It is not in chatroom's tool
ceiling, so a stranger in stream chat can't ask her to recite her
history; the turns it reads never include chat turns anyway, since
those aren't recorded.

What comes back is measurement, worded as measurement. What she makes
of it is generated text like anything else she says, which is why the
viewer keeps the raw numbers next to it.
"""
from datetime import datetime

import timeutil

from . import tool


def _available():
    try:
        import thoughtlog

        return thoughtlog.enabled()
    except Exception:
        return False


@tool(
    "introspect",
    "Look at measured data about one of your own earlier replies: how "
    "sure you actually were of each word (from your token probabilities), "
    "the words you nearly said instead, and any problems the review "
    "flagged. Use it when asked how confident you were, why you said "
    "something, or whether you were guessing. It describes a past reply, "
    "not the one you're writing now.",
    {
        "turns_back": {
            "type": "integer",
            "description": "Which reply: 1 is your previous one, 2 the one "
                           "before that. Defaults to 1.",
        },
    },
    available=_available,
    why=lambda: "the reasoning log is off (thoughts.enabled)",
)
def _introspect(turns_back=1):
    import config
    import thoughtlog

    try:
        back = max(1, min(int(turns_back or 1), 50))
    except (TypeError, ValueError):
        back = 1

    rows = thoughtlog.rows(limit=1, offset=back - 1)

    if not rows:
        return "There's no recorded reply that far back."

    row = rows[0]
    lines = []

    try:
        when = timeutil.relative(datetime.fromisoformat(row["timestamp"]),
                                 datetime.now())
    except (ValueError, TypeError):
        when = row["timestamp"]

    said = " ".join(row["user_text"].split())
    lines.append(f"Your reply from {when}, to: \"{said[:160]}\"")

    if row.get("n_tokens"):
        runs = thoughtlog.tokens_for(row["id"])
        shape = thoughtlog.confidence(runs)

        replied = sum(1 for run in runs for t in run if t[1] == "a")

        if shape["conf"] is not None:
            lines.append(
                f"Measured confidence (your token probabilities, not an "
                f"opinion): {shape['conf']:.0%} on average across the reply; "
                f"{shape['low']} of its {replied} tokens "
                f"{'was' if shape['low'] == 1 else 'were'} under {thoughtlog.LOW:.0%}."
            )

        for text, p, alts in thoughtlog.shakiest(runs):
            nearly = ", ".join(f"\"{a.strip() or '(end)'}\" {q:.0%}" for a, q in alts)
            lines.append(f"- \"{text.strip()}\" was only {p:.0%} likely"
                         + (f"; you nearly said {nearly}" if nearly else ""))
    elif getattr(config, "LLM_BACKEND", "") != "llama":
        lines.append("Token confidence isn't measured on this server (LM "
                     "Studio) - only on llama-server.")
    else:
        lines.append("No token confidence was recorded for that reply.")

    flags = row.get("flags") or []

    lines.append("Review flags: " + ("; ".join(flags) if flags else "none."))

    if row.get("tools"):
        lines.append("Tools you called: " + ", ".join(row["tools"]) + ".")

    if row.get("mood_e") or row.get("mood_w"):
        lines.append(f"Your mood then: {row.get('mood_e', '')}, {row.get('mood_w', '')}.")

    if row.get("highlight"):
        lines.append(f"How your thinking ended: \"{row['highlight']}\"")

    return "\n".join(lines)
