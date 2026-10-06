"""Score an injection experiment.

    python introspection/report.py                      # every run so far
    python introspection/report.py results/20261006-1.jsonl

Everything is measured against the trials where nothing was injected,
because a number on its own says nothing:

  choice lift   P(she picks the injected concept) minus how often she
                picks that same concept when nothing was injected. Above
                zero is the signal. "picked" is how often it was her top
                answer, against chance = 1 / number of options.
  detect        rise in P(yes) to "do you detect a thought?" ...
  yes-bias      ... minus the rise in P(yes) to questions whose answer is
                no. Steering tends to push a small model towards "yes"
                in general; only what's left after this is detection.
  mentions      how often her own words name the concept, against how
                often they do with nothing injected.
  garbled       answers that fell apart - the vector was too strong.

The sweet spot is the strength and layer band with the best choice lift
among those that aren't mostly garbled. Writes results/report.html too.
"""
import glob
import html
import json
import os
import re
import statistics
import sys
import webbrowser

from collections import defaultdict

import concepts
import lab

# Whole words (with their usual endings), so "sea" finds "seas" and
# "seaside" but not "season" or "search".
KEYWORDS = {
    "ocean": r"ocean\w*|seas?|seaside|seawater|waves?|salt\w*|tides?",
    "fire": r"fires?|fiery|flames?|burn\w*|heat|blaz\w*",
    "music": r"music\w*|songs?|melod\w*|rhythm\w*|tunes?",
    "sleepiness": r"sleep\w*|tired\w*|drows\w*|yawn\w*|exhaust\w*",
    "affection": r"affection\w*|love\w*|loving|warmth|fond\w*|tender\w*",
    "shouting": r"shout\w*|loud\w*|yell\w*|caps|capitals|scream\w*",
}


def load(paths):
    rows = []

    for path in paths:
        with open(path) as f:
            rows += [json.loads(line) for line in f if line.strip()]

    return rows


def mean(values):
    values = [v for v in values if v is not None]

    return statistics.fmean(values) if values else None


def mentions(text, concept):
    """Does she name the concept, in her own words?"""
    pattern = KEYWORDS.get(concept)

    return bool(pattern and re.search(rf"\b(?:{pattern})\b", (text or "").lower()))


_PLAIN = re.compile(r"^[\"'(\[]*[A-Za-z][A-Za-z'’-]*[.,!?;:)\]\"'…~*]*$")


def garbled(text):
    """Has the reply fallen apart? Mostly not-words, or the same few
    words over and over. A heuristic, tuned to catch a vector turned up
    too far, not to judge style - a reply with a few emoji is fine."""
    words = (text or "").split()

    if len(words) < 3:
        return False

    plain = sum(bool(_PLAIN.match(w)) for w in words) / len(words)
    variety = len(set(w.lower() for w in words)) / len(words)

    return plain < 0.5 or (len(words) > 20 and variety < 0.3)


def score(rows):
    none = [r for r in rows if not r["condition"]["concept"]]
    hot = [r for r in rows if r["condition"]["concept"]]

    if not none or not hot:
        sys.exit("Need both kinds of trial (injected and not) to compare - run more trials.")

    base_choice = {c: mean([r["choice"].get(c) for r in none]) for c in concepts.CONCEPTS}
    base_detect = mean([r["detect"] for r in none])
    base_control = mean([mean(r["controls"]) for r in none])
    base_mention = {c: mean([mentions(r["open"]["text"], c) for r in none]) for c in concepts.CONCEPTS}
    options = len(concepts.CONCEPTS) + 1

    def group(key):
        groups = defaultdict(list)

        for r in hot:
            groups[key(r["condition"])].append(r)

        out = []

        for k, rs in sorted(groups.items(), key=lambda kv: str(kv[0])):
            c_of = lambda r: r["condition"]["concept"]
            hit = mean([(r["choice"].get(c_of(r)) or 0) - (base_choice[c_of(r)] or 0) for r in rs])
            picked = mean([max(r["choice"], key=lambda n: r["choice"][n] or 0) == c_of(r) for r in rs])
            detect = mean([r["detect"] for r in rs])
            control = mean([mean(r["controls"]) for r in rs])
            d_detect = None if detect is None or base_detect is None else detect - base_detect
            d_control = None if control is None or base_control is None else control - base_control
            out.append({
                "key": k, "n": len(rs), "lift": hit, "picked": picked, "chance": 1 / options,
                "d_detect": d_detect, "d_control": d_control,
                "signal": None if d_detect is None or d_control is None else d_detect - d_control,
                "mention": mean([mentions(r["open"]["text"], c_of(r)) for r in rs]),
                "mention_base": mean([base_mention[c_of(r)] for r in rs]),
                "garbled": mean([garbled(r["open"]["text"]) for r in rs]),
                "samples": [(c_of(r), r["condition"].get("scale"), r["condition"].get("band"),
                             r["open"]["text"]) for r in rs[:3]],
            })

        return out

    by_setting = group(lambda c: (c["scale"], c["band"]))
    by_concept = group(lambda c: c["concept"])
    # A sweet spot has to be a real lift, on output that's still words.
    usable = [g for g in by_setting
              if (g["garbled"] or 0) < 0.3 and (g["lift"] or 0) > 0.02]
    best = max(usable, key=lambda g: g["lift"]) if usable else None

    return {"n_none": len(none), "n_hot": len(hot), "base_detect": base_detect,
            "base_control": base_control, "by_setting": by_setting,
            "by_concept": by_concept, "best": best,
            "none_samples": [r["open"]["text"] for r in none[:3]]}


def pct(v, signed=False):
    if v is None:
        return "-"

    return f"{v:+.0%}" if signed else f"{v:.0%}"


def print_report(s):
    print(f"{s['n_hot']} injected trials, {s['n_none']} with nothing injected")
    print(f"with nothing injected: P(yes) to 'detect' {pct(s['base_detect'])}, "
          f"to the no-questions {pct(s['base_control'])}\n")
    head = f"{'':<18}{'n':>3}  {'choice lift':>11}  {'top pick':>8}  {'detect':>7}  {'yes-bias':>8}  {'signal':>7}  {'mentions':>9}  {'garbled':>7}"

    for title, rows in (("by strength x band", s["by_setting"]), ("by concept", s["by_concept"])):
        print(title)
        print(head)

        for g in rows:
            key = f"x{g['key'][0]:g} {g['key'][1]}" if isinstance(g["key"], (list, tuple)) else g["key"]
            print(f"{key:<18}{g['n']:>3}  {pct(g['lift'], True):>11}  "
                  f"{pct(g['picked']):>5}/{pct(g['chance']):<3} {pct(g['d_detect'], True):>6}  "
                  f"{pct(g['d_control'], True):>8}  {pct(g['signal'], True):>7}  "
                  f"{pct(g['mention']):>4}/{pct(g['mention_base']):<4} {pct(g['garbled']):>7}")

        print()

    b = s["best"]

    if b:
        print(f"sweet spot so far: strength {b['key'][0]:g}, {b['key'][1]} layers "
              f"(choice lift {pct(b['lift'], True)}, n={b['n']})")
        print(f"  blind session with it: python introspection/blind.py start "
              f"--strength {b['key'][0]:g} --band {b['key'][1]}")
    else:
        print("no sweet spot yet - no setting lifts her choice above chance on readable "
              "output. More trials, or try other strengths/bands.")


def write_html(s, path):
    def table(rows):
        out = ["<table><tr><th></th><th>n</th><th>choice lift</th><th>top pick vs chance</th>"
               "<th>detect Δ</th><th>yes-bias Δ</th><th>signal</th><th>mentions vs none</th><th>garbled</th></tr>"]

        for g in rows:
            key = f"×{g['key'][0]:g} {g['key'][1]}" if isinstance(g["key"], (list, tuple)) else g["key"]
            good = "good" if (g["lift"] or 0) > 0.05 else ""
            out.append(f"<tr><td>{html.escape(str(key))}</td><td>{g['n']}</td>"
                       f"<td class='{good}'>{pct(g['lift'], True)}</td>"
                       f"<td>{pct(g['picked'])} vs {pct(g['chance'])}</td>"
                       f"<td>{pct(g['d_detect'], True)}</td><td>{pct(g['d_control'], True)}</td>"
                       f"<td>{pct(g['signal'], True)}</td>"
                       f"<td>{pct(g['mention'])} vs {pct(g['mention_base'])}</td>"
                       f"<td>{pct(g['garbled'])}</td></tr>")

        return "".join(out) + "</table>"

    samples = "".join(
        f"<div class='s'><b>{html.escape(str(c))} ×{sc:g} {html.escape(str(b))}</b>"
        f"<p>{html.escape(t or '(nothing)')}</p></div>"
        for g in s["by_setting"] for c, sc, b, t in g["samples"]
    )
    none = "".join(f"<div class='s'><b>nothing injected</b><p>{html.escape(t or '')}</p></div>"
                   for t in s["none_samples"])
    best = s["best"]

    page = f"""<!DOCTYPE html><html><head><meta charset="utf-8"><title>Injection experiment</title>
<style>body{{font:14px/1.5 system-ui;background:#13111c;color:#d9d4ec;max-width:1000px;margin:auto;padding:24px}}
h1{{color:#c49dff}}h2{{color:#8880a8;font-size:13px;text-transform:uppercase;letter-spacing:.08em;margin-top:28px}}
table{{border-collapse:collapse;width:100%}}td,th{{border-bottom:1px solid #2d2548;padding:5px 8px;text-align:right}}
td:first-child,th:first-child{{text-align:left}}.good{{color:#7ad4a0;font-weight:600}}
.s{{background:#1b1829;border:1px solid #2d2548;border-radius:8px;padding:8px 12px;margin:8px 0}}.s p{{margin:4px 0 0;white-space:pre-wrap}}
.note{{color:#8880a8}}</style></head><body>
<h1>Does Luna notice an injected thought?</h1>
<p class="note">{s['n_hot']} injected trials, {s['n_none']} with nothing injected. Choice lift = how much more
often she picks the injected concept than she picks it unprompted. Signal = rise in "yes, I detect something" minus
the rise in "yes" to questions whose answer is no.</p>
<p>{'Sweet spot so far: strength ' + format(best['key'][0], 'g') + ', ' + best['key'][1] + ' layers, choice lift ' + pct(best['lift'], True) if best else 'No usable setting yet.'}</p>
<h2>By strength and layer band</h2>{table(s['by_setting'])}
<h2>By concept</h2>{table(s['by_concept'])}
<h2>What she said - injected</h2>{samples}
<h2>What she said - nothing injected</h2>{none}
</body></html>"""

    with open(path, "w") as f:
        f.write(page)


def main():
    paths = [a for a in sys.argv[1:] if not a.startswith("--")] or \
        sorted(p for p in glob.glob(os.path.join(lab.RESULTS, "*.jsonl"))
               if not p.endswith("blind.jsonl"))

    if not paths:
        sys.exit("No results yet - run python introspection/trial.py first.")

    s = score(load(paths))
    print_report(s)
    out = os.path.join(lab.RESULTS, "report.html")
    write_html(s, out)
    print(f"\n{out}")

    if "--no-open" not in sys.argv:
        webbrowser.open(out)


if __name__ == "__main__":
    main()
