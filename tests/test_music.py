"""Her ears for music (life/music.py, server/music/listen.py). The player,
the recording and the service are faked; the service's own helpers are
tested when numpy is there (Essentia isn't needed for these)."""
import io
import os
import sys
import unittest
import wave
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from tests.offline import FAKE  # noqa: E402,F401  (first: no real servers)

import config  # noqa: E402
from life import music  # noqa: E402

ANSWER = {"kind": "music", "styles": [["Electronic---Dub Techno", 0.62], ["Electronic---Techno", 0.4], ["Electronic---Ambient", 0.05]],
          "bpm": 64.0, "beats": [0.4, 0.87], "beat_conf": 3.2, "loud": -14.0, "bass": 0.5, "secs": 8, "model": True}


class Summary(unittest.TestCase):
    def test_reads_the_answer(self):
        s = music.summary(ANSWER, started=1000.0)
        self.assertEqual(s["style"], "dub techno")
        self.assertEqual(s["styles"], ["dub techno", "techno"])
        self.assertEqual(s["bpm"], 128)                       # 64 is really 128
        self.assertEqual(s["beat_at"], 1000.4)
        self.assertTrue(s["rave"] and s["energetic"])

    def test_calm_and_talk(self):
        calm = dict(ANSWER, styles=[["Electronic---Ambient", 0.7]], bpm=80, loud=-25)
        s = music.summary(calm, 0)
        self.assertFalse(s["rave"] or s["energetic"])
        talk = music.summary(dict(ANSWER, kind="speech"), 0)
        self.assertFalse(talk["energetic"])

    def test_beat_period_from_the_beats(self):
        beats = [0.5 + i * 0.4688 for i in range(16)]          # 128.0 BPM
        s = music.summary(dict(ANSWER, beats=beats, bpm=129.0), 0)
        self.assertEqual(s["bpm"], 129)
        self.assertAlmostEqual(s["beat_bpm"], 128.0, places=1)  # the pulse keeps the beats' own time
        self.assertEqual(music.period([], 120), 0.5)

    def test_tempo(self):
        self.assertEqual([music.tempo(b) for b in (64, 128, 200, 0)], [128, 128, 100, 0])


class Track(unittest.TestCase):
    def setUp(self):
        self.events = []
        self.now_playing = (True, "spotify|Artist|Song", "Artist - Song")
        music._state.update(track=None, title="", since=0.0, asked=False, answer=None, playing=False, cache={}, sent=None)
        self.p = [mock.patch.object(music, "_emit", lambda k, **d: self.events.append((k, d))),
                  mock.patch.object(music, "player", lambda: self.now_playing),
                  mock.patch.object(music, "_talking", lambda: False),
                  mock.patch.object(music, "record", lambda s: b"\0\0" * 1600),
                  mock.patch.object(music, "ask", lambda wav: ANSWER),
                  mock.patch.object(music.threading, "Thread", lambda target, **k: mock.Mock(start=target)),
                  mock.patch.object(config, "MUSIC_URL", "http://server:8795", create=True),
                  mock.patch.object(config, "MUSIC_AFTER", 10, create=True)]
        for p in self.p:
            p.start()

    def tearDown(self):
        for p in self.p:
            p.stop()

    def music_events(self):
        return [d for k, d in self.events if k == "music"]

    def test_listens_once_ten_seconds_in(self):
        music.tick(now=100)
        music.tick(now=105)
        self.assertIsNone(music._state["answer"])
        music.tick(now=111)
        self.assertEqual(music._state["answer"]["style"], "dub techno")
        on = self.music_events()[-1]
        self.assertTrue(on["on"] and on["rave"] and on["bpm"] == 128)
        self.assertIn("dub techno", music.describe())
        self.assertIn("Artist - Song", music.describe())
        n = len(self.events)
        music.tick(now=130)                                   # no second look, no repeat event
        self.assertEqual(len(self.events), n)

    def test_pause_and_next_track(self):
        music.tick(now=0)
        music.tick(now=11)
        self.now_playing = (False, "spotify|Artist|Song", "Artist - Song")
        music.tick(now=20)
        self.assertEqual(self.music_events()[-1], {"on": False})
        self.assertEqual(music.describe(), "")
        self.now_playing = (True, "spotify|Artist|Song", "Artist - Song")
        music.tick(now=30)                                    # back on: the style it had, but the beat is lost
        self.assertTrue(self.music_events()[-1]["on"])
        self.assertIsNone(self.music_events()[-1]["beat_at"])
        music.tick(now=41)                                    # so it listens again to find the beat
        self.assertIsNotNone(self.music_events()[-1]["beat_at"])
        self.now_playing = (True, "spotify|Other|Tune", "Other - Tune")
        music.tick(now=40)
        self.assertEqual(self.music_events()[-1], {"on": False})
        self.assertIsNone(music._state["answer"])

    def test_waits_while_she_talks(self):
        with mock.patch.object(music, "_talking", lambda: True):
            music.tick(now=0)
            music.tick(now=20)
        self.assertIsNone(music._state["answer"])
        music.tick(now=21)
        self.assertIsNotNone(music._state["answer"])

    def test_counts_only_playing_time(self):
        self.now_playing = (False, "spotify|Artist|Song", "Artist - Song")
        music.tick(now=0)
        music.tick(now=30)                                    # paused all along
        self.now_playing = (True, "spotify|Artist|Song", "Artist - Song")
        music.tick(now=31)
        self.assertIsNone(music._state["answer"])
        music.tick(now=42)
        self.assertIsNotNone(music._state["answer"])

    def test_one_listen_at_a_time(self):
        self.assertTrue(music._listening.acquire(blocking=False))
        try:
            self.assertIsNone(music.listen_now())
        finally:
            music._listening.release()

    def test_a_failure_says_why(self):
        with mock.patch.object(music, "record", return_value=b"x" * 100), \
                mock.patch.object(music, "ask", side_effect=RuntimeError("404 at /health/listen")):
            self.assertIsNone(music.listen_now())
        self.assertIn("404 at /health/listen", music._state["why"])

    def test_off_without_url(self):
        with mock.patch.object(config, "MUSIC_URL", "", create=True):
            self.assertFalse(music.enabled())

    def test_wav(self):
        with wave.open(io.BytesIO(music.as_wav(b"\0\0" * 160))) as w:
            self.assertEqual((w.getframerate(), w.getnchannels(), w.getnframes()), (16000, 1, 160))


try:
    import numpy  # noqa: F401
    HERE = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "server", "music")
    sys.path.insert(0, HERE)
    import listen  # noqa: E402
except ImportError:
    listen = None


@unittest.skipIf(listen is None, "numpy isn't installed")
class MusicNow(unittest.TestCase):
    """Real threads here: Track's setUp runs every Thread inline."""

    def test_music_now_waits_for_a_listen_under_way(self):
        """/music now landing on the track's own listen used to say it couldn't."""
        import threading
        heard = dict(music.summary(ANSWER, 1000.0))
        self.addCleanup(music._state.update, answer=None)
        music._listening.acquire()
        got = []
        t = threading.Thread(target=lambda: got.append(music.listen_now(wait=True)))
        t.start()
        t.join(0.2)
        self.assertEqual(got, [])                          # waiting, not failing
        music._state["answer"] = heard
        music._listening.release()
        t.join(2)
        self.assertEqual(got, [heard])



class Service(unittest.TestCase):
    def test_kind(self):
        labels = ["Non-Music---Spoken Word", "Electronic---Techno"]
        self.assertEqual(listen.kind_of([], [0.8, 0.1], labels, 1.0), "speech")
        self.assertEqual(listen.kind_of([], [0.05, 0.9], labels, 3.0), "music")
        self.assertEqual(listen.kind_of([], [0.2, 0.3], labels, 1.0), "mixed")
        self.assertEqual(listen.kind_of(None, None, None, 3.5), "music")

    def test_yamnet_decides_what_is_music(self):
        """With YAMNet's shares (talking, music) the Discogs styles don't get a
        say in music or not: they called a cartoon's dialogue and effects
        "experimental" music."""
        labels = ["Non-Music---Story", "Electronic---Experimental"]
        experimental = [0.02, 0.22]                       # what the cartoon got from the styles
        k = lambda talk, tune: listen.kind_of([], experimental, labels, 4.6, (talk, tune))
        self.assertEqual(k(0.8, 0.0), "speech")           # a podcast
        self.assertEqual(k(0.7, 0.5), "mixed")            # a cartoon: dialogue over its score
        self.assertEqual(k(0.1, 0.95), "music")           # a song (singing isn't talk)
        self.assertEqual(k(0.3, 0.3), "mixed")            # a little of both
        self.assertEqual(k(0.0, 0.1), "speech")           # effects and crowd noise: not music
        self.assertEqual(listen.kind_of([], experimental, labels, 4.6), "music")   # no YAMNet: the styles, as before

    def test_heard_counts_the_frames(self):
        import numpy as np

        scores = np.zeros((4, 521), np.float32)
        scores[0, 0] = 0.9            # Speech
        scores[1, 3] = 0.6            # Narration, monologue
        scores[2, 132] = 0.8          # Music
        scores[3, 132] = 0.4          # unsure music: not counted

        class Session:
            def run(self, _out, feed):
                self.fed = next(iter(feed.values()))
                return [scores]

        s = Session()
        with mock.patch.object(listen, "_yamnet", (s, "waveform", [0, 1, 2, 3, 5], 132)):
            self.assertEqual(listen.heard(np.zeros(16000, np.float64)), (0.5, 0.25))
        self.assertEqual(s.fed.dtype, np.float32)
        with mock.patch.object(listen, "_yamnet", None):
            self.assertIsNone(listen.heard(np.zeros(16000)))

    def test_yamnet_loads_from_its_class_list(self):
        import tempfile

        d = tempfile.mkdtemp()
        try:
            self.assertIsNone(listen.load_yamnet(d))          # nothing there: off, no error
            with open(os.path.join(d, listen.YAMNET), "wb") as f:
                f.write(b"x")
            with open(os.path.join(d, listen.YAMNET_CLASSES), "w") as f:
                f.write('index,mid,display_name\n0,/m/09x0r,Speech\n1,/m/0ytgt,"Child speech, kid speaking"\n'
                        '2,/m/02qldy,"Narration, monologue"\n3,/m/04rlf,Music\n')
            fake = mock.MagicMock()
            fake.InferenceSession.return_value.get_inputs.return_value = [mock.Mock(name="in")]
            # only this one entry, not patch.dict(sys.modules): that puts the whole
            # table back and drops modules first imported meanwhile
            had = sys.modules.get("onnxruntime")
            sys.modules["onnxruntime"] = fake
            try:
                got = listen.load_yamnet(d)
            finally:
                if had is None:
                    sys.modules.pop("onnxruntime", None)
                else:
                    sys.modules["onnxruntime"] = had
            self.assertEqual((got[2], got[3]), ([0, 1, 2], 3))
        finally:
            listen._yamnet = None
            import shutil
            shutil.rmtree(d)

    def test_a_clip_led_by_a_non_music_style_isnt_music(self):
        """What Ryan's log showed: a narrated story video and a sports ad came
        back as music (120 and 146 BPM) with "story" and "radioplay" as their
        top styles. A top Non-Music style that still came back as music means
        it scored under the old fixed 0.3 bar. The numbers here are made up in
        that shape (the log didn't keep scores; it does now)."""
        labels = ["Non-Music---Story", "Non-Music---Radioplay", "Pop---Dance-pop", "Hip Hop---Trap"]
        self.assertEqual(listen.kind_of([], [0.24, 0.05, 0.12, 0.06], labels, 2.6), "speech")   # narration, a bed under it
        self.assertEqual(listen.kind_of([], [0.05, 0.18, 0.16, 0.04], labels, 3.1), "mixed")    # an ad: voice over music
        self.assertEqual(listen.kind_of([], [0.04, 0.03, 0.31, 0.10], labels, 3.2), "music")    # a song
        self.assertEqual(listen.kind_of([], [0.01, 0.0, 0.02, 0.0], labels, 1.0), "speech")     # no opinion: the beat

    def test_reads_wav_and_bass(self):
        import numpy as np

        t = np.arange(16000) / 16000
        buf = io.BytesIO()
        with wave.open(buf, "wb") as w:
            w.setnchannels(2); w.setsampwidth(2); w.setframerate(16000)
            s = (np.sin(2 * np.pi * 60 * t) * 0.5 * 32767).astype("<i2")
            w.writeframes(np.stack([s, s], axis=1).tobytes())
        x, rate = listen.read_wav(buf.getvalue())
        self.assertEqual((rate, len(x)), (16000, 16000))
        loud, bass = listen.color(x, rate)
        self.assertGreater(bass, 0.9)
        self.assertLess(loud, -5)


if __name__ == "__main__":
    unittest.main()


class Address(unittest.TestCase):
    """music.url is the service's address; one of its paths pasted in (as
    Ryan's was: .../health) sent every clip to .../health/listen, a 404."""

    def test_a_pasted_path_is_taken_off(self):
        for url in ("http://192.168.0.186:8795", "http://192.168.0.186:8795/", "http://192.168.0.186:8795/health",
                    "http://192.168.0.186:8795/listen/", " http://192.168.0.186:8795/HEALTH "):
            with mock.patch.object(music.config, "MUSIC_URL", url, create=True):
                self.assertEqual(music.service(), "http://192.168.0.186:8795", url)

    def test_clips_go_to_listen(self):
        seen = []
        class Reply(io.BytesIO):
            def __enter__(self): return self
            def __exit__(self, *a): return False
        def opened(req, timeout):
            seen.append(req.full_url)
            return Reply(b'{"kind": "music"}')
        with mock.patch.object(music.config, "MUSIC_URL", "http://h:8795/health", create=True), \
                mock.patch("urllib.request.urlopen", side_effect=opened):
            self.assertEqual(music.ask(b"wav"), {"kind": "music"})
        self.assertEqual(seen, ["http://h:8795/listen"])

    def test_a_404_says_what_to_set(self):
        import urllib.error
        err = urllib.error.HTTPError("http://h:9/x/listen", 404, "Not Found", {}, None)
        with mock.patch.object(music.config, "MUSIC_URL", "http://h:9/x", create=True), \
                mock.patch("urllib.request.urlopen", side_effect=err):
            with self.assertRaisesRegex(RuntimeError, "should be its address"):
                music.ask(b"wav")


class TheEventLeaves(unittest.TestCase):
    """The music event has its own "kind" field (music, speech, mixed): it
    collided with emit's first argument, a TypeError on every song."""

    def test_sent_with_its_kind(self):
        from web import livefeed
        seen = []
        with mock.patch.object(livefeed, "_line", side_effect=lambda ev: seen.append(ev) or "x"), \
                mock.patch.object(livefeed, "_subs", [object()]), mock.patch.object(livefeed, "_send_all", create=True):
            try:
                livefeed.emit("music", on=True, kind="music", bpm=128)
            except Exception:
                pass
        self.assertEqual((seen[0]["t"], seen[0]["kind"]), ("music", "music"))

    def test_send_doesnt_raise(self):
        s = music.summary(ANSWER, 1000.0)
        with mock.patch("web.livefeed.emit") as emit:
            music._send(s)
        self.assertEqual(emit.call_args.args, ("music",))
        self.assertEqual(emit.call_args.kwargs["kind"], "music")
