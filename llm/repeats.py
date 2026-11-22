"""Her reply saying itself twice, or saying yours back (llm/turns.py).

A small model copies what it sees. Once one reply came out as itself,
"~mew~ There we go, Daddy~", then itself again, every later turn had
that shape in its history, and copied it: each reply grew a second
copy, sometimes of the reply before or of your own message. Cutting the
copy before the reply is saved breaks the loop; the thought log keeps
what she actually wrote.

Two checks, both by wording, nothing about meaning:

  * a tail made of what's already been said - earlier in this reply,
    in her previous reply, or in your message - is cut, with the short
    line that led into it ("There we go~"), as long as something new
    came first;
  * a paragraph that is your message said back is dropped, wherever it is.

Short lines are never enough on their own: "*tilts head* 🌸" turns up in
every reply on purpose. Code is never touched: a script she sends again
with one line changed is mostly the last one, and that's the point of it.
"""
import os
import re
import unicodedata

LONG = 25          # a sentence this long (letters and digits only) counts as wording
MIN_COPY = 150     # this much copied wording before a tail is cut
SHARE = 0.6        # and at least this share of what's left
BRIDGE = 40        # a lead-in line this short goes with the copy
WORDED = 50        # a paragraph with this much wording has to be a copy for the tail to be one
FRESH = 100        # and this much new wording has to come before it

_SENTENCE = re.compile(r"(?<=[.!?~])\s+|\n")


def _norm(text):
    """Letters and digits only, lower case: emoji, *actions* marks and
    spacing don't make two copies different."""
    text = unicodedata.normalize("NFKC", str(text or "")).lower()
    return re.sub(r"[\W_]+", "", text)


def _sentences(text):
    return [n for n in (_norm(s) for s in _SENTENCE.split(str(text or ""))) if len(n) >= LONG]


def _paragraphs(text):
    """Paragraphs, with a ``` code block kept whole as one, however many
    blank lines it has. [(text, is_code)]"""
    out, code = [], None
    for chunk in re.split(r"(\n\s*\n)", str(text or "").strip()):
        if code is not None:
            code += chunk
            if chunk.count("```") % 2:
                out.append((code, True))
                code = None
        elif chunk.strip() and chunk.count("```") % 2:
            code = chunk                                    # a block opens here and runs on
        elif chunk.strip():
            out.append((chunk, "```" in chunk))
    if code is not None:
        out.append((code, True))                            # never closed: code to the end
    return out


def trim(answer, said="", previous=""):
    """The reply without its copied tail or your words said back. Returns
    (text, what was cut: "" | "repeat" | "echo" | "repeat+echo")."""
    blocks = _paragraphs(answer)
    if len(blocks) < 2:
        return answer, ""

    yours = _norm(said)
    cut = []

    # your message said back, as a paragraph of its own (never code)
    if len(yours) >= LONG:
        kept = [(p, code) for p, code in blocks
                if code or not (len(_norm(p)) >= LONG and (_norm(p) in yours or yours in _norm(p)))]
        if kept and len(kept) < len(blocks):
            blocks, cut = kept, ["echo"]

    paras = [p for p, _ in blocks]
    coded = [code for _, code in blocks]

    before = set(_sentences(previous)) | set(_sentences(said))
    norms = [_norm(p) for p in paras]

    def seen(k, earlier):
        """(copied wording, all wording) in paragraph k. Code counts as neither."""
        if coded[k]:
            return 0, 0
        sents = _sentences(paras[k])
        copied = sum(len(s) for s in sents if s in earlier or any(s in e for e in norms[:k] if len(e) > len(s)))
        return copied, sum(len(s) for s in sents)

    earlier = set(before)
    stats = []
    for k in range(len(paras)):
        stats.append(seen(k, earlier))
        if not coded[k]:
            earlier |= set(_sentences(paras[k]))

    # The copy starts where every paragraph with real wording in it, to the
    # end, is mostly said already. Something new has to come first: a reply
    # that is all repeat (asked the same thing twice) is left as it is.
    start = None
    for k in range(1, len(paras)):
        tail = stats[k:]
        if (stats[k][0] and not any(coded[k:]) and sum(c for c, _ in tail) >= MIN_COPY
                and all(c >= SHARE * t for c, t in tail if t >= WORDED)
                and sum(t - c for c, t in stats[:k]) >= FRESH):
            start = k
            break

    if start is not None:
        # walk back over short lines that are copies too, then one short lead-in
        while start > 1 and len(norms[start - 1]) < LONG and any(norms[start - 1] in e for e in norms[:start - 1]):
            start -= 1
        if start > 1 and len(norms[start - 1]) < BRIDGE:
            start -= 1
        paras = paras[:start]
        cut.append("repeat")

    return ("\n\n".join(paras), "+".join(sorted(cut, reverse=True))) if cut else (answer, "")


def clean_history(path):
    """Cut the copies out of the replies already saved in a history file
    (core/history.py's conversation.json), the ones that taught her the
    habit. A copy of the file is kept beside it first. Returns how many
    replies changed. Run it with Luna stopped: she saves over the file."""
    import json
    import shutil
    import time

    with open(path, encoding="utf-8") as f:
        data = json.load(f)
    messages = data.get("messages") if isinstance(data, dict) else None
    if not isinstance(messages, list):
        return 0

    changed, said, previous = 0, "", ""
    for m in messages:
        if not isinstance(m, dict) or not isinstance(m.get("content"), str):
            continue
        if m.get("role") == "user":
            said = m["content"]
        elif m.get("role") == "assistant":
            text, why = trim(m["content"], said, previous)
            if why:
                m["content"] = text
                changed += 1
            previous = m["content"]          # as it now stands, the way a live turn sees it

    if changed:
        shutil.copy2(path, f"{path}.before-repeats-{time.strftime('%Y%m%d-%H%M%S')}")
        tmp = path + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        os.replace(tmp, path)
    return changed


if __name__ == "__main__":
    import sys

    here = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    target = sys.argv[1] if len(sys.argv) > 1 else os.path.join(here, "history", "conversation.json")
    n = clean_history(target)
    print(f"{n} of her saved replies had a copy cut out of them" + (f" (the old file is kept beside {target})" if n else ""))
