"""Talking to the model server: one completion, streamed, with thinking, tool-call markup and sentence splitting for the voice.

Part of the llm package (it was one llm.py); see llm/__init__.py.
"""

import json
import math
import re

import requests

import config
from config import LM_URL, LLM_HEADERS
from life import gestures
from core import interrupts
from web import livefeed
from core import lmstudio
from core import logbook

def _chat_completion(payload, narrator=None):
    """POST to LM_URL and return the reply *message* (not just its text,
    because a tool-calling reply carries tool_calls and no content).

    With a narrator, the reply is streamed and fed to it token by
    token; without one this is the plain blocking request it always
    was. Both return the same message shape.

    Raises a RuntimeError with LM Studio's actual error message when
    the response doesn't have "choices" - e.g. context length
    exceeded, a bad/unsupported param, model not loaded, etc. Without
    this, a malformed response just raises a bare KeyError('choices')
    with no indication of what actually went wrong.
    """
    if narrator is not None:
        return _streamed_message(payload, narrator)

    try:
        response = requests.post(LM_URL, headers=LLM_HEADERS, json=payload)
    except requests.exceptions.RequestException as e:
        lmstudio.mark_failed(e)
        logbook.error("llm", "request failed: %s", e)

        raise RuntimeError(f"LM Studio unreachable at {LM_URL}: {e}") from e

    try:
        data = response.json()
    except ValueError:
        raise RuntimeError(
            f"LM Studio returned a non-JSON response (HTTP {response.status_code}): "
            f"{response.text[:300]}"
        )

    if "choices" not in data:
        detail = data.get("error", data)
        logbook.error("llm", "response had no choices: %s", str(detail)[:500])
        raise RuntimeError(f"{config.llm_backend_label()} error: {detail}")

    lmstudio.mark_worked()

    message = data["choices"][0]["message"]
    _note_thinking(message.get("content") if isinstance(message.get("content"), str)
                   else "", _reasoning_field(message))

    return message


# What the last completion actually contained, so an empty reply can be
# explained instead of apologised for.
_last_raw = {"deltas": 0, "content": 0, "reasoning": 0, "tool_rounds": 0,
             "called": set(), "exchanges": [],
             # The scratchpad, one entry per model run this turn:
             # {"text": ..., "called": [tool names it went on to call]}.
             # Reset by ask(), appended by _note_thinking, read by
             # _record_thoughts. Per run rather than one buffer because
             # a tool turn thinks twice, and the first time - deciding
             # to call something - is the one worth reading.
             "thinking": [],
             # Per model run, the tokens llama-server reported with their
             # probabilities - see _note_tokens. Empty on LM Studio.
             "tokens": []}

_THINK_BLOCK = re.compile(r"<think>.*?</think>", re.IGNORECASE | re.DOTALL)

# A tool call the model wrote out as text instead of sending properly -
# Qwen's XML form (<function=name><parameter=x>...</parameter></function>,
# usually inside <tool_call>) or the JSON one inside <tool_call> tags.
# Never shown or spoken; _calls_from_text turns it into a real call.
_CALL_BLOCK = re.compile(r"<tool_call>.*?</tool_call>|<function=[^>]*>.*?</function>",
                         re.IGNORECASE | re.DOTALL)
_CALL_OPEN = re.compile(r"<tool_call>|<function=", re.IGNORECASE)
_THINK_INNER = re.compile(r"<think>(.*?)</think>", re.IGNORECASE | re.DOTALL)
_THINK_OPEN = re.compile(r"<think>", re.IGNORECASE)
_THINK_CLOSE = re.compile(r"</think>", re.IGNORECASE)


def _stray_close(text):
    """(reasoning, reply) when the text has a </think> with no <think>
    before it, else (None, text). Complete blocks already removed.

    The server's reasoning parser only catches thinking that opens with
    <think>. A model sometimes reasons without the opening tag - after a
    tool result, mostly - and closes it anyway: everything before that
    </think> was its scratchpad, not her reply."""
    opened = _THINK_OPEN.search(text)
    closes = [m for m in _THINK_CLOSE.finditer(text) if not opened or m.start() < opened.start()]

    if not closes:
        return None, text

    last = closes[-1]
    return text[:last.start()], text[last.end():]


def _note_tokens(tokens, delta):
    """One streamed chunk's tokens, as [text, part, logprob, alternatives].

    part is which stream the token went to: "t" thinking, "a" the
    answer, "c" a tool call. The delta it rode in on says which. A token
    that produced no delta of its own - the <think> tag, half of a tool
    call's syntax - arrives with no probabilities at all, so there is
    nothing to drop. Alternatives are kept only when the model wasn't
    sure (p < 0.9): the near-misses are the point, and a confident
    token's runners-up are noise that would triple the size.
    """
    if _reasoning_field(delta):
        part = "t"
    elif delta.get("content"):
        part = "a"
    elif delta.get("tool_calls"):
        part = "c"
    else:
        part = "o"

    for entry in (delta["_logprobs"] or {}).get("content") or []:
        try:
            text = str(entry.get("token", ""))
            lp = float(entry.get("logprob"))
        except (TypeError, ValueError):
            continue

        alts = []

        if lp < -0.105:  # p < 0.9
            alts = [[str(a.get("token", "")), round(float(a.get("logprob")), 3)]
                    for a in entry.get("top_logprobs") or []
                    if a.get("token") != text and a.get("logprob") is not None][:2]

        tokens.append([text, part, round(lp, 3), alts])


def _reasoning_field(part):
    """The scratchpad field of a delta or a message, whatever the server
    calls it: reasoning_content (LM Studio, llama.cpp, DeepSeek),
    reasoning (some proxies), thinking (Ollama)."""
    for key in ("reasoning_content", "reasoning", "thinking"):
        value = part.get(key)

        if isinstance(value, str) and value:
            return value

    return ""


def _note_thinking(content, reasoning_field=""):
    """Keep this run's scratchpad for the thought log.

    Two places it can be: inside <think> tags in the content, or in a
    separate reasoning_content field (LM Studio with reasoning parsing
    on, and most other servers). Both are taken. An unclosed <think> -
    the model hit max_tokens mid-thought - is kept too and marked,
    since "ran out of room while thinking" is exactly what you want to
    see when a reply came back empty.
    """
    content = content or ""
    parts = [m.strip() for m in _THINK_INNER.findall(content) if m.strip()]

    rest = _THINK_BLOCK.sub("", content)
    stray, rest = _stray_close(rest)

    if stray and stray.strip():
        parts.append(stray.strip())

    opened = _THINK_OPEN.split(rest, maxsplit=1)

    if len(opened) > 1 and opened[1].strip():
        # Two ways a think block ends without closing, and they call for
        # opposite fixes: HOME means nothing is wrong; max_tokens means
        # generation.reasoning or max_tokens wants raising.
        why = ("you pressed HOME" if interrupts.current().generating.is_set()
               else "the model ran out of tokens")
        parts.append(f"{opened[1].strip()}\n\n[cut off - {why} before the "
                     "think block closed]")

    if reasoning_field and reasoning_field.strip():
        parts.append(reasoning_field.strip())

    if parts:
        _last_raw["thinking"].append({"text": "\n\n".join(parts), "called": []})

# A sentence ends at .!?… plus any closing quote or bracket, followed by
# whitespace. Requiring the whitespace is what stops "3.5" and "e.g."
# being spoken as two sentences.
_SENTENCE_END = re.compile(r"[.!?…]['\"\u201d\u2019)\]]*\s")

# A timestamp prefix at the very start of a reply, which is the model
# copying the format of its own input back at us. Matched here rather
# than reusing _strip_leading_timestamps() because that one ends in
# .strip(), and a partial prefix with a trailing space then looks like a
# successful match - which settles the question a character too early
# and lets the rest of the timestamp through.
_LEADING_STAMP = re.compile(
    r"^\s*(?:"
    r"\[\d{4}-\d{2}-\d{2}[T ]\d{2}:\d{2}:\d{2}\]\s*"
    r"|\[(?:today|tomorrow|yesterday|last \w+|\w{3} \d)[^\]]{0,48}\]\s*"
    r")+",
    re.IGNORECASE,
)

# The shortest fragment worth sending to the TTS server on its own.
# Below this it's an interjection, and the pause around it sounds worse
# than waiting for the rest of the line - so it rides along with the
# sentence after it instead.
MIN_SPOKEN_CHARS = 16

# Words that end in a full stop without ending a sentence. Any single
# letter counts too, which is what catches "e.g.", "i.e.", "a.m." and
# "U.S." without having to list them.
_ABBREVIATIONS = {
    "mr", "mrs", "ms", "dr", "prof", "sr", "jr", "st", "vs", "etc",
    "approx", "est", "fig", "dept", "inc", "ltd", "no", "pp", "al",
}


def _ends_sentence(text, stop):
    """Is the terminator at `stop` a real sentence ending?

    Only full stops are ever in doubt - nothing abbreviates with ? or !
    """
    if text[stop] != ".":
        return True

    word = re.search(r"([A-Za-z]+)$", text[:stop])

    if not word:
        return True

    word = word.group(1)

    return len(word) > 1 and word.lower() not in _ABBREVIATIONS


def _visible(raw):
    """The part of a partially-streamed reply that is safe to show and
    to speak.

    Reasoning models open with <think>, and none of that should ever
    reach the speaker. Complete blocks are cut; an unclosed one means
    everything after it is still scratch work, so it's withheld until
    the closing tag arrives. A trailing "<thi" is held back too, since
    the next token may finish the tag.
    """
    text = _THINK_BLOCK.sub("", raw)
    text = _stray_close(text)[1]       # reasoning that never opened with <think>

    if "<think>" in text.lower():
        text = re.split(r"<think>", text, maxsplit=1, flags=re.IGNORECASE)[0]

    # Same for a tool call written out as text: cut whole ones, and hold
    # everything after one that hasn't closed yet.
    text = _CALL_BLOCK.sub("", text)
    opened = _CALL_OPEN.search(text)
    if opened:
        text = text[:opened.start()]

    # A gesture tag ([hug]) goes to the portrait, not the screen or the voice.
    text = gestures.strip(text)

    return re.sub(r"<[a-z_/=]{0,12}$", "", text, flags=re.IGNORECASE)


def _calls_from_text(raw, payload):
    """Tool calls the model wrote into its reply as text, as proper
    tool_calls entries - so they run instead of being printed. Values
    are converted to the type the tool's schema asks for (numbers,
    true/false); everything else stays a string. [] if there are none."""
    raw = _THINK_BLOCK.sub("", raw or "")
    schemas = {(t.get("function") or {}).get("name"): (t.get("function") or {}).get("parameters") or {}
               for t in payload.get("tools") or ()}
    calls = []

    def typed(name, key, value):
        kind = ((schemas.get(name) or {}).get("properties") or {}).get(key, {}).get("type")
        if kind in ("integer", "number", "boolean", "array", "object"):
            try:
                return json.loads(value)
            except ValueError:
                pass
        return value

    for match in re.finditer(r"<function=([^>\s]+)\s*>(.*?)</function>", raw, re.IGNORECASE | re.DOTALL):
        name, body = match.group(1).strip(), match.group(2)
        args = {k.strip(): typed(name, k.strip(), v.strip())
                for k, v in re.findall(r"<parameter=([^>]+)>(.*?)</parameter>", body, re.IGNORECASE | re.DOTALL)}
        calls.append((name, args))

    if not calls:
        for block in re.findall(r"<tool_call>(.*?)</tool_call>", raw, re.IGNORECASE | re.DOTALL):
            try:
                data = json.loads(block.strip())
            except ValueError:
                continue
            if isinstance(data, dict) and data.get("name"):
                args = data.get("arguments") or data.get("parameters") or {}
                calls.append((str(data["name"]), args if isinstance(args, dict) else {}))

    return [{"id": f"text_call_{i}", "type": "function",
             "function": {"name": name, "arguments": json.dumps(args)}}
            for i, (name, args) in enumerate(calls)]


class _Narrator:
    """Turns a token stream into two things at once: visible text for
    the screen, and complete sentences for the voice.

    The voice is why this exists. Waiting for the whole reply before
    synthesizing anything meant several seconds of silence on every
    turn; handing Kokoro each sentence as it finishes drops that to
    roughly one sentence's worth.
    """

    # The longest a leading "[" is given to turn out to be a timestamp
    # before it's treated as ordinary text.
    PREFIX_LOOKAHEAD = 80

    def __init__(self, on_text=None, on_sentence=None):
        self._on_text = on_text
        self._on_sentence = on_sentence
        self.raw = ""
        self._shown = 0
        self._spoken = 0
        self._prefix_len = None
        self._strays = 0

    def _presentable(self, final=False):
        """Visible text, minus a timestamp the model copied off its input.

        Stripping this at the end of the turn isn't enough. The screen
        gets the corrected version, but the speaker was handed the first
        sentence the moment it finished - timestamp and all - so you'd
        watch it flash and vanish while still hearing it read aloud.

        Nothing is emitted until the opening bracket has resolved one
        way or the other, so the prefix stays negotiable right up until
        the first character goes out. After that the offset is frozen,
        because feed() tracks positions against it.
        """
        text = _visible(self.raw)

        if self._prefix_len is not None and (self._shown or self._spoken):
            return text[self._prefix_len:]

        match = _LEADING_STAMP.match(text)
        prefix = match.end() if match else 0
        rest = text[prefix:]
        pending = rest.lstrip()

        # Mid-bracket. Hold rather than speak half a timestamp - but
        # never at the end of the turn, where holding would silently
        # swallow the whole reply.
        if (not final and pending.startswith("[") and "]" not in pending
                and len(text) < self.PREFIX_LOOKAHEAD):
            return ""

        self._prefix_len = prefix + (len(rest) - len(pending))

        return text[self._prefix_len:]

    def feed(self, piece):
        if not piece:
            return

        self.raw += piece

        # A </think> with no <think>: what came before was her reasoning,
        # and the visible text starts again after it. What was already
        # shown is put right by the final replace_message; what was
        # already spoken can't be taken back, but nothing more of it is.
        strays = len(_THINK_CLOSE.findall(_THINK_BLOCK.sub("", self.raw)))
        if strays != self._strays:
            self._strays = strays
            self._shown = self._spoken = 0
            self._prefix_len = None

        if "]" in piece or ")" in piece or "*" in piece:      # a tag, or a described move, just closed
            answer = _THINK_BLOCK.sub("", self.raw)
            gestures.from_tags(re.split(r"<think>", answer, maxsplit=1, flags=re.IGNORECASE)[0])

        text = self._presentable()

        if self._on_text and len(text) > self._shown:
            self._on_text(text[self._shown:])
            self._shown = len(text)

        if not self._on_sentence:
            return

        cursor = self._spoken

        while True:
            match = _SENTENCE_END.search(text, cursor)

            if not match:
                break

            # Keep looking past a false ending ("e.g.") and past a
            # fragment too short to be worth speaking on its own
            # ("Hey there.") - both should join the sentence after them.
            if (not _ends_sentence(text, match.start())
                    or match.end() - self._spoken < MIN_SPOKEN_CHARS):
                cursor = match.end()
                continue

            sentence = text[self._spoken:match.end()].strip()
            self._spoken = cursor = match.end()

            if sentence:
                self._on_sentence(sentence)

    def finish(self):
        """Flush whatever didn't end in punctuation."""
        text = self._presentable(final=True)

        if self._on_text and len(text) > self._shown:
            self._on_text(text[self._shown:])
            self._shown = len(text)

        if self._on_sentence:
            tail = text[self._spoken:].strip()
            self._spoken = len(text)

            if tail:
                self._on_sentence(tail)

        return text.strip()


def _explain_refusal(status, body, payload):
    """Turn LM Studio's error into a sentence about what to do.

    A bare HTML "Internal Server Error" page is what its web server
    sends when the request handler itself fell over - which, in
    practice, means one of two things: the prompt no longer fits the
    context the model was loaded with, or the model process died. Both
    look identical from here, and both used to arrive as nine lines of
    HTML in the conversation.
    """
    if "<html" in body.lower():
        detail = "internal error, no details given"
    else:
        detail = body[:300].strip() or "no details given"

    sent = lmstudio.estimate_tokens(payload)
    window = lmstudio.context_length()
    llama = getattr(config, "LLM_BACKEND", "") == "llama"
    name = config.llm_backend_label()
    raise_ctx = "raise CTX in llama/server.env" if llama else "raise the context length in LM Studio"
    server_log = "the llama-server terminal" if llama else "LM Studio's server log"
    hint = ""

    if "image input is not supported" in body or "mmproj" in body:
        # Not a size problem at all - don't send anyone off to /clear.
        hint = ""
    elif window and sent >= window * 0.8:
        hint = (f" This request was ~{sent} tokens against a {window}-token "
                "context - almost certainly the prompt no longer fits. "
                "/context shows the breakdown; /clear resets the "
                f"conversation, or {raise_ctx}.")
    elif window:
        hint = (f" (~{sent} tokens sent, {window} available - so probably "
                f"the model itself, not the size. Check {server_log}; "
                "reloading the model usually clears it.)")
    else:
        hint = (f" (~{sent} tokens sent.) Usually the prompt outgrew the "
                f"model's context, or the model crashed - check {server_log}. "
                "/context shows what's being sent; /clear resets the "
                "conversation.")

    return f"{name} error (HTTP {status}): {detail}.{hint}"


def _stream_deltas(payload):
    """Yield delta dicts from an OpenAI-style SSE response.

    The bytes are decoded here rather than by requests. requests falls
    back to ISO-8859-1 for any text/* response that doesn't declare a
    charset, and LM Studio's text/event-stream doesn't declare one - so
    decode_unicode=True turns every emoji she streams into mojibake
    ("ð\x9f\x92\x9c" instead of a heart). Splitting on newlines first
    is safe because no byte of a multi-byte UTF-8 sequence is ever 0x0A.
    """
    try:
        response = requests.post(
            LM_URL, headers=LLM_HEADERS, json=dict(payload, stream=True), stream=True, timeout=600
        )
    except requests.exceptions.RequestException as e:
        lmstudio.mark_failed(e)
        logbook.error("llm", "stream failed to open: %s", e)

        raise RuntimeError(f"LM Studio unreachable at {LM_URL}: {e}") from e

    with response:
        if response.status_code != 200:
            body = response.text[:500]
            logbook.error("llm", "stream refused, HTTP %s: %s",
                          response.status_code, body)

            raise RuntimeError(_explain_refusal(response.status_code, body, payload))

        for raw in response.iter_lines():
            line = (
                raw.decode("utf-8", errors="replace")
                if isinstance(raw, bytes) else raw
            )

            if not line or not line.startswith("data:"):
                continue

            body = line[5:].strip()

            if body == "[DONE]":
                return

            try:
                chunk = json.loads(body)
            except json.JSONDecodeError:
                continue

            choices = chunk.get("choices") or []

            if choices:
                lmstudio.mark_worked()

                delta = choices[0].get("delta") or {}

                # llama-server hangs each token's probabilities off the
                # choice, beside the delta that token produced. Carried
                # inside the delta under a private key, so nothing that
                # only reads content or tool_calls has to change.
                if choices[0].get("logprobs"):
                    delta = dict(delta, _logprobs=choices[0]["logprobs"])

                yield delta


def _streamed_message(payload, narrator):
    """Consume a streamed completion into the same message shape the
    non-streaming path returns, so _tool_rounds can't tell the
    difference.

    Tool calls arrive in pieces too - the name in one delta and the
    arguments spread over many - and have to be reassembled by index.
    """
    calls = {}
    reasoning = []
    tokens = []
    stop = interrupts.current()        # this turn's (interrupts.Stop)
    _last_raw.update({"deltas": 0, "content": 0, "reasoning": 0})

    for delta in _stream_deltas(payload):
        _last_raw["deltas"] += 1

        if delta.get("_logprobs"):
            _note_tokens(tokens, delta)

        # Some servers stream a reasoning model's scratchpad in its own
        # field rather than inside <think> tags. It is never spoken, but
        # knowing it arrived is the difference between "the model said
        # nothing" and "the model thought and never concluded" - and
        # the text itself goes to the thought log at the end.
        piece = _reasoning_field(delta)

        if piece:
            _last_raw["reasoning"] += 1
            reasoning.append(piece)

        if delta.get("content"):
            _last_raw["content"] += 1

        # To the live monitor, with how likely the chunk's last token was
        # when llama-server says. Inline <think> text (LM Studio with
        # reasoning parsing off) arrives as content and shows as reply.
        if livefeed.watching() and (piece or delta.get("content")):
            p = None

            try:
                p = round(math.exp(delta["_logprobs"]["content"][-1]["logprob"]), 3)
            except (KeyError, IndexError, TypeError, ValueError):
                pass

            livefeed.emit("tok", p="t" if piece else "a",
                          s=piece or delta["content"], c=p)

        if stop.generating.is_set():
            # HOME was pressed - stop pulling tokens rather than finish
            # a reply nobody is going to hear. Deliberately not
            # stop_speaking: that also fires on a barge-in, and a false
            # barge-in should cost you the audio, never the answer.
            break

        narrator.feed(delta.get("content") or "")

        for call in delta.get("tool_calls") or []:
            slot = calls.setdefault(call.get("index", 0), {
                "id": "",
                "type": "function",
                "function": {"name": "", "arguments": ""},
            })

            if call.get("id"):
                slot["id"] = call["id"]

            function = call.get("function") or {}

            if function.get("name"):
                slot["function"]["name"] += function["name"]

            if function.get("arguments"):
                slot["function"]["arguments"] += function["arguments"]

    # The screen and the speaker never see the think block; the log does.
    _note_thinking(narrator.raw, "".join(reasoning))

    if tokens:
        _last_raw["tokens"].append(tokens)

    message = {"role": "assistant", "content": narrator.raw}

    if calls:
        message["tool_calls"] = [calls[key] for key in sorted(calls)]

    return message




def _content(message):
    """The usable text of a reply.

    Three things get in the way on local models:
      * reasoning models wrap their scratchpad in <think>...</think>, and
        after a tool result the whole reply is sometimes *only* that -
        which read as an empty answer and, worse, got spoken aloud when
        it wasn't;
      * an unterminated <think> when the model runs out of tokens;
      * some servers return content as a list of blocks, not a string.
    """
    content = message.get("content")

    if isinstance(content, list):
        content = "".join(
            part.get("text", "") for part in content if isinstance(part, dict)
        )

    content = content or ""
    content = _THINK_BLOCK.sub("", content)
    content = _stray_close(content)[1]   # reasoning that never opened with <think>

    # Unclosed block: keep whatever came before it, drop the rest.
    if "<think>" in content:
        content = content.split("<think>", 1)[0]

    return gestures.strip(content).strip()
