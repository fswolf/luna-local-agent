"""Live dictation: what you've said so far, while you're still saying it.

Whisper isn't a streaming recogniser: it reads finished audio. So the chat
page's mic (core/assistant.py dictation) is fed the recording as it comes
(voice/listen.py record_audio's on_audio), and about once a second the part
not read yet goes through Whisper again, quickly (one beam), and the words
so far go to the page as a draft. When you stop, the usual full
transcription replaces the draft: the words you send are as good as ever.

One pass at a time on its own thread: on a slow machine the draft just
updates less often, nothing piles up. Past WINDOW seconds a stretch is
settled (its words kept) and the next pass starts after it, so a long
dictation doesn't make every pass read it all from the start. Off with
stt.live_text false.
"""
import threading

import numpy as np

import config
from config import SAMPLE_RATE
from core import logbook

EVERY = 1.0          # seconds between passes (a pass that runs long just delays the next)
WINDOW = 20.0        # seconds of audio a pass reads at most; past it, that stretch is settled
SHORTEST = 0.5       # seconds: less than this isn't worth a pass


def on():
    return bool(getattr(config, "STT_LIVE_TEXT", True))


class Drafts:
    """feed(blocks) from the recording; on_text(words so far) from its thread."""

    def __init__(self, on_text, read=None):
        self._on_text = on_text
        self._read = read or _quick
        self._blocks = []
        self._lock = threading.Lock()
        self._stop = threading.Event()
        self._settled_at = 0          # samples already turned into settled words
        self._settled = ""
        self._last = ""
        self._round = 0               # bumped when the recording starts over: a pass from before is stale
        self._thread = threading.Thread(target=self._run, daemon=True, name="dictation-drafts")

    def start(self):
        self._thread.start()
        return self

    def feed(self, blocks):
        """More of the recording; None when it started over (the detector
        failed and the fallback records afresh), so the old part goes."""
        with self._lock:
            if blocks is None:
                self._blocks, self._settled_at, self._settled = [], 0, ""
                self._round += 1
                return
            self._blocks.extend(blocks)

    def close(self):
        """Stop drafting (before the final transcription: one Whisper at a time)."""
        self._stop.set()
        if self._thread.is_alive():
            self._thread.join(timeout=30)

    def _audio(self):
        """(the recording so far, where it settled, which round), together."""
        with self._lock:
            audio = np.concatenate(self._blocks) if self._blocks else np.zeros(0, dtype=np.float32)
            return audio, self._settled_at, self._round

    def _run(self):
        while not self._stop.wait(EVERY):
            try:
                self.step()
            except Exception:
                logbook.exception("stt", "a dictation draft failed")
                return          # the final transcription still comes; only the draft stops

    def step(self):
        """One pass: the words since the last settled stretch, sent if they changed."""
        audio, settled_at, round_ = self._audio()
        window = audio[settled_at:]
        if len(window) < SHORTEST * SAMPLE_RATE:
            return
        words = (self._read(window.astype(np.float32)) or "").strip()
        if self._stop.is_set():
            return          # stopped while reading: the full transcription has it now
        with self._lock:
            if round_ != self._round:
                return      # the recording started over while this was read
            if len(window) >= WINDOW * SAMPLE_RATE:
                self._settled = f"{self._settled} {words}".strip()
                self._settled_at = len(audio)
                words = ""
            draft = f"{self._settled} {words}".strip()
        if draft and draft != self._last:
            self._last = draft
            self._on_text(draft)


def _quick(audio):
    """A fast read of some audio, for a draft: one beam, no timestamps."""
    from voice import speech

    if speech.whisper is None:
        return ""
    segments, _info = speech.whisper.transcribe(
        audio, language=config.STT_LANGUAGE or None, beam_size=1, vad_filter=True,
        condition_on_previous_text=False, without_timestamps=True)
    text = "".join(s.text for s in segments).strip()
    return "" if speech.hallucination(text) else text
