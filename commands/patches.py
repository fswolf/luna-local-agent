"""Examples for her patches: /good, /fix, /examples (docs/patches.md).

Slash commands never reach her history, transcript or notes, so keeping
or correcting a reply here teaches a future patch without her hearing
about it.

Part of the commands package; see commands/__init__.py.
"""
import ui


def _short(text, n=70):
    text = " ".join(str(text).split())
    return text if len(text) <= n else text[:n - 1] + "…"


def handle(text):
    """True when text was one of these commands (and it ran)."""
    if text == "/good" or text.startswith("/good "):
        from training import dataset

        try:
            ex = dataset.keep("good")
        except ValueError as e:
            ui.add_message("system", f"Not kept: {e}.")
            return True
        n = dataset.counts()["habit"]["approved"]
        ui.add_message("system", f"Kept her last reply as a good example ({n} so far): {_short(ex['reply'])}")
        return True

    if text == "/fix" or text.startswith("/fix "):
        from training import dataset

        better = text[len("/fix"):].strip()
        if not better:
            ui.add_message("system", "/fix <the reply she should have given> - saves your version "
                           "of her last reply as an example. She doesn't see it.")
            return True
        try:
            ex = dataset.keep("fix", reply=better)
        except ValueError as e:
            ui.add_message("system", f"Not kept: {e}.")
            return True
        n = dataset.counts()["habit"]["approved"]
        ui.add_message("system", f"Kept your version as an example ({n} so far)"
                       + ("" if ex["original"] else " - it was the same as hers, so kept as good") + ".")
        return True

    if text == "/examples":
        from training import dataset

        c = dataset.counts()
        lines = ["Examples for her patches (agent/dataset/, never committed):"]
        for kind, n in c.items():
            lines.append(f"  {kind:8} {n['approved']} approved, {n['waiting']} waiting, {n['dropped']} dropped")
        lines.append("/good keeps her last reply, /fix <better> keeps your version. "
                     "A first patch wants 300 to 500.")
        try:
            from web import dataset_web

            lines.append(f"Look through them: {dataset_web.url()}")
        except Exception:
            pass
        ui.add_message("system", "\n".join(lines))
        return True

    return False
