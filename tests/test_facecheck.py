"""The face check (facecheck.py) and the camera hooks (camera.hooks),
without a camera: every way a look can fail, and that none of them
raises or holds a turn up past its budget.

    python -m unittest discover tests        (from the repo folder)
"""
import os
import sys
import threading
import time
import unittest
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from tests.offline import FAKE  # noqa: E402,F401  (first: no real servers)

import camera  # noqa: E402
import config  # noqa: E402
import facecheck  # noqa: E402
import people  # noqa: E402
import plugins  # noqa: E402
import presence  # noqa: E402


class FakeImage:
    shape = (480, 640, 3)

    def mean(self):
        return 100.0


class FakeFaces:
    """presence._Faces with its models loaded (or not)."""

    def __init__(self, found=True, loaded=True):
        self.yunet = object() if loaded else None
        self.sface = object() if loaded else None
        self.found = found

    def name(self):
        return "YuNet" if self.yunet else "waiting for the face model to download"

    def find(self, img):
        return [(10.0, 10.0, 100.0, 100.0, "row")] if self.found else []

    def print_of(self, img, row):
        return [0.1] * 128


SETTINGS = {"PEOPLE_FACE_CHECK": True, "PEOPLE_FACE_CHECK_MINUTES": 10,
            "PEOPLE_FACE_CHECK_SECONDS": 0.5, "PEOPLE_VOICE_MATCH": 0.3, "PRESENCE_MATCH": 0.36}


class Base(unittest.TestCase):
    def setUp(self):
        facecheck.reset()
        self.patches = [mock.patch.object(config, k, v, create=True) for k, v in SETTINGS.items()]
        self.patches += [
            mock.patch.object(camera, "_cv2", return_value=mock.MagicMock()),
            mock.patch.object(presence, "running", return_value=False),
            mock.patch.object(presence, "_faces_for", side_effect=lambda cv2: self.faces),
            mock.patch.object(people, "everyone", return_value={"Shannon": {"name": "Shannon", "face": [[0.1] * 128]}}),
            mock.patch.object(people, "verdict", return_value=("Shannon", 0.6)),
            mock.patch.object(facecheck, "_remote_or_job", return_value=False),
            mock.patch("facecheck.logbook"),
        ]
        for p in self.patches:
            p.start()
        self.faces = FakeFaces()
        self.frame = mock.patch.object(camera, "frame", return_value=(FakeImage(), "camera 0"))
        self.grab = self.frame.start()

    def tearDown(self):
        self.frame.stop()
        for p in reversed(self.patches):
            p.stop()
        facecheck.reset()


class Looks(Base):
    def test_off_never_opens_the_camera(self):
        with mock.patch.object(config, "PEOPLE_FACE_CHECK", False):
            self.assertIsNone(facecheck.check())
        self.grab.assert_not_called()

    def test_finds_the_face(self):
        self.assertEqual(facecheck.check(), "Shannon")

    def test_one_look_counts_for_a_while(self):
        facecheck.check()
        facecheck.check()
        self.assertEqual(self.grab.call_count, 1)

    def test_a_pause_in_the_conversation_means_a_new_look(self):
        facecheck.check()
        facecheck._state["turn_at"] -= facecheck.GAP + 1
        facecheck.check()
        self.assertEqual(self.grab.call_count, 2)

    def test_too_dark_is_an_answer_not_a_failure(self):
        dark = FakeImage()
        dark.mean = lambda: 2.0
        self.grab.return_value = (dark, "camera 0")
        self.assertIsNone(facecheck.check())
        self.assertEqual(facecheck._state["fails"], 0)
        self.assertIn("dark", facecheck._state["what"])

    def test_presence_watching_means_no_look(self):
        with mock.patch.object(presence, "running", return_value=True), \
                mock.patch.object(presence, "verdict", return_value="Shannon"):
            self.assertEqual(facecheck.check(), "Shannon")
        self.grab.assert_not_called()

    def test_not_on_a_remote_or_job_turn(self):
        with mock.patch.object(facecheck, "_remote_or_job", return_value=True):
            self.assertIsNone(facecheck.check())
        self.grab.assert_not_called()

    def test_nobody_in_view_is_an_answer_not_a_failure(self):
        self.faces = FakeFaces(found=False)
        self.assertIsNone(facecheck.check())
        self.assertEqual(facecheck._state["fails"], 0)
        self.assertEqual(facecheck._state["what"], "nobody in view")

    def test_unknown_face_is_nobody(self):
        with mock.patch.object(people, "verdict", return_value=(None, 0.1)):
            self.assertIsNone(facecheck.check())
        self.assertEqual(facecheck._state["fails"], 0)


class Failures(Base):
    def test_no_opencv(self):
        with mock.patch.object(camera, "_cv2", return_value=None):
            self.assertIsNone(facecheck.check())
        self.grab.assert_not_called()

    def test_nobody_has_face_prints(self):
        with mock.patch.object(people, "everyone", return_value={"Ryan": {"name": "Ryan", "voice": [[1]]}}):
            self.assertIsNone(facecheck.check())
        self.grab.assert_not_called()

    def test_models_still_loading_is_not_a_failure(self):
        self.faces = FakeFaces(loaded=False)
        self.assertIsNone(facecheck.check())
        self.assertEqual(facecheck._state["fails"], 0)

    def test_camera_error_backs_off_then_pauses(self):
        self.grab.return_value = (None, "couldn't open camera 0")
        for _ in range(facecheck.FAILS_TO_PAUSE):
            facecheck._state["retry_at"] = 0.0          # skip the minute's wait
            self.assertIsNone(facecheck.check())
        self.assertTrue(facecheck._state["paused"])
        self.assertIn("paused", facecheck.why_not())
        calls = self.grab.call_count
        facecheck._state["retry_at"] = 0.0
        self.assertIsNone(facecheck.check())             # paused: no look
        self.assertEqual(self.grab.call_count, calls)
        self.grab.return_value = (FakeImage(), "camera 0")
        self.assertEqual(facecheck.check(force=True), "Shannon")   # /people check
        self.assertFalse(facecheck._state["paused"])

    def test_a_failed_look_waits_before_the_next(self):
        self.grab.return_value = (None, "busy")
        facecheck.check()
        facecheck.check()
        self.assertEqual(self.grab.call_count, 1)

    def test_a_hanging_camera_costs_only_the_budget(self):
        release = threading.Event()
        self.grab.side_effect = lambda **kw: (release.wait(5), (FakeImage(), "late"))[1]
        began = time.monotonic()
        self.assertIsNone(facecheck.check())
        self.assertLess(time.monotonic() - began, 1.5)
        facecheck._state["retry_at"] = 0.0
        self.assertIsNone(facecheck.check())             # still busy: no second look on top
        self.assertEqual(self.grab.call_count, 1)
        release.set()

    def test_a_crash_in_the_look_is_caught(self):
        self.grab.side_effect = RuntimeError("driver exploded")
        self.assertIsNone(facecheck.check())
        self.assertEqual(facecheck._state["fails"], 1)

    def test_a_bug_in_check_is_caught(self):
        with mock.patch.object(facecheck, "_check", side_effect=KeyError("oops")):
            self.assertIsNone(facecheck.check())

    def test_bad_settings_fall_back(self):
        with mock.patch.object(config, "PEOPLE_FACE_CHECK_SECONDS", "soon"), \
                mock.patch.object(config, "PEOPLE_FACE_CHECK_MINUTES", None):
            self.assertEqual(facecheck.check(), "Shannon")

    def test_status_never_raises(self):
        self.assertIn("no look yet", facecheck.status())
        facecheck.check()
        self.assertIn("Shannon", facecheck.status())


class SecondPass(Base):
    def test_a_look_under_way_is_shared_not_repeated(self):
        go = threading.Event()
        self.grab.side_effect = lambda **kw: (go.wait(2), (FakeImage(), "camera 0"))[1]
        with mock.patch.object(config, "PEOPLE_FACE_CHECK_SECONDS", 2):
            first = []
            t = threading.Thread(target=lambda: first.append(facecheck.check("voice")))
            t.start()
            time.sleep(0.1)
            threading.Timer(0.2, go.set).start()
            self.assertEqual(facecheck.check("typed"), "Shannon")
            t.join()
        self.assertEqual(first, ["Shannon"])
        self.assertEqual(self.grab.call_count, 1)

    def test_a_stuck_look_doesnt_slow_later_turns(self):
        release = threading.Event()
        self.grab.side_effect = lambda **kw: (release.wait(5), (FakeImage(), "late"))[1]
        facecheck.check()
        facecheck._state["retry_at"] = 0.0
        began = time.monotonic()
        self.assertIsNone(facecheck.check())
        self.assertLess(time.monotonic() - began, 0.2)
        release.set()

    def test_models_that_never_load_become_a_failure(self):
        self.faces = FakeFaces(loaded=False)
        facecheck.check()
        self.assertEqual(facecheck._state["fails"], 0)
        facecheck._state["loading_since"] -= facecheck.LOADING_GIVE_UP + 1
        facecheck._state["retry_at"] = 0.0
        facecheck.check()
        self.assertEqual(facecheck._state["fails"], 1)
        self.assertIn("didn't load", facecheck._state["last_error"])

    def test_not_looking_doesnt_reread_the_folder_every_turn(self):
        with mock.patch.object(people, "everyone", return_value={}) as folder:
            facecheck.check()
            facecheck.check()
        self.assertEqual(folder.call_count, 1)

    def test_asks_the_camera_for_a_small_picture(self):
        facecheck.check()
        self.assertEqual(self.grab.call_args.kwargs.get("width"), presence.WIDTH)

    def test_unsure_voice_starts_the_look_during_transcription(self):
        import assistant
        import voices

        with mock.patch.object(voices, "identify", return_value=(None, 0.25)), \
                mock.patch.object(voices, "enrolling", return_value=None):
            heard = {}
            assistant._whose_voice("x.wav", heard)              # a station: no look
            self.grab.assert_not_called()
            assistant._whose_voice("x.wav", heard, True)        # the desk: looks now
        self.assertEqual(self.grab.call_count, 1)
        with mock.patch.object(config, "USER_NAME", "Ryan", create=True):
            self.assertEqual(people.decide(None, True, voice_score=0.25), "Shannon")
        self.assertEqual(self.grab.call_count, 1)             # the answer was ready


class Deciding(Base):
    def test_typed_turn_with_someone_else(self):
        with mock.patch.object(config, "USER_NAME", "Ryan", create=True):
            self.assertEqual(people.typed_speaker(), "Shannon")

    def test_typed_turn_is_yours_with_it_off(self):
        with mock.patch.object(config, "PEOPLE_FACE_CHECK", False):
            self.assertIsNone(people.typed_speaker())
        self.grab.assert_not_called()

    def test_typed_turn_owner_is_none(self):
        with mock.patch.object(people, "verdict", return_value=("Ryan", 0.7)), \
                mock.patch.object(config, "USER_NAME", "Ryan", create=True):
            self.assertIsNone(people.typed_speaker())

    def test_unsure_voice_gets_a_look(self):
        with mock.patch.object(config, "USER_NAME", "Ryan", create=True):
            self.assertEqual(people.decide(None, True, voice_score=0.25, at_desk=True), "Shannon")

    def test_clear_miss_is_still_the_owner(self):
        self.assertIsNone(people.decide(None, True, voice_score=0.05, at_desk=True))
        self.grab.assert_not_called()

    def test_unsure_voice_away_from_the_desk_gets_no_look(self):
        self.assertIsNone(people.decide(None, True, voice_score=0.25, at_desk=False))
        self.grab.assert_not_called()

    def test_a_station_in_another_room_never_uses_the_desk_face(self):
        with mock.patch.object(presence, "verdict", return_value="Shannon"):
            self.assertIsNone(people.decide(None, False, at_desk=False))
            self.assertIsNone(people.decide(None, True, voice_score=0.25, at_desk=False))
        self.grab.assert_not_called()

    def test_recognised_voice_wins(self):
        with mock.patch.object(config, "USER_NAME", "Ryan", create=True):
            self.assertEqual(people.decide("Mia", True, voice_score=0.8, at_desk=True), "Mia")
        self.grab.assert_not_called()

    def test_grey_zone(self):
        self.assertTrue(facecheck.unsure(0.2))
        self.assertTrue(facecheck.unsure(0.29))
        self.assertFalse(facecheck.unsure(0.3))
        self.assertFalse(facecheck.unsure(0.19))
        self.assertFalse(facecheck.unsure(None))


class Hooks(unittest.TestCase):
    def setUp(self):
        self.log = mock.patch("camera.logbook").start()
        self.addCleanup(mock.patch.stopall)

    def test_command_not_installed(self):
        with mock.patch.object(config, "CAMERA_BEFORE", "no-such-program-xyz {device}", create=True):
            camera._run_command("before", 0)
        self.assertTrue(self.log.warn.called)

    def test_command_fails(self):
        with mock.patch.object(config, "CAMERA_AFTER", "false", create=True):
            camera._run_command("after", 0)
        self.assertTrue(self.log.warn.called)

    def test_unreadable_command(self):
        with mock.patch.object(config, "CAMERA_BEFORE", 'echo "unclosed', create=True):
            camera._run_command("before", 0)
        self.assertTrue(self.log.warn.called)

    def test_device_goes_into_the_command(self):
        with mock.patch.object(config, "CAMERA_BEFORE", "tool -d {device}", create=True), \
                mock.patch("camera.subprocess.run") as run:
            run.return_value = mock.Mock(returncode=0)
            camera._run_command("before", "/dev/video2")
        self.assertEqual(run.call_args[0][0], ["tool", "-d", "/dev/video2"])

    def test_a_hanging_hook_is_left_behind(self):
        began = time.monotonic()
        camera._bounded(lambda: time.sleep(3), 0.2, "slow hook")
        self.assertLess(time.monotonic() - began, 1.0)

    def test_after_runs_when_the_camera_fails(self):
        seen = []
        with mock.patch.object(camera, "hooks", side_effect=lambda which, d: seen.append(which)), \
                mock.patch.object(camera, "_open", side_effect=OSError("busy")):
            img, why = camera._read_local(mock.MagicMock(), 0, 640, 0)
        self.assertIsNone(img)
        self.assertIn("busy", why)
        self.assertEqual(seen, ["open", "close"])

    def test_frame_never_raises(self):
        with mock.patch.object(camera, "_cv2", side_effect=RuntimeError("weird")):
            img, why = camera.frame()
        self.assertIsNone(img)
        self.assertIn("weird", why)

    def test_a_raising_plugin_hook_is_logged(self):
        broken = mock.Mock()
        broken.name = "broken"
        broken._on_camera_open = mock.Mock(side_effect=RuntimeError("nope"))
        broken.running.return_value = True
        with mock.patch.dict(plugins._loaded, {"broken": broken}, clear=True), \
                mock.patch("plugins.logbook") as log:
            plugins.camera_open(0)
        self.assertTrue(log.exception.called)

    def test_no_command_no_thread(self):
        with mock.patch.object(config, "CAMERA_BEFORE", "", create=True), \
                mock.patch.object(camera, "_run_command") as run:
            camera.hooks("open", 0)
        run.assert_not_called()

    def test_hooks_never_raise(self):
        with mock.patch.object(camera, "_bounded", side_effect=RuntimeError("no threads")):
            camera.hooks("open", 0)


if __name__ == "__main__":
    unittest.main()
