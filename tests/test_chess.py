"""Chess: the game is python-chess's, so these check the parts around it -
reading your move however you say it, whose turn it is, her one move a
turn, take-backs, the end of a game and its PGN, and the board page's
answers. A temporary save folder; no model, no browser.

    python -m unittest discover tests        (from the repo folder)
"""
import json
import os
import shutil
import sys
import tempfile
import unittest
from unittest import mock

# The repo on the path, so this also runs on its own: python tests/<this file>
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from tests.offline import FAKE  # noqa: E402,F401  (first: no real servers)

try:
    import chess
except ImportError:          # python-chess not installed: nothing to test
    chess = None

if chess is not None:
    from plugins import chessgame as cg


@unittest.skipIf(chess is None, "pip install chess")
class Game(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.patches = [mock.patch.object(cg, "SAVES", self.tmp),
                        mock.patch.object(cg, "GAME_FILE", os.path.join(self.tmp, "game.json")),
                        mock.patch.object(cg, "_on", True),
                        mock.patch.object(cg, "_emit")]
        for p in self.patches:
            p.start()
        cg._new("white")

    def tearDown(self):
        for p in self.patches:
            p.stop()
        cg._loop._wake.clear()
        shutil.rmtree(self.tmp)

    def board(self):
        return cg._g["board"]

    def test_your_move_however_you_say_it(self):
        b = chess.Board()
        for said, want in (("e4", "e2e4"), ("Nf3", "g1f3"), ("knight to f3", "g1f3"),
                           ("g1f3", "g1f3"), ("pawn to d4", "d2d4"), ("horse c3", "b1c3")):
            self.assertEqual(cg._parse(b, said), chess.Move.from_uci(want), said)
        self.assertIsNone(cg._parse(b, "queen to h5"))       # not legal yet
        self.assertIsNone(cg._parse(b, "banana"))

    def test_castling_out_loud(self):
        b = chess.Board("r3k2r/8/8/8/8/8/8/R3K2R w KQkq - 0 1")
        self.assertEqual(cg._parse(b, "castle kingside"), chess.Move.from_uci("e1g1"))
        self.assertEqual(cg._parse(b, "castle queenside"), chess.Move.from_uci("e1c1"))
        self.assertEqual(cg._parse(b, "0-0"), chess.Move.from_uci("e1g1"))

    def test_turns(self):
        self.assertIn("not yours", cg.luna_move("e5"))           # white (you) to move
        ok, _ = cg.user_move("e4")
        self.assertTrue(ok)
        ok, msg = cg.user_move("d4")
        self.assertFalse(ok)
        self.assertIn("move, not yours", msg)
        self.assertIn("You played e5", cg.luna_move("e5"))

    def test_an_illegal_move_doesnt_use_up_her_turn(self):
        cg.user_move("e4")
        cg._turn.update(active=True, moved=False)
        try:
            self.assertIn("isn't one of your legal moves", cg.luna_move("Ke7"))
            self.assertIn("You played", cg.luna_move("e5"))
            cg.user_move("Nf3")
            self.assertIn("already made your move", cg.luna_move("Nc6"))
        finally:
            cg._turn["active"] = False

    def test_take_back_your_move_and_her_reply(self):
        cg.user_move("e4"); cg.luna_move("e5"); cg.user_move("Nf3"); cg.luna_move("Nc6")
        ok, _ = cg.undo()
        self.assertTrue(ok)
        self.assertEqual(cg._san_history(self.board()), "1. e4 e5")
        self.assertEqual(self.board().turn, chess.WHITE)

    def test_take_back_as_black(self):
        cg._new("black")
        self.assertFalse(cg.undo()[0])                        # you haven't moved
        cg.luna_move("e4"); cg.user_move("e5"); cg.luna_move("Nf3")
        cg.undo()
        self.assertEqual(cg._san_history(self.board()), "1. e4")

    def test_checkmate_ends_it_and_writes_a_pgn(self):
        cg._new("white")
        cg.user_move("f3"); cg.luna_move("e5"); cg.user_move("g4")
        self.assertIn("game is over: you won by checkmate", cg.luna_move("Qh4"))
        self.assertFalse(cg._g["reacted"])                    # she gets to say something
        self.assertFalse(cg.user_move("e4")[0])
        pgns = os.listdir(os.path.join(self.tmp, "games"))
        with open(os.path.join(self.tmp, "games", pgns[0])) as f:
            text = f.read()
        self.assertIn('[Result "0-1"]', text)
        self.assertIn('[Black "Luna"]', text)

    def test_resigning(self):
        cg.user_move("e4")
        ok, _ = cg.resign()
        self.assertTrue(ok)
        self.assertEqual(cg._score(), "0-1")
        self.assertEqual(cg.state()["status"], "Luna wins by resignation")

    def test_saved_and_picked_up(self):
        cg.user_move("e4"); cg.luna_move("c5")
        cg._g["board"] = None
        self.assertTrue(cg._load())
        self.assertEqual(cg._san_history(self.board()), "1. e4 c5")

    def test_what_she_sees(self):
        cg.user_move("e4"); cg.luna_move("d5"); cg.user_move("Bb5")
        text = cg.describe()
        self.assertIn("CHECK", text)
        self.assertIn("Your legal moves:", text)
        self.assertIn("your pawn on d5 (defended 1x)", text)
        rows = text.splitlines()
        self.assertTrue(rows[2].startswith("1  R N . K Q"))       # from black's side: rank 1 on top, h to a
        self.assertIn("h g f e d c b a", text)

    def test_threats_and_captures(self):
        cg.user_move("e4"); cg.luna_move("d5")
        caps = cg._captures(self.board())
        self.assertTrue(any(c.startswith("exd5 takes a pawn") for c in caps))
        cg.user_move("Qh5")                       # the queen joins in on d5; her move
        threats = cg._threats(self.board(), chess.BLACK)
        self.assertIn("your pawn on d5 (defended 1x)", threats)

    def test_the_page(self):
        code, kind, body = cg.page("GET", "/state", b"")
        self.assertEqual(code, 200)
        state = json.loads(body)
        self.assertTrue(state["yourTurn"])
        self.assertIn("e4", state["legal"]["e2"])
        code, kind, body = cg.page("GET", "/piece/wN.svg", b"")
        self.assertEqual(kind, "image/svg+xml")
        self.assertIn("<svg", body)
        code, kind, body = cg.page("POST", "/move", b'{"move": "e2e4"}')
        self.assertTrue(json.loads(body)["ok"])
        code, kind, body = cg.page("POST", "/move", b'{"move": "e2e4"}')
        self.assertFalse(json.loads(body)["ok"])              # not your move now
        self.assertEqual(cg.page("GET", "/../../etc/passwd", b"")[0], 404)

    def test_the_page_is_gone_when_off(self):
        with mock.patch.object(cg, "_on", False):
            self.assertEqual(cg.page("GET", "/state", b"")[0], 404)


@unittest.skipIf(chess is None, "pip install chess")
class LivePage(unittest.TestCase):
    def test_registered_and_linked_only_while_on(self):
        from web import livefeed
        self.assertIn("chess", livefeed.PAGES)
        with mock.patch.object(cg, "_on", False):
            self.assertNotIn("/chess/", livefeed.with_switcher("<body></body>", "live"))
        with mock.patch.object(cg, "_on", True):
            self.assertIn('href="/chess/"', livefeed.with_switcher("<body></body>", "live"))


if __name__ == "__main__":
    unittest.main()
