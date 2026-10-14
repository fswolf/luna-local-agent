"""Tool routing: every tool stays on, each turn gets the ones it needs.

Every schema costs context on every turn, called or not, and a local
model picks worse from forty tools than from ten. The tools pane answers
"may she ever use this"; this answers "does this turn need it".

Per turn, by group (the tools pane's groups, MCP servers' and plugins'
included):

1. Core groups always travel (tools.core: time, reminders, memory, shell).
2. The groups closest in meaning to what was said, through the
   embedding server (embedmem: llama-server or LM Studio, whatever
   EMBED_URL points at). "Is the tower up?" brings Network because it
   means network, not because of a word list.
3. Groups used in the last few turns stay (tools.sticky_turns), so "and
   restart it" doesn't lose the tool mid-job.
4. Anything else she can still reach: more_tools(group) attaches a group
   mid-turn, and calling a hidden tool by name attaches its group too.
   Both only ever reach tools this turn was allowed in the first place;
   a stream-chat turn's ceiling holds.

No embedding server, no routing: every tool goes, as before. There is
no keyword fallback on purpose; guessing from words is what tool
calling replaced.

tools.routing false sends everything, as before.
"""
import threading

import config
import logbook

from . import tool

_state = {"turn": 0, "used": {}}           # group -> turn it was last used
_turn = threading.local()                 # this turn: pool, chosen, extra


def enabled():
    return bool(getattr(config, "TOOLS_ROUTING", True))


def begin_turn():
    _state["turn"] += 1
    _turn.extra = set()


def _doc(group, entries):
    """What a group is about, for matching: its name and the first
    sentence of each of its tools' descriptions."""
    first = [(e["spec"]["function"]["description"] or "").split(". ")[0] for e in entries]
    return f"{group}. " + " ".join(first)


def _meaning(query, docs):
    """{group: similarity to what was said}, or None when the embedding
    server can't answer - and then the turn isn't routed at all."""
    try:
        import embedmem

        ranked = embedmem.rank(query, list(docs.values()))
    except Exception:
        ranked = None

    if not ranked:
        return None

    by_doc = {d: g for g, d in docs.items()}
    return {by_doc[d]: s for s, d in ranked if d in by_doc}


def choose(query, pool, group_of):
    """The tool names to send this turn, out of pool {name: entry}."""
    groups = {}

    for name, entry in pool.items():
        groups.setdefault(group_of(name), []).append(entry)

    core = set(getattr(config, "TOOLS_CORE", ["Time", "Reminders", "Memory", "Shell"]))
    top = max(1, int(getattr(config, "TOOLS_ROUTE_GROUPS", 3)))
    sticky = max(0, int(getattr(config, "TOOLS_STICKY_TURNS", 3)))
    extra = getattr(_turn, "extra", set())

    _turn.pool = pool
    _turn.group_of = group_of

    # Few enough groups that routing would save nothing: send them all.
    if len(groups) <= top + len(core & set(groups)):
        _turn.chosen = set(groups)
        _turn.hidden = {}
        return set(pool)

    scores = _meaning(query, {g: _doc(g, e) for g, e in groups.items()})

    # No embedding server (or nothing to compare): every tool, as before.
    if scores is None or not str(query or "").strip():
        _turn.chosen = set(groups)
        _turn.hidden = {}
        return set(pool)

    keep = (core | extra) & set(groups)
    keep |= {g for g, t in _state["used"].items() if g in groups and _state["turn"] - t < sticky}
    keep |= {g for _s, g in sorted((s, g) for g, s in scores.items())[-top:]}

    _turn.chosen = keep
    _turn.hidden = {g: e for g, e in groups.items() if g not in keep}

    logbook.info("tools", "routed: %s (hidden: %s)", ", ".join(sorted(keep)),
                 ", ".join(sorted(_turn.hidden)) or "none")

    return {n for n in pool if group_of(n) in keep}


def hidden():
    """{group: [entries]} not sent this turn."""
    return getattr(_turn, "hidden", {}) or {}


def allowed(name):
    """Was this tool in the turn's pool (on, available, inside the ceiling)?"""
    return name in (getattr(_turn, "pool", None) or {})


def attach(group):
    """Load a hidden group for the rest of this turn."""
    if group in hidden():
        _turn.extra = getattr(_turn, "extra", set()) | {group}
        _turn.chosen = getattr(_turn, "chosen", set()) | {group}
        _turn.hidden = {g: e for g, e in hidden().items() if g != group}
        logbook.info("tools", "attached %s mid-turn", group)
        return True

    return False


def attach_tool(name):
    """A hidden tool called by name: attach its group. True if it may run."""
    if not allowed(name):
        return False

    attach(_turn.group_of(name))
    return True


def current():
    """The names to send now, after anything attached mid-turn, or None
    when this turn wasn't routed."""
    pool = getattr(_turn, "pool", None)

    if pool is None or not hasattr(_turn, "chosen"):
        return None

    return {n for n in pool if _turn.group_of(n) in _turn.chosen}


def note_used(name, group_of):
    _state["used"][group_of(name)] = _state["turn"]


def more_tools_spec():
    """more_tools, described with exactly what's hidden this turn."""
    groups = hidden()

    if not groups:
        return None

    listing = "; ".join(f"{g} ({', '.join(e['spec']['function']['name'] for e in entries)})"
                        for g, entries in sorted(groups.items()))

    return {
        "type": "function",
        "function": {
            "name": "more_tools",
            "description": ("Not every tool is attached every turn. If you need one that isn't in your "
                            "list, load its group here and then call it. Available: " + listing),
            "parameters": {
                "type": "object",
                "properties": {"group": {"type": "string", "enum": sorted(groups)}},
                "required": ["group"],
            },
        },
    }


@tool("more_tools", "Attach a group of tools for the rest of this turn.",
      {"group": {"type": "string"}}, required=("group",))
def _more_tools(group):
    group = str(group or "").strip()
    match = next((g for g in hidden() if g.lower() == group.lower()), None)

    if match is None:
        on = sorted(getattr(_turn, "chosen", ()) or ())
        return f"No hidden group called {group!r}. Already attached: {', '.join(on) or 'none'}."

    names = [e["spec"]["function"]["name"] for e in hidden()[match]]
    attach(match)

    return f"Attached {match}: {', '.join(names)}. Call them now."
