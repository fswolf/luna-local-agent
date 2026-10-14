"""What kind of turn is running, and what it may do.

One object per turn, carrying everything that used to be spread across
state.job, state.remote, state.untrusted, llm's `turn` dict and the
tool router's thread-local:

    who started it     source, private (his own conversation or not)
    standing passes    job (job_write_dirs), remote + approver (Discord)
    what it has seen   seen (outside content), read_local (one of his files)
    bookkeeping        lessons and skills shown, max_rounds, project_id,
                       the tool router's choices for this turn, the tool
                       calls it made (a game's turn record reads these)

It lives in a contextvars.ContextVar, so it belongs to the turn that set
it and nothing else: it ends when the turn ends, and a thread started
elsewhere (a reminder firing mid-job) starts with none, so it can never
inherit a job's write pass or a Discord approver.

    with turnctx.begin(source="job:backup", private=False, job="backup"):
        llm.ask(...)

llm.ask opens one itself when nobody has (turnctx.ensure), so callers
that don't need a pass don't have to think about this at all.
"""
import contextvars
from contextlib import contextmanager
from dataclasses import dataclass, field
from types import SimpleNamespace
from typing import Any, Callable, Optional


@dataclass
class Turn:
    source: str = "typed"              # typed, voice, discord, job:<name>, reminder, greeting...
    private: bool = True               # his own conversation: his history, his tools
    job: Optional[str] = None          # a scheduled job or game: may write in job_write_dirs
    max_rounds: Optional[int] = None   # a job's tool-round budget (None: tools.max_rounds)
    project_id: Any = None             # a game's project, for game_note
    remote: Optional[str] = None       # a remote plugin's turn ("discord")
    approver: Optional[Callable] = None  # who answers permission questions for it
    seen: Optional[str] = None         # the first outside content this turn took in
    read_local: bool = False           # set once she has read one of his files
    lessons: list = field(default_factory=list)  # lesson ids shown, credited after
    skills: list = field(default_factory=list)   # skill ids shown, credited after
    routing: SimpleNamespace = field(default_factory=SimpleNamespace)  # tools/routing.py
    exchanges: list = field(default_factory=list)  # {name, arguments, result} per tool call, in order


_current = contextvars.ContextVar("luna_turn", default=None)


def current():
    """The running turn, or a fresh blank one outside any turn. A blank
    turn carries no passes (no job, no remote, nothing seen), and what's
    written to it is dropped - there's no conversation to remember it for."""
    turn = _current.get()
    return turn if turn is not None else Turn(source="none")


def active():
    """Is a turn running here?"""
    return _current.get() is not None


@contextmanager
def begin(**fields):
    """Start a turn for the length of the with-block."""
    turn = Turn(**fields)
    token = _current.set(turn)

    try:
        yield turn
    finally:
        _current.reset(token)


@contextmanager
def ensure(**fields):
    """The running turn if there is one (a job or Discord turn began it,
    with its passes), otherwise a new one from these fields."""
    turn = _current.get()

    if turn is not None:
        yield turn
        return

    with begin(**fields) as turn:
        yield turn
