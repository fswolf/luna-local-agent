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
from types import SimpleNamespace

import config
import logbook
import turnctx

from . import tool

_state = {"turn": 0, "used": {}}           # group -> turn it was last used


def _t():
    """This turn's routing state: pool, chosen, hidden, extra, track."""
    return turnctx.current().routing


def enabled():
    return bool(getattr(config, "TOOLS_ROUTING", True))


def begin_turn(track=True):
    """A new turn: its routing state starts empty (it lives on the
    turnctx turn, so nothing can carry over from the last one). track=False
    for turns that aren't the user's own (stream chat, jobs): they don't
    advance or set the sticky groups."""
    if track:
        _state["turn"] += 1

    turnctx.current().routing = SimpleNamespace(extra=set(), track=track)


def start(pool, group_of):
    """Record what this turn may use, routed or not, so attach() and
    current() answer for this turn and no other."""
    _t().pool = pool
    _t().group_of = group_of
    _t().chosen = {group_of(n) for n in pool}
    _t().hidden = {}


_DOC_CHARS = 600   # the embedding server's context is short; a 20-tool MCP server isn't


def _doc(group, entries):
    """What a group is about, for matching: its name and the first
    sentence of each of its tools' descriptions."""
    first = [(e["spec"]["function"]["description"] or "").split(". ")[0] for e in entries]
    return (f"{group}. " + " ".join(first))[:_DOC_CHARS]


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


def choose(query, pool, group_of, previous="", quiet=False):
    """The tool names to send this turn, out of pool {name: entry}.
    previous is the user's message before this one: "yes, do it" means
    nothing alone, so the best group for what came before goes too."""
    groups = {}

    for name, entry in pool.items():
        groups.setdefault(group_of(name), []).append(entry)

    core = set(getattr(config, "TOOLS_CORE", ["Time", "Reminders", "Memory", "Shell"]))
    top = max(1, int(getattr(config, "TOOLS_ROUTE_GROUPS", 3)))
    sticky = max(0, int(getattr(config, "TOOLS_STICKY_TURNS", 3)))
    extra = getattr(_t(), "extra", set())

    start(pool, group_of)

    # Few enough groups that routing would save nothing: send them all.
    if len(groups) <= top + len(core & set(groups)) or not str(query or "").strip():
        return set(pool)

    docs = {g: _doc(g, e) for g, e in groups.items()}
    scores = _meaning(query, docs)

    # No embedding server: every tool, as before.
    if scores is None:
        return set(pool)

    def best(by, n):
        return {g for _s, g in sorted((s, g) for g, s in by.items())[-n:]}

    keep = (core | extra) & set(groups)
    keep |= {g for g, t in _state["used"].items() if g in groups and _state["turn"] - t < sticky}
    keep |= best(scores, top)

    if str(previous or "").strip():
        before = _meaning(previous, docs)    # usually cached: it was last turn's query
        keep |= best(before, 1) if before else set()

    _t().chosen = keep
    _t().hidden = {g: e for g, e in groups.items() if g not in keep}

    if not quiet:
        logbook.info("tools", "routed: %s (hidden: %s)", ", ".join(sorted(keep)),
                     ", ".join(sorted(_t().hidden)) or "none")

    return {n for n in pool if group_of(n) in keep}


def hidden():
    """{group: [entries]} not sent this turn."""
    return getattr(_t(), "hidden", {}) or {}


def allowed(name):
    """Was this tool in the turn's pool (on, available, inside the ceiling)?"""
    return name in (getattr(_t(), "pool", None) or {})


def attach(group):
    """Load a hidden group for the rest of this turn."""
    if group in hidden():
        _t().extra = getattr(_t(), "extra", set()) | {group}
        _t().chosen = getattr(_t(), "chosen", set()) | {group}
        _t().hidden = {g: e for g, e in hidden().items() if g != group}
        logbook.info("tools", "attached %s mid-turn", group)
        return True

    return False


def attach_tool(name):
    """A hidden tool called by name: attach its group. True if it may run."""
    if not allowed(name):
        return False

    attach(_t().group_of(name))
    return True


def current():
    """The names to send now, after anything attached mid-turn, or None
    when this turn wasn't routed."""
    pool = getattr(_t(), "pool", None)

    if pool is None or not hasattr(_t(), "chosen") or not hasattr(_t(), "group_of"):
        return None

    return {n for n in pool if _t().group_of(n) in _t().chosen}


def note_used(name, group_of):
    if getattr(_t(), "track", True):
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
                            "list, attach its group here, then call it. Check here before telling the "
                            "user you can't do something. Groups not attached now: " + listing),
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
        on = sorted(getattr(_t(), "chosen", ()) or ())
        return f"No hidden group called {group!r}. Already attached: {', '.join(on) or 'none'}."

    names = [e["spec"]["function"]["name"] for e in hidden()[match]]
    attach(match)

    return f"Attached {match}: {', '.join(names)}. Call them now."
