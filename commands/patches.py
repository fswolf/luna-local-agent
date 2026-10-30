"""Her patches: /good, /fix, /examples for the examples, /patches for the trained ones (docs/patches.md).

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

    if text == "/patches" or text.startswith("/patches "):
        from training import patches

        words = text.split()[1:]
        if len(words) == 2:
            try:
                p = patches.set_scale(words[0], words[1])
            except ValueError as e:
                ui.add_message("system", f"Not changed: {e}.")
                return True
            ui.add_message("system", f"{_short(p['path'].rsplit('/', 1)[-1], 60)} at {p['scale']:g} "
                           "(until llama-server restarts; 0 = off, 1 = full).")
            return True
        if words:
            ui.add_message("system", "/patches  or  /patches <name or id> <strength 0-1>")
            return True
        model, found, live = patches.current_model(), patches.local(), patches.loaded()
        lines = [f"Her patches (llama/patches/) - model: {model or 'not started by llama/start.sh yet'}"]
        if not found:
            lines.append("  none trained yet: training/train.sh gesture|habit (docs/patches.md)")
        for p in found:
            on = next((r for r in live or [] if r["path"].endswith(p["name"] + ".gguf")), None)
            state = (f"loaded, id {on['id']}, strength {on['scale']:g}" if on else
                     "fits, not loaded (restart llama/start.sh)" if p["fits"] else f"left out: made for {p['for'] or 'unknown'}")
            lines.append(f"  {p['name']}  [{p['kind']}, {p['examples'] or '?'} examples]  {state}")
        if live is None:
            lines.append("  (llama-server isn't answering, so what's loaded is unknown)")
        ui.add_message("system", "\n".join(lines))
        return True

    return False
