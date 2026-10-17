"""Chess - you play her on a board you drag the pieces around on.

    /chess on              set up the board (opens it in your browser)
    /chess new [black]     a new game; you're white unless you say black (or random)
    /chess e4              your move, typed (or drag it on the board, or tell her)
    /chess undo            take back your last move and her reply
    /chess resign          give up this game
    /chess nudge           remind her it's her move, if she stalled
    /chess open            open the board again
    /chess off             put it away (the game is saved)
    /chess                 the position, whose move it is, and the board's address

The board is a page Luna serves herself, next to the live view:
http://127.0.0.1:8792/chess/ . Drag a piece (or click it, then click
where it goes); the squares it can reach light up, and anything illegal
snaps back. Her moves slide in on their own, with what she said about
them beside the board. Add the same address to OBS as a browser source
and chat can watch.

python-chess keeps the game: whose move it is, what's legal, check,
mate and draws. She never has to hold the board in her head, which is
where a language model falls apart. Each of her moves is a job turn
(fresh context, nothing in your history): she's shown the board from her
side, the moves so far, her legal moves, which of her pieces are attacked
and what she can capture, then makes one move with chess_move and says a
sentence or two about it. A move that isn't legal is turned back with
the list, and doesn't use up her turn.

Moving by voice: tell her ("knight to f3", "e4", "castle kingside") and
she plays it for you with chess_user_move. /chess e4 does the same
without her.

A finished game is written to agent/chess/games/ as a PGN file, which
any chess program (or lichess's analysis board) opens.

Needs python-chess (pip install chess) and the live monitor
(monitor.enabled, on by default) for the board page.

    "chess": {
        "enabled": false,
        "side": "white",        # your colour in a new game: white, black or random
        "speak": true,          # say her comments out loud
        "open": true,           # open the board in your browser with /chess on
        "think_seconds": 1.5,   # a pause before her move, so it doesn't snap in
        "turn_seconds": 90      # a turn of hers that runs longer is cut short
    }
"""
import json
import os
import random
import re
import threading
import time

import config
import logbook

try:
    import chess
    import chess.pgn
    import chess.svg
except ImportError:          # the plugin says so instead of failing to load
    chess = None

NAME = "chess"
SUMMARY = "play chess against her on a board you can drag pieces on"

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PAGE = os.path.join(HERE, "games", "chess", "board.html")
SAVES = os.path.join(HERE, "agent", "chess")
GAME_FILE = os.path.join(SAVES, "game.json")

DEFAULTS = {"side": "white", "speak": True, "open": True, "think_seconds": 1.5, "turn_seconds": 90}
TOOLS = ["chess_board", "chess_move", "chess_user_move", "chess_new_game"]

_lock = threading.RLock()
_wake = threading.Event()
_stop = threading.Event()
_thread = None
_on = False
_g = {"board": None, "luna": None, "said": [], "result": "", "started": "", "reacted": True,
      "thinking": False, "fails": 0, "stalled": False, "model": None, "error": ""}
_turn = {"active": False, "moved": False}


def settings():
    s = dict(DEFAULTS)
    s.update({k: v for k, v in config.plugin_settings(NAME).items() if k in DEFAULTS})
    return s


def _ended(for_luna=True):
    """How the game ended, worded for her or for you; "" while it's on."""
    r = _g["result"]
    if not r:
        return ""
    if r["winner"] is None:
        return f"a draw ({r['how']})"
    if for_luna:
        return ("you won" if r["winner"] == "luna" else "the user won") + f" by {r['how']}"
    return (f"{config.AGENT_NAME} wins" if r["winner"] == "luna" else "You win") + f" by {r['how']}"


def _score():
    """The PGN result: 1-0, 0-1 or 1/2-1/2."""
    r = _g["result"]
    if not r or r["winner"] is None:
        return "1/2-1/2"
    white_won = (r["winner"] == "luna") == (_g["luna"] == chess.WHITE)
    return "1-0" if white_won else "0-1"


def _emit():
    try:
        import livefeed

        livefeed.emit("chess")
    except Exception:
        pass


def _say(text):
    try:
        import ui

        ui.add_message("system", text)
    except Exception:
        pass


# ---------------------------------------------------------------------------
# The game
# ---------------------------------------------------------------------------
def _color_name(color):
    return "white" if color == chess.WHITE else "black"


def _new(side=None):
    side = (side or settings()["side"] or "white").lower()
    if side not in ("white", "black"):
        side = random.choice(("white", "black"))
    with _lock:
        _g.update(board=chess.Board(), luna=chess.BLACK if side == "white" else chess.WHITE,
                  said=[], result=None, started=time.strftime("%Y-%m-%d %H:%M"), reacted=True,
                  fails=0, stalled=False)
        _save()
    _emit()
    _wake.set()
    return side


def _load():
    try:
        with open(GAME_FILE, encoding="utf-8") as f:
            data = json.load(f)
        board = chess.Board()
        for uci in data.get("moves", []):
            board.push_uci(uci)
        _g.update(board=board, luna=chess.WHITE if data.get("luna") == "white" else chess.BLACK,
                  said=list(data.get("said", []))[-60:], result=data.get("result") or None,
                  started=data.get("started", ""), reacted=True, fails=0, stalled=False)
        return True
    except (OSError, ValueError, KeyError, TypeError):
        return False


def _save():
    try:
        os.makedirs(SAVES, exist_ok=True)
        data = {"moves": [m.uci() for m in _g["board"].move_stack], "luna": _color_name(_g["luna"]),
                "said": _g["said"][-60:], "result": _g["result"], "started": _g["started"]}
        tmp = GAME_FILE + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(data, f)
        os.replace(tmp, GAME_FILE)
    except OSError as e:
        logbook.warn(NAME, "couldn't save the game: %s", e)


def _san_history(board):
    """'1. e4 e5 2. Nf3 Nc6' for the moves so far."""
    replay, parts = chess.Board(), []
    for move in board.move_stack:
        if replay.turn == chess.WHITE:
            parts.append(f"{replay.fullmove_number}.")
        parts.append(replay.san(move))
        replay.push(move)
    return " ".join(parts)


def _finish_if_over():
    """Record the result once the game has ended; True if it has."""
    board = _g["board"]
    outcome = board.outcome(claim_draw=True)
    if not outcome or _g["result"]:
        return bool(_g["result"])
    how = outcome.termination.name.replace("_", " ").lower()
    winner = None if outcome.winner is None else ("luna" if outcome.winner == _g["luna"] else "user")
    _g["result"] = {"winner": winner, "how": how}
    _g["reacted"] = False
    _end_game()
    return True


def _end_game():
    """The PGN, the playlog and her memory, once the game is over."""
    board = _g["board"]
    try:
        game = chess.pgn.Game.from_board(board)
        luna, you = config.AGENT_NAME, "You"
        game.headers.update(Event="Casual game", Site="Luna", Date=_g["started"][:10].replace("-", "."),
                            White=luna if _g["luna"] == chess.WHITE else you,
                            Black=luna if _g["luna"] == chess.BLACK else you)
        game.headers["Result"] = _score()
        folder = os.path.join(SAVES, "games")
        os.makedirs(folder, exist_ok=True)
        with open(os.path.join(folder, f"{time.strftime('%Y-%m-%d-%H%M')}.pgn"), "w", encoding="utf-8") as f:
            f.write(str(game) + "\n")
    except Exception as e:
        logbook.warn(NAME, "couldn't write the PGN: %s", e)
    _save()


def user_move(text):
    """Your move: from the board, /chess, or her chess_user_move."""
    with _lock:
        board = _g["board"]
        if board is None:
            return False, "No game yet - /chess new."
        if _g["result"]:
            return False, f"This game is over ({_ended(False)}). /chess new for another."
        if board.turn == _g["luna"]:
            return False, f"It's {config.AGENT_NAME}'s move, not yours."
        move = _parse(board, text)
        if move is None:
            return False, (f"'{text}' isn't a legal move here. Legal: "
                           + ", ".join(sorted(board.san(m) for m in board.legal_moves)))
        san = board.san(move)
        board.push(move)
        _g.update(fails=0, stalled=False)
        _finish_if_over()
        _save()
    _emit()
    _wake.set()
    return True, f"You played {san}." + (f" {_ended(False)}." if _g["result"] else "")


def luna_move(text):
    """Her move, through chess_move."""
    with _lock:
        board = _g["board"]
        if board is None:
            return "There's no game going. Start one with chess_new_game."
        if _g["result"]:
            return f"The game is over ({_ended()})."
        if board.turn != _g["luna"]:
            return "It's the user's move, not yours - wait for them."
        if _turn["active"] and _turn["moved"]:
            return "You've already made your move this turn. Say a sentence about it and stop."
        move = _parse(board, text)
        if move is None:
            return (f"'{text}' isn't one of your legal moves - nothing was played, your move is still "
                    "yours. Legal moves: " + ", ".join(sorted(board.san(m) for m in board.legal_moves)))
        san = board.san(move)
        board.push(move)
        _turn["moved"] = True
        _g.update(fails=0, stalled=False)
        over = _finish_if_over()
        _save()
    _emit()
    return f"You played {san}." + (f" The game is over: {_ended()}." if over else "")


_PIECES = {"king": "K", "queen": "Q", "rook": "R", "castle": "R", "bishop": "B", "knight": "N",
           "horse": "N", "pawn": ""}


def _parse(board, text):
    """A legal move from SAN (Nf3), UCI (g1f3) or speech ("knight to f3",
    "pawn takes d5", "castle kingside", "e4"); None if it isn't one."""
    raw = str(text or "").strip()
    if not raw:
        return None
    for attempt in (raw, raw.replace("0", "O")):
        try:
            return board.parse_san(attempt)
        except ValueError:
            pass
    try:
        move = chess.Move.from_uci(raw.lower())
        if move in board.legal_moves:
            return move
        promo = chess.Move.from_uci(raw.lower() + "q")
        if promo in board.legal_moves:
            return promo
    except ValueError:
        pass

    words = re.sub(r"[^a-z0-9 ]", " ", raw.lower()).split()
    joined = " ".join(words)
    if "castle" in words or "castles" in words or "castling" in words:
        side = "O-O-O" if any(w in words for w in ("queenside", "queen", "long")) else "O-O"
        try:
            return board.parse_san(side)
        except ValueError:
            return None
    square = next((w for w in reversed(words) if re.fullmatch(r"[a-h][1-8]", w)), None)
    if not square:
        return None
    target = chess.parse_square(square)
    piece = next((_PIECES[w] for w in words if w in _PIECES and w != "castle"), None)
    promote = None
    m = re.search(r"(promot\w*|becomes|to a?)\s+(queen|rook|bishop|knight)", joined)
    if m and piece == "":
        promote = chess.Piece.from_symbol(_PIECES[m.group(2)]).piece_type
    candidates = []
    for move in board.legal_moves:
        if move.to_square != target:
            continue
        mover = board.piece_at(move.from_square)
        if piece is not None and mover.symbol().upper() != (piece or "P"):
            continue
        if move.promotion and move.promotion != (promote or chess.QUEEN):
            continue
        candidates.append(move)
    if piece is None and len(candidates) > 1:     # "e4" alone means a pawn when one can go there
        pawns = [m for m in candidates if board.piece_type_at(m.from_square) == chess.PAWN]
        candidates = pawns or candidates
    return candidates[0] if len(candidates) == 1 else None


def undo():
    """Take back your last move, and her reply to it."""
    with _lock:
        board = _g["board"]
        if board is None:
            return False, "Nothing to take back."
        you = not _g["luna"]
        if len(board.move_stack) < (1 if you == chess.WHITE else 2):
            return False, "You haven't moved yet."
        if _g["thinking"]:
            return False, "She's thinking - wait for her move first."
        while board.move_stack:
            board.pop()
            if board.turn == you:          # that was your move: stop here
                break
        _g.update(result=None, reacted=True, fails=0, stalled=False)
        _save()
    _emit()
    _wake.set()
    return True, "Taken back - your move."


def resign():
    with _lock:
        if _g["board"] is None or _g["result"]:
            return False, "No game in progress."
        _g.update(result={"winner": "luna", "how": "resignation"}, reacted=False)
        _end_game()
    _emit()
    _wake.set()
    return True, "You resigned. /chess new for another."


# ---------------------------------------------------------------------------
# What she's shown
# ---------------------------------------------------------------------------
def _diagram(board, color):
    """The board as text, from her side, with files and ranks."""
    ranks = range(7, -1, -1) if color == chess.WHITE else range(8)
    files = range(8) if color == chess.WHITE else range(7, -1, -1)
    rows = []
    for r in ranks:
        cells = [(board.piece_at(chess.square(f, r)) or ".").__str__() for f in files]
        rows.append(f"{r + 1}  " + " ".join(cells))
    rows.append("   " + " ".join("abcdefgh"[f] for f in files))
    return "\n".join(rows)


_NAMES = {chess.PAWN: "pawn", chess.KNIGHT: "knight", chess.BISHOP: "bishop", chess.ROOK: "rook",
          chess.QUEEN: "queen", chess.KING: "king"}
_VALUE = {chess.PAWN: 1, chess.KNIGHT: 3, chess.BISHOP: 3, chess.ROOK: 5, chess.QUEEN: 9, chess.KING: 0}


def _threats(board, color):
    """Her pieces that are attacked, and how well defended."""
    out = []
    for square, piece in board.piece_map().items():
        if piece.color != color or piece.piece_type == chess.KING:
            continue
        attackers = board.attackers(not color, square)
        if not attackers:
            continue
        defenders = len(board.attackers(color, square))
        cheapest = min(_VALUE[board.piece_type_at(a)] for a in attackers)
        danger = "UNDEFENDED" if not defenders else (
            "attacked by something cheaper" if cheapest < _VALUE[piece.piece_type] else f"defended {defenders}x")
        out.append(f"your {_NAMES[piece.piece_type]} on {chess.square_name(square)} ({danger})")
    return out


def _captures(board):
    out = []
    for move in board.legal_moves:
        if board.is_capture(move):
            victim = board.piece_at(move.to_square)
            name = _NAMES[victim.piece_type] if victim else "pawn"     # en passant
            safe = not board.attackers(not board.turn, move.to_square)
            out.append(f"{board.san(move)} takes a {name}" + (" (and it isn't defended)" if safe else ""))
    return out


def describe(for_luna=True):
    """The game as text: for chess_board, /chess and her turn prompt."""
    with _lock:
        board = _g["board"]
        if board is None:
            return "No game yet."
        luna = _g["luna"]
        if not for_luna:
            return "\n".join([_diagram(board, not luna), "Moves: " + (_san_history(board) or "none yet"),
                              state()["status"]])
        lines = [f"You're playing {_color_name(luna)}; the user is {_color_name(not luna)}.",
                 "The board from your side (capitals are White, small letters Black, . is empty):",
                 _diagram(board, luna),
                 "Moves so far: " + (_san_history(board) or "none yet")]
        if board.move_stack:
            last = board.pop()
            san = board.san(last)
            board.push(last)
            who = "You" if board.turn != luna else "The user"
            lines.append(f"Last move: {who} played {san}.")
        if _g["result"]:
            lines.append(f"The game is over: {_ended()}.")
        elif board.turn == luna:
            if board.is_check():
                lines.append("You're in CHECK: your move has to get out of it.")
            lines.append("It's your move. Your legal moves: "
                         + ", ".join(sorted(board.san(m) for m in board.legal_moves)))
            threats, caps = _threats(board, luna), _captures(board)
            lines.append("Under attack: " + ("; ".join(threats) if threats else "nothing"))
            lines.append("Captures you can make: " + ("; ".join(caps) if caps else "none"))
        else:
            lines.append("It's the user's move.")
        return "\n".join(lines)


STEP_PROMPT = (
    "(You're playing chess against the user, on a board they can see.\n{game}\n\n"
    "Choose ONE move from your legal moves and play it with chess_move (like Nf6, exd5, O-O). "
    "First look at their last move: what does it attack or threaten? Don't leave a piece "
    "undefended, take free material when it's offered, and get out of check if you're in it. "
    "Then talk to the user in one or two short sentences, in your own voice: what you played and "
    "why, a bit playful. No move lists, no board, no notation except your own move.)"
)

REACT_PROMPT = (
    "(Your chess game against the user just ended: {result}.\n{game}\n\n"
    "Say one or two sentences to the user about the game, in your own voice: gracious if you lost, "
    "pleased but kind if you won. Don't call any tools.)"
)


def _step():
    import assistant

    s = settings()
    react = bool(_g["result"]) and not _g["reacted"]
    prompt = (REACT_PROMPT if react else STEP_PROMPT).format(
        game=describe(), result=_ended())
    allowed = ["chess_board"] if react else ["chess_board", "chess_move"]

    if not react:
        _stop.wait(float(s["think_seconds"] or 0))
    _g["thinking"] = not react
    _emit()
    _turn.update(active=True, moved=False)
    exchanges = []
    try:
        answer = assistant.respond_to_job(prompt, _g["model"], "chess", allowed, speak=bool(s["speak"]),
                                          max_rounds=1 if react else 4, exchanges=exchanges,
                                          time_limit=float(s["turn_seconds"] or 0) or None) or ""
    finally:
        _turn["active"] = False
        _g["thinking"] = False

    with _lock:
        if react:
            _g["reacted"] = True
        elif not _turn["moved"] and _g["board"].turn == _g["luna"] and not _g["result"]:
            _g["fails"] += 1
            if _g["fails"] >= 2:
                _g["stalled"] = True
                _say("Chess: she didn't move twice in a row - /chess nudge to let her try again.")
        said = answer.strip()
        if said:
            _g["said"] = (_g["said"] + [{"ply": len(_g["board"].move_stack), "text": said[:600]}])[-60:]
        _save()
    _emit()

    from plugins import _playlog

    _playlog.write(NAME, len(_g["board"].move_stack), answer)
    _playlog.remember(NAME, "chess", answer, exchanges)
    if react:
        _playlog.finished(NAME)


def _play():
    while not _stop.is_set():
        _wake.wait(2)
        _wake.clear()
        with _lock:
            board = _g["board"]
            due = (_on and board is not None and not _g["stalled"] and
                   ((not _g["result"] and board.turn == _g["luna"]) or (_g["result"] and not _g["reacted"])))
        if not due:
            continue
        try:
            _step()
        except Exception as e:
            _g["error"] = str(e)[:200]
            logbook.exception(NAME, "turn failed")
            _stop.wait(10)


# ---------------------------------------------------------------------------
# The board page (served by livefeed at /chess/)
# ---------------------------------------------------------------------------
def state():
    with _lock:
        board = _g["board"]
        if board is None:
            return {"on": _on, "game": False}
        legal = {}
        your_turn = not _g["result"] and board.turn != _g["luna"]
        if your_turn:
            for m in board.legal_moves:
                legal.setdefault(chess.square_name(m.from_square), []).append(
                    chess.square_name(m.to_square) + (chess.piece_symbol(m.promotion) if m.promotion else ""))
        last = board.peek() if board.move_stack else None
        king = board.king(board.turn) if board.is_check() else None
        if _g["result"]:
            status = _ended(False)
        elif _g["thinking"] or (board.turn == _g["luna"] and not _g["stalled"]):
            status = f"{config.AGENT_NAME} is thinking..."
        elif board.turn == _g["luna"]:
            status = f"{config.AGENT_NAME} didn't move - /chess nudge"
        else:
            status = "Your move" + (" - you're in check" if board.is_check() else "")
        return {"on": _on, "game": True, "fen": board.board_fen(), "you": _color_name(not _g["luna"]),
                "luna": config.AGENT_NAME, "yourTurn": your_turn, "legal": legal, "status": status,
                "last": [chess.square_name(last.from_square), chess.square_name(last.to_square)] if last else None,
                "check": chess.square_name(king) if king is not None else None,
                "history": _san_history(board), "said": _g["said"][-12:], "over": bool(_g["result"])}


def _json(data, code=200):
    return code, "application/json", json.dumps(data)


def page(method, path, body):
    if not _on:
        return 404, "text/plain; charset=utf-8", "The chess plugin is off - /chess on."
    if method == "GET" and path in ("/", ""):
        with open(PAGE, encoding="utf-8") as f:
            return 200, "text/html; charset=utf-8", f.read()
    if method == "GET" and path == "/state":
        return _json(state())
    m = re.fullmatch(r"/piece/([wb])([KQRBNP])\.svg", path) if method == "GET" else None
    if m:
        symbol = m.group(2) if m.group(1) == "w" else m.group(2).lower()
        return 200, "image/svg+xml", chess.svg.piece(chess.Piece.from_symbol(symbol))
    if method == "POST":
        try:
            data = json.loads(body or b"{}")
        except ValueError:
            data = {}
        if path == "/move":
            ok, message = user_move(str(data.get("move", ""))[:10])
            return _json({"ok": ok, "message": message, "state": state()})
        if path == "/action":
            action = data.get("action")
            if action == "new":
                _new(data.get("side"))
                ok, message = True, "New game."
            elif action == "undo":
                ok, message = undo()
            elif action == "resign":
                ok, message = resign()
            elif action == "nudge":
                ok, message = _nudge()
            else:
                ok, message = False, "unknown action"
            return _json({"ok": ok, "message": message, "state": state()})
    return 404, "text/plain; charset=utf-8", "not found"


def _nudge():
    with _lock:
        _g.update(stalled=False, fails=0)
    _wake.set()
    return True, "Nudged - her move."


try:
    import livefeed

    livefeed.add_page(NAME, "chess", page, visible=lambda: _on)
except Exception:
    pass


# ---------------------------------------------------------------------------
# Plugin interface
# ---------------------------------------------------------------------------
def why_unavailable():
    if chess is None:
        return "pip install chess"
    if not os.path.exists(PAGE):
        return f"missing {PAGE}"
    return ""


def available():
    return not why_unavailable()


def running():
    return _on


def board_url():
    import livefeed

    return livefeed.url() + "/chess/"


def _open_board():
    if not getattr(config, "MONITOR_ENABLED", True):
        return "The board page needs the live monitor - set monitor.enabled to true and restart."
    import webbrowser

    threading.Thread(target=webbrowser.open, args=(board_url(),), daemon=True).start()
    return f"The board: {board_url()}"


def start(model):
    global _thread, _on
    problem = why_unavailable()
    if problem:
        return False, problem
    if _on:
        return True, "chess: already set up"
    _g["model"] = model
    with _lock:
        resumed = _load()
        if not resumed:
            _new()
    _on = True
    _stop.clear()
    _thread = threading.Thread(target=_play, daemon=True, name="chess")
    _thread.start()
    _wake.set()
    opened = _open_board() if settings()["open"] else f"The board: {board_url()}"
    return True, ("chess: " + ("carrying on the saved game. " if resumed else "new game - you're "
                               f"{_color_name(not _g['luna'])}. ") + opened)


def stop():
    global _on
    _on = False
    _stop.set()
    _wake.set()
    with _lock:
        if _g["board"] is not None:
            _save()
    from plugins import _playlog

    _playlog.finished(NAME)
    _emit()
    return True, "chess: put away (the game is saved)"


def status():
    if not _on:
        return "chess: off - /chess on"
    lines = ["chess: on - " + board_url(), describe(for_luna=False)]
    if _g["error"]:
        lines.append(f"  last error: {_g['error']}")
    return "\n".join(lines)


def command(text):
    word = text.strip()
    low = word.lower()
    if not _on:
        return "chess: set it up first - /chess on"
    if low.startswith("new"):
        side = low[3:].strip() or None
        return f"chess: new game - you're {_new(side)}."
    if low in ("undo", "takeback", "take back"):
        return "chess: " + undo()[1]
    if low == "resign":
        return "chess: " + resign()[1]
    if low == "nudge":
        return "chess: " + _nudge()[1]
    if low in ("open", "board", "show"):
        return "chess: " + _open_board()
    return "chess: " + user_move(word)[1]


def prompt_line(private=True):
    if not _on or _g["board"] is None:
        return ""
    return ("\nYou're in a chess game with the user on a board they can see "
            "(chess_board shows it). Your own moves happen on their own turn; if they tell you "
            "their move out loud, play it for them with chess_user_move.")


# ---------------------------------------------------------------------------
# Her tools
# ---------------------------------------------------------------------------
def _register_tools():
    import tools

    off = lambda: "the chess plugin is off - /chess on"  # noqa: E731

    tools.register_external(
        "chess_board", "See the chess game: the board, the moves so far, whose move it is, and "
        "your legal moves when it's yours.", {}, run=lambda: describe(), group="Chess",
        available=running, why=off)
    tools.register_external(
        "chess_move", "Make YOUR move in the chess game, in standard notation (Nf3, exd5, O-O, "
        "e8=Q). Only when it's your move; one move.",
        {"move": {"type": "string", "description": "Your move, like Nf3 or exd5."}},
        required=("move",), run=lambda move="": luna_move(move), group="Chess",
        available=running, why=off)
    tools.register_external(
        "chess_user_move", "Play the USER's move in the chess game when they tell it to you, in "
        "any words: 'knight to f3', 'e4', 'pawn takes d5', 'castle kingside'. Only ever their move, "
        "never yours.",
        {"move": {"type": "string", "description": "Their move, as they said it."}},
        required=("move",), run=lambda move="": user_move(move)[1], group="Chess",
        available=running, why=off)
    tools.register_external(
        "chess_new_game", "Start a new chess game when the user asks for one. side is the "
        "user's colour: white, black or random.",
        {"side": {"type": "string", "enum": ["white", "black", "random"],
                  "description": "The user's colour."}},
        run=lambda side="white": f"New game - they're {_new(side)}. The board is at {board_url()}.",
        group="Chess", available=running, why=off)


if chess is not None:
    _register_tools()
