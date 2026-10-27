"""What she remembers and learns: /facts, /thoughts, /memory, /reflect, /lessons, /skills,
/projects, /knowledge, /episodes.

Part of the commands package; see commands/__init__.py.
"""
import os
import sys
import threading

import config
from web import livefeed
from mind import longterm
from web import portrait_window
from mind import reflect
import ui

from . import ctx


def handle(text):
    """True when text was one of these commands (and it ran)."""
    if text.startswith("/facts"):

        argument = text[6:].strip().lower()
        which = longterm.backend()

        if which == "sqlite":
            from mind import factstore

            active, retired = factstore.counts()

            if argument == "retired":
                listing = factstore.rows(retired=True, limit=30)
                shown = "\n".join(
                    f"  ~ {fact}  (retired {when[:10]})"
                    for _i, fact, _s, _c, when in listing
                ) or "  (none)"
                ui.add_message(
                    "system",
                    f"{retired} retired fact(s) - superseded, kept for "
                    f"history:\n{shown}",
                )
                return True

            limit = 500 if argument == "all" else 20
            listing = factstore.rows(retired=False, limit=limit)
            shown = "\n".join(
                f"  - {fact}" + (f"  [{subject}]" if subject else "")
                for _i, fact, subject, _c, _w in reversed(listing)
            ) or "  (none yet)"
            more = (
                f"\n  ... /facts all shows the rest of the {active}."
                if argument != "all" and active > limit else ""
            )
            ui.add_message(
                "system",
                f"Memory backend: sqlite (experimental) - {active} active, "
                f"{retired} retired. Newest {min(active, limit)}:\n{shown}{more}"
                "\n/facts retired shows what's been superseded. "
                "/set long_term_memory.backend json falls back to the old "
                "handling - nothing is lost either way.",
            )
        else:
            facts = longterm.get_facts()
            shown = "\n".join(f"  - {f}" for f in facts) or "  (none yet)"
            ui.add_message(
                "system",
                f"Memory backend: json (capped at "
                f"{config.LONG_TERM_MEMORY_MAX_FACTS}) - {len(facts)} "
                f"fact(s):\n{shown}\n"
                "/set long_term_memory.backend sqlite switches to the "
                "experimental permanent store.",
            )
        return True

    if text in ("/thoughts", "/memory"):
        # Both pages live on the live monitor's server while she runs -
        # one port, no extra process. With the monitor off, the old
        # standalone servers still work.

        from mind import thoughtlog

        page = text[1:]
        if config.MONITOR_ENABLED:

            url = f"{livefeed.url()}/{page}/"

            portrait_window.quiet_open(url)
        else:
            import subprocess

            folder, file, port = (("thought-viewer", "viewer.py", 8791) if page == "thoughts"
                                  else ("memory-manager", "manager.py", 8790))
            url = f"http://127.0.0.1:{port}"
            subprocess.Popen([sys.executable, os.path.join(config.BASE_DIR, folder, file)],
                             stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

        ui.add_message("system", (f"{thoughtlog.summary()} - " if page == "thoughts" else "Memory editor: ")
                       + url)
        return True

    if text == "/reflect":

        def run():
            ui.set_status("Reflecting...")

            try:
                reflect.run_all(ctx.model, report=lambda line: ui.add_message("system", line))
            except Exception as e:
                ui.add_message("system", f"Reflection failed: {e}")
            finally:
                ui.set_status("Idle")

        ui.add_message("system", "Reflecting - session notes, then lessons, then "
                       "fact cleanup. A minute or two.")
        threading.Thread(target=run, daemon=True).start()
        return True

    if text == "/lessons" or text.startswith("/lessons "):
        from mind import notebook

        words = text.split()

        if len(words) == 3 and words[1] in ("forget", "restore") and words[2].isdigit():
            ok = (notebook.retire_lesson if words[1] == "forget"
                  else notebook.restore_lesson)(int(words[2]))
            done = "restored" if words[1] == "restore" else "hidden from her"
            ui.add_message("system", f"Lesson {words[2]} {done}." if ok
                           else f"No lesson {words[2]} to {words[1]}.")
            return True

        retired = len(words) > 1 and words[1] == "retired"
        rows = notebook.lessons(retired=retired)

        if not rows:
            ui.add_message("system", "No retired lessons." if retired else
                           "No lessons yet - they come from the dream pass "
                           "(/reflect, or on its own once a day while she's idle).")
            return True

        ui.add_message("system", "\n".join(
            [f"{'Retired' if retired else 'Lessons'} ({len(rows)}):"]
            + [f"{l['id']:>3}. {l['text']}"
               + (f"  [from #{', #'.join(map(str, l['from']))}]" if l["from"]
                  else "  [noted herself]" if l.get("origin") == "self" else "")
               + (f"  ×{l['hits']}" if l["hits"] else "") for l in rows]
            + ["/lessons forget <n> hides one; /lessons retired lists hidden ones."]))
        return True

    if text == "/skills" or text.startswith("/skills "):
        from mind import skills

        words = text.split()

        if len(words) == 3 and words[1] in ("forget", "restore", "show") and words[2].isdigit():
            n = int(words[2])

            if words[1] == "show":
                found = skills.get(n)
                ui.add_message("system", skills.render(found) + (
                    f"\n  tools: {', '.join(found['tools'])}" if found and found["tools"] else "")
                    + (f"\n  used {found['uses']}x" if found and found["uses"] else "")
                    if found else f"No recipe {n}.")
                return True

            ok = (skills.retire if words[1] == "forget" else skills.restore)(n)
            done = "restored" if words[1] == "restore" else "hidden from her"
            ui.add_message("system", f"Recipe {n} {done}." if ok else f"No recipe {n} to {words[1]}.")
            return True

        retired = len(words) > 1 and words[1] == "retired"
        rows = skills.skills(retired=retired)

        if not rows:
            ui.add_message("system", "No retired recipes." if retired else
                           "No recipes yet - she saves one with save_skill after a multi-step "
                           "job goes right, or when you tell her to remember how she did it.")
            return True

        ui.add_message("system", "\n".join(
            [f"{'Retired recipes' if retired else 'Recipes'} ({len(rows)}):"]
            + [f"{s['id']:>3}. {s['name']}  - when: {s['when']}  ({len(s['steps'])} steps"
               + (f", used {s['uses']}x" if s["uses"] else "") + ")" for s in rows]
            + ["/skills show <n> prints one; /skills forget <n> hides it; /skills retired lists hidden ones."]))
        return True

    if text == "/projects" or text.startswith("/projects "):
        from mind import projects

        words = text.split()
        verbs = ("show", "done", "pause", "resume", "drop", "restore")

        if len(words) == 3 and words[1] in verbs and words[2].lstrip("#").isdigit():
            n = int(words[2].lstrip("#"))
            p = projects.get(n)

            if not p:
                ui.add_message("system", f"No project {n}.")
                return True

            if words[1] == "show":
                log = projects.entries(n)
                ui.add_message("system", "\n".join(
                    [projects.render(p, recent=0)]
                    + [f"  {e['at'][:16].replace('T', ' ')}  {e['kind']}: {e['text']}" for e in log[-30:]]
                    + ([] if log else ["  (nothing recorded yet)"])))
                return True

            if words[1] == "drop":
                ok, done = projects.retire(n), "dropped (/projects restore brings it back)"
            elif words[1] == "restore":
                ok, done = projects.restore(n), "restored"
            else:
                status = {"done": "done", "pause": "paused", "resume": "active"}[words[1]]
                ok, done = projects.set_status(n, status), f"marked {status}"

            ui.add_message("system", f"Project {n} {done}." if ok else f"Project {n} unchanged.")
            return True

        if len(words) > 1 and words[1] == "dropped":
            rows = projects.projects(retired=True)
        else:
            rows = projects.projects()

        if not rows:
            ui.add_message("system", "No projects yet - she starts one with start_project when "
                           "you begin something that spans sessions, or ask her to track one.")
            return True

        order = {"active": 0, "paused": 1, "done": 2}
        rows.sort(key=lambda p: p["updated"], reverse=True)       # newest first...
        rows.sort(key=lambda p: order.get(p["status"], 3))         # ...within active, paused, done
        ui.add_message("system", "\n".join(
            [f"Projects ({len(rows)}):"]
            + [f"{p['id']:>3}. [{p['status']}] {p['title']}"
               + (f"  - next: {p['next']}" if p["next"] and p["status"] != "done" else "") for p in rows]
            + ["/projects show <n> for the log; done|pause|resume|drop <n> to steer."]))
        return True

    if text == "/knowledge" or text.startswith("/knowledge "):
        from mind import knowledge

        rest = text[len("/knowledge"):].strip()
        word, _, arg = rest.partition(" ")
        word, arg = word.lower(), arg.strip()

        if word in ("reindex", "rescan", "refresh"):
            knowledge.reindex()
            ui.add_message("system", "Knowledge: looking through the folders again - /knowledge shows progress.")
        elif word == "add" and arg:
            path = knowledge.resolve(arg)

            if not os.path.isdir(path):
                ui.add_message("system", f"Knowledge: {arg} isn't a folder.")
            else:
                knowledge.set_folders(knowledge.folders() + [path])
                ui.add_message("system", f"Knowledge: added {path}, indexing it now.")
        elif word == "remove" and arg:
            path = knowledge.resolve(arg)
            knowledge.set_folders([f for f in knowledge.folders() if f != path])
            ui.add_message("system", f"Knowledge: {path} removed; its passages go on the next scan.")
        elif word == "search" and arg:
            found, how = knowledge.search(arg, 5)
            ui.add_message("system", "\n".join(
                [f"Knowledge search ({how}):"] + [f"  {s:.2f}  {knowledge._where(i)}" for s, i in found]
                if found else ["Knowledge: nothing matches."]))
        else:
            ui.add_message("system", knowledge.status())
        return True

    if text == "/episodes" or text.startswith("/episodes "):
        from mind import notebook

        words = text.split()

        if len(words) == 3 and words[1] == "forget" and words[2].isdigit():
            ok = notebook.delete_episode(int(words[2]))
            ui.add_message("system", f"Episode {words[2]} forgotten." if ok
                           else f"No episode {words[2]}.")
            return True

        rows = notebook.episodes(8)
        felt = notebook.game_feelings()

        if not rows and not felt:
            ui.add_message("system", "No session notes yet - a conversation is "
                           f"written up after {config.SELF_IDLE_MINUTES} quiet "
                           "minutes, or at the next startup.")
            return True

        games = notebook.play_episodes()
        head = ("How she feels about games:\n" + "\n".join(
            f"  {f['title']}: {f['feeling']}" for f in felt.values()) + "\n\n") if felt else ""
        ui.add_message("system", head + "\n\n".join(
            f"{e['id']}. {e['started'][:16].replace('T', ' ')} "
            f"({games[e['id']] + ', ' if e['id'] in games else ''}{e['turns']} "
            f"{'turns' if e['id'] in games else 'lines'})\n{e['summary']}"
            for e in rows) + "\n\n/episodes forget <n> deletes one; /memory edits it all.")
        return True

    return False
