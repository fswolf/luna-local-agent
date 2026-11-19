"""Luna's ears for music: a small service that listens to a clip and says
what it is. Runs on her server (or the same machine), beside llama.cpp.

    POST /listen   a WAV clip (16-bit PCM, any rate, mono or stereo), ~10 s
                   -> {"kind": "music"|"speech"|"mixed", "styles": [[name, score], ...],
                       "bpm": 128.0, "beats": [0.41, 0.88, ...], "beat_conf": 3.1,
                       "loud": -14.2, "bass": 0.38, "secs": 10.0, "model": true}
    GET  /health   -> {"ok": true, "model": true|false}

The style model is MTG's Discogs-EffNet (400 Discogs styles, among them a
"Non-Music" family: spoken word, interviews...), run with onnxruntime. Its
input is the mel bands Essentia's TensorflowInputMusiCNN makes, so the
numbers match what it was trained on. Without the model file it still
answers tempo, loudness and bass, and guesses music from the beat.
The model is CC BY-NC-SA 4.0 (MTG): fine for personal and open-source use,
not for selling; it's downloaded by install.sh (to ~/.local/share/luna-listen/models), never
shipped with Luna.

    python3 listen.py [--host 0.0.0.0] [--port 8795] [--models DIR]
"""
import argparse
import io
import json
import os
import sys
import time
import wave
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
# install.sh keeps its venv and the model here, outside the repo
HOME = os.environ.get("LISTEN_HOME", os.path.join(os.path.expanduser("~"), ".local", "share", "luna-listen"))
MODELS = os.path.join(HOME, "models")
MODEL = "discogs-effnet-bsdynamic-1.onnx"
LABELS = "genre_discogs400-discogs-effnet-1.json"
MAX_BODY = 8 * 1024 * 1024        # ~45 s of 44.1 kHz stereo; a clip is far less
MAX_SECS = 30                     # only the first 30 s are listened to
TOP = 5                           # styles sent back

_es = None                        # essentia.standard, loaded once
_model = None                     # (session, input name, transpose, output index, labels) or None


def _essentia():
    global _es
    if _es is None:
        import essentia
        essentia.log.infoActive = False
        import essentia.standard as es
        _es = es
    return _es


def load_model(folder):
    """The style model, or None when it isn't there (or onnxruntime isn't)."""
    global _model
    path, lpath = os.path.join(folder, MODEL), os.path.join(folder, LABELS)
    if not (os.path.isfile(path) and os.path.isfile(lpath)):
        _model = None
        return None
    import onnxruntime as ort
    s = ort.InferenceSession(path, providers=["CPUExecutionProvider"])
    inp = s.get_inputs()[0]
    # [batch, 128 frames, 96 bands] is what Essentia feeds it; turn ours round if it wants the other way
    transpose = len(inp.shape) == 3 and inp.shape[-1] == 128
    outs = [o.shape[-1] for o in s.get_outputs()]
    out = outs.index(400) if 400 in outs else 0
    with open(lpath, encoding="utf-8") as f:
        labels = json.load(f)["classes"]
    _model = (s, inp.name, transpose, out, labels)
    return _model


def read_wav(data):
    """WAV bytes -> (mono float32 samples, rate)."""
    with wave.open(io.BytesIO(data)) as w:
        if w.getsampwidth() != 2:
            raise ValueError("16-bit PCM only")
        rate, ch = w.getframerate(), w.getnchannels()
        x = np.frombuffer(w.readframes(min(w.getnframes(), rate * MAX_SECS)), dtype="<i2").astype(np.float32) / 32768
    if ch > 1:
        x = x.reshape(-1, ch).mean(axis=1)
    return np.ascontiguousarray(x, dtype=np.float32), rate


def resample(x, rate, to):
    if rate == to:
        return x
    return _essentia().Resample(inputSampleRate=rate, outputSampleRate=to, quality=1)(x)


def styles(x16):
    """[[style, score], ...] best first, from 16 kHz audio; None with no model."""
    if _model is None:
        return None
    es = _essentia()
    s, name, transpose, out, labels = _model
    mel = es.TensorflowInputMusiCNN()
    frames = np.array([mel(f) for f in es.FrameGenerator(x16, frameSize=512, hopSize=256, startFromZero=True)], dtype=np.float32)
    if len(frames) < 128:                                         # short clip: pad to one patch
        frames = np.vstack([frames, np.zeros((128 - len(frames), 96), np.float32)]) if len(frames) else np.zeros((128, 96), np.float32)
    patches = np.stack([frames[i:i + 128] for i in range(0, len(frames) - 127, 62)])
    if transpose:
        patches = patches.transpose(0, 2, 1)
    act = s.run(None, {name: patches})[out].mean(axis=0)
    order = np.argsort(act)[::-1][:TOP]
    return [[labels[i], round(float(act[i]), 3)] for i in order], act, labels


def rhythm(x44):
    """(bpm, beat times in seconds, confidence 0..5.3) from 44.1 kHz audio."""
    bpm, beats, conf, _, _ = _essentia().RhythmExtractor2013(method="multifeature")(x44)
    return float(bpm), [round(float(b), 3) for b in beats], float(conf)


def color(x, rate):
    """(loudness in dBFS, share of the spectrum's energy below 150 Hz)."""
    rms = float(np.sqrt(np.mean(x ** 2))) if len(x) else 0.0
    loud = 20 * np.log10(max(rms, 1e-6))
    n = 1 << int(np.log2(min(len(x), rate * 4)) if len(x) > 1024 else 10)
    spec = np.abs(np.fft.rfft(x[:n] * np.hanning(n))) ** 2 if len(x) >= n else np.zeros(1)
    f = np.fft.rfftfreq(n, 1 / rate) if len(x) >= n else np.zeros(1)
    total = float(spec.sum()) or 1.0
    return round(loud, 1), round(float(spec[f < 150].sum()) / total, 3)


def kind_of(found, act, labels, conf):
    """music, speech or mixed: the Non-Music styles against the rest, else the beat."""
    if found is None:
        return "music" if conf >= 3.0 else "speech" if conf < 1.5 else "mixed"     # rough: the beat alone
    talk = max((a for a, l in zip(act, labels) if l.startswith("Non-Music")), default=0.0)
    tune = max((a for a, l in zip(act, labels) if not l.startswith("Non-Music")), default=0.0)
    if talk >= 0.3 and talk > tune:
        return "speech"
    if talk >= 0.15 and conf < 2.0:
        return "mixed"
    return "music"


def listen(data):
    x, rate = read_wav(data)
    if len(x) < rate:
        raise ValueError("under a second of sound")
    x16, x44 = resample(x, rate, 16000), resample(x, rate, 44100)
    got = styles(x16)
    found, act, labels = got if got else (None, None, None)
    bpm, beats, conf = rhythm(x44)
    loud, bass = color(x, rate)
    return {"kind": kind_of(found, act, labels, conf), "styles": found, "bpm": round(bpm, 1), "beats": beats,
            "beat_conf": round(conf, 2), "loud": loud, "bass": bass, "secs": round(len(x) / rate, 2),
            "model": _model is not None}


class Handler(BaseHTTPRequestHandler):
    server_version = "luna-listen/1"

    def _send(self, code, obj):
        body = json.dumps(obj).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        if self.path.split("?")[0] == "/health":
            return self._send(200, {"ok": True, "model": _model is not None})
        self._send(404, {"error": "not here"})

    def do_POST(self):
        if self.path.split("?")[0] != "/listen":
            return self._send(404, {"error": "not here"})
        try:
            n = int(self.headers.get("Content-Length") or 0)
        except ValueError:
            n = 0
        if not 0 < n <= MAX_BODY:
            return self._send(413, {"error": f"send a WAV clip under {MAX_BODY // 1048576} MB"})
        t = time.monotonic()
        try:
            out = listen(self.rfile.read(n))
        except (ValueError, wave.Error, EOFError) as e:
            return self._send(400, {"error": str(e) or "that isn't a WAV clip"})
        out["took"] = round(time.monotonic() - t, 2)
        self._send(200, out)

    def log_message(self, fmt, *args):
        if not getattr(self.server, "quiet", False):
            sys.stderr.write("%s %s\n" % (self.address_string(), fmt % args))


def main(argv=None):
    p = argparse.ArgumentParser(description="Luna's music listener")
    p.add_argument("--host", default=os.environ.get("LISTEN_HOST", "0.0.0.0"))
    p.add_argument("--port", type=int, default=int(os.environ.get("LISTEN_PORT", 8795)))
    p.add_argument("--models", default=os.environ.get("LISTEN_MODELS", MODELS))
    a = p.parse_args(argv)
    _essentia()
    have = load_model(a.models) is not None
    print(f"listening on {a.host}:{a.port}; style model: {'yes' if have else 'not found in ' + a.models + ' (tempo only)'}", flush=True)
    ThreadingHTTPServer((a.host, a.port), Handler).serve_forever()


if __name__ == "__main__":
    main()
