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

# SQLite's INTEGER tops out here; a bigger id typed by hand was an
# OverflowError from inside the database call rather than "no such one".
_MAX_ID = 2 ** 63 - 1


def _id(word):
    """A typed id ("12" or "#12") as an int SQLite can take, or None."""
    word = word.lstrip("#")

    if not word.isdigit() or len(word) > 19 or int(word) > _MAX_ID:
        return None

    return int(word)


def _real(detail, lead="; "):
    """'; true from 2026-10 to 2026-11-14' and/or 'not sure', if there's either."""
    since, until, sure = detail or ("", "", True)
    notes = []
    if since or until:
        notes.append("true " + " ".join(x for x in (f"from {since}" if since else "",
                                                    f"to {until}" if until else "") if x))
    if not sure:
        notes.append("not sure")
    return lead + ", ".join(notes) if notes else ""


def _event_line(event):
    """One row of the audit log: "  11-24 09:12  #42 corrected by her tools: <fact> (was: ...)"."""
    _id, at, action, fact_id, fact, detail, by = event
    what = f"#{fact_id} " if fact_id is not None else ""
    words = f": {fact}" if fact else (": (the words were forgotten)" if action != "unforgotten" else "")
    return f"  {at[5:16].replace('T', ' ')}  {what}{action} by {by}{words}" + (f"  ({detail})" if detail else "")


def handle(text):
    """True when text was one of these commands (and it ran)."""
    if text.startswith("/facts"):

        argument = text[6:].strip().lower()

        if not longterm.ready():
            ui.add_message("system", "Memory: agent/facts.db can't be opened - the log says why.")
            return True

        from mind import factstore

        active, retired = factstore.counts()

        if argument == "retired":
            listing = factstore.rows(retired=True, limit=30)
            real = factstore.row_details([r[0] for r in listing])
            shown = "\n".join(
                f"  ~ {fact}  (retired {when[:10]}{_real(real.get(i))})"
                for i, fact, _s, _c, when in listing
            ) or "  (none)"
            ui.add_message(
                "system",
                f"{retired} retired fact(s) - superseded, kept for "
                f"history:\n{shown}",
            )
            return True

        if argument == "log" or argument.startswith("log "):
            # the audit log: every change, newest first; "/facts log 42" is one fact's history
            what = argument[3:].strip().lstrip("#")
            fact_id = int(what) if what.isdigit() else None
            listing = factstore.events(limit=40, fact_id=fact_id)
            shown = "\n".join(_event_line(e) for e in reversed(listing)) or "  (nothing yet)"
            ui.add_message(
                "system",
                (f"Fact #{fact_id}, every change:" if fact_id is not None else
                 "Her memory's last changes, oldest of these first (/facts log <number> for one fact's whole history):")
                + f"\n{shown}")
            return True

        if argument == "unsure":
            listing = [r for r in factstore.rows(limit=2000) if not factstore.is_sure(r[0])]
            shown = "\n".join(f"  ? {fact}" for _i, fact, _s, _c, _w in reversed(listing)) or "  (none)"
            ui.add_message(
                "system",
                f"{len(listing)} not sure - picked up once in passing. They're confirmed when they "
                f"come up again, when you say so, or on the memory page (/memory):\n{shown}",
            )
            return True

        limit = 500 if argument == "all" else 20
        listing = factstore.rows(retired=False, limit=limit)
        real = factstore.row_details([r[0] for r in listing])
        shown = "\n".join(
            f"  - {fact}" + (f"  [{subject}]" if subject else "") + _real(real.get(i), "  ")
            for i, fact, subject, _c, _w in reversed(listing)
        ) or "  (none yet)"
        more = (
            f"\n  ... /facts all shows the rest of the {active}."
            if argument != "all" and active > limit else ""
        )
        ui.add_message(
            "system",
            f"Memory: {active} active, {retired} retired"
            + (f", {factstore.forgotten_count()} forgotten for good" if factstore.forgotten_count() else "")
            + f". Newest {min(active, limit)}:\n{shown}{more}"
            "\n/facts retired shows what's been superseded, /facts unsure what she isn't sure of, "
            "/facts log every change and who made it.",
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
            if _id(words[2]) is None:
                ui.add_message("system", f"No lesson {words[2]}.")
                return True

            ok = (notebook.retire_lesson if words[1] == "forget"
                  else notebook.restore_lesson)(_id(words[2]))
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
            n = _id(words[2])

            if n is None:
                ui.add_message("system", f"No recipe {words[2]}.")
                return True

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
        verbs = ("show", "done", "pause", "resume", "drop", "restore", "unplan")

        # a note of hers that's wrong ("the lab is upstairs"): kept, marked, never shown to her again
        if len(words) == 3 and words[1] == "wrong" and words[2].lstrip("#").isdigit():
            ok = projects.mark_wrong(int(words[2].lstrip("#")))
            ui.add_message("system", f"Note {words[2]} marked wrong - she won't see it on a game turn again."
                           if ok else f"No note {words[2]}.")
            return True

        if len(words) == 3 and words[1] in verbs and words[2].lstrip("#").isdigit():
            n = _id(words[2])
            p = projects.get(n) if n is not None else None

            if not p:
                ui.add_message("system", f"No project {words[2]}.")
                return True

            if words[1] == "show":
                log = projects.entries(n)
                ui.add_message("system", "\n".join(
                    [projects.render(p, recent=0)]
                    + [f"  [{e['id']}] {e['at'][:16].replace('T', ' ')}  {e['kind']}: {e['text']}" for e in log[-30:]]
                    + ([] if log else ["  (nothing recorded yet)"])
                    + (["  /projects wrong <note> hides a wrong note from her; /projects unplan "
                        f"{n} clears her plan."] if log or p["next"] else [])))
                return True

            if words[1] == "unplan":
                projects.set_next(n, "")
                ok, done = True, "has no plan now - she makes a new one on her next turn"
            elif words[1] == "drop":
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
            + ["/projects show <n> for the log; done|pause|resume|drop|unplan <n> to steer; "
               "wrong <note> hides a wrong note."]))
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

    if text == "/pages" or text.startswith("/pages "):
        from mind import pages

        word = text[len("/pages"):].strip()
        if word.lower() == "rebuild":
            n = pages.rebuild_all()
            ui.add_message("system", f"{n} page(s) will be rewritten on her next idle pass (or /reflect now).")
        elif word.lower().startswith("forget "):
            gone = pages.forget(word[7:].strip())
            ui.add_message("system", f"Page on {gone} dropped." if gone else "No page by that name.")
        elif word:
            page = pages.get(word)
            ui.add_message("system", f"{word}: {page['text']}\n(from {page['facts']} facts, {page['updated'][:16].replace('T', ' ')})"
                           if page else f"No page on {word}. /pages lists them.")
        else:
            have = pages.pages()
            waiting = sorted(set(pages.subjects()) - set(have))
            lines = [f"{s} ({p['facts']} facts, {p['updated'][5:10]}): {p['text'][:110]}{'...' if len(p['text']) > 110 else ''}"
                     for s, p in have.items()] or ["No pages yet."]
            if waiting:
                lines.append("Waiting for her next idle pass: " + ", ".join(waiting))
            lines.append("A subject gets a page once 3 of your facts are about it. /pages <subject> reads one; "
                         "/pages rebuild, /pages forget <subject>.")
            ui.add_message("system", "\n".join(lines))
        return True

    if text == "/profile" or text.startswith("/profile "):
        from mind import profiles

        word = text[len("/profile"):].strip()
        if word.lower() == "rebuild":
            n = profiles.rebuild_all()
            ui.add_message("system", f"{n} profile(s) will be rewritten on her next idle pass (or /reflect now).")
        elif word.lower().startswith("forget "):
            gone = profiles.forget(word[7:].strip())
            ui.add_message("system", f"Profile of {gone} dropped." if gone else "No profile by that name.")
        elif word:
            found = profiles.get(word)
            ui.add_message("system", f"{found['text']}\n(from {found['facts']} facts, {found['updated'][:16].replace('T', ' ')})"
                           if found else f"No profile of {word}. /profile lists them.")
        else:
            have = profiles.profiles()
            waiting = [profiles.label(p) for p in profiles.material() if p not in have]
            lines = [f"{profiles.label(p)} ({c['facts']} facts, {c['updated'][5:10]}): {c['text'][:110]}{'...' if len(c['text']) > 110 else ''}"
                     for p, c in have.items()] or ["No profiles yet."]
            if waiting:
                lines.append("Waiting for her next idle pass: " + ", ".join(waiting))
            if not profiles.enabled():
                lines.append("Profiles are off (self.profiles).")
            lines.append("A profile is a few sentences she writes from someone's facts (3 or more), and it's in her "
                         "prompt whenever she talks to them. /profile <name> (or me) reads one; /profile rebuild, "
                         "/profile forget <name>.")
            ui.add_message("system", "\n".join(lines))
        return True

    if text == "/conclusions" or text.startswith("/conclusions "):
        ui.add_message("system", _conclusions(text[len("/conclusions"):].strip()))
        return True

    if text == "/episodes" or text.startswith("/episodes "):
        from mind import notebook

        words = text.split()

        if len(words) == 3 and words[1] == "forget" and words[2].isdigit():
            ok = _id(words[2]) is not None and notebook.delete_episode(_id(words[2]))
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


def _conclusions(word):
    """/conclusions [name|me | why <n> | wrong <n> | restore <n>]"""
    from mind import conclusions

    verb, _, rest = word.partition(" ")
    verb = verb.lower()
    if verb in ("why", "wrong", "restore"):
        if not rest.strip().lstrip("#").isdigit():
            return f"/conclusions {verb} <number> - the numbers are in /conclusions <name>."
        cid = int(rest.strip().lstrip("#"))
        found = conclusions.get(cid)
        if not found:
            return f"No conclusion #{cid}."
        if verb == "wrong":
            return (f"Set aside: {found['text']}\n(she won't conclude it again; /conclusions restore {cid} undoes it)"
                    if conclusions.mark_wrong(cid) else f"#{cid} is already marked wrong.")
        if verb == "restore":
            return f"Back: {found['text']}" if conclusions.restore(cid) else f"#{cid} wasn't set aside."
        lines = [f"#{cid} ({found['kind']}, {found['created'][:10]}): {found['text']}"]
        if found["retired"]:
            lines.append(f"  set aside {found['retired'][:10]}: {found['why']}")
        behind = conclusions.sources_text(cid, reflect._transcript())
        for at, said, answered in behind:
            lines.append(f"  {at[:16].replace('T', ' ')}  {conclusions.label(found['person'])}: {conclusions._short(said, 160)}")
            lines.append(f"  {' ' * 16}  her: {conclusions._short(answered, 120)}")
        if len(behind) < len(found["sources"]):
            lines.append(f"  ({len(found['sources']) - len(behind)} of the exchanges it came from aren't in the "
                         "transcript any more)")
        return "\n".join(lines)
    if word:
        person = conclusions.find_person(word)
        if person is None:
            return f"No conclusions about {word}. /conclusions lists who she has some for."
        if not conclusions.rows(person, limit=1) and not conclusions.rows(person, retired=True, limit=1):
            return f"No conclusions about {conclusions.label(person)} yet."
        lines = [f"#{r['id']} {'said    ' if r['kind'] == 'said' else 'inferred'} {r['created'][5:10]}  {r['text']}"
                 + (f"  (from {len(r['sources'])}, seen again {r['backed'][5:10]})" if r["backed"] else "")
                 for r in conclusions.rows(person)]
        old = conclusions.rows(person, retired=True, limit=10)
        if old:
            lines.append("Set aside:")
            lines += [f"#{r['id']} {r['text']}  ({r['why']})" for r in old]
        lines.append("/conclusions why <n> shows the conversation it came from; wrong <n> sets one aside.")
        return "\n".join(lines)
    have = conclusions.counts()
    lines = [f"{conclusions.label(p)}: {n} - newest: {conclusions.rows(p, limit=1)[0]['text']}"
             for p, n in have.items()] or ["No conclusions yet."]
    if not conclusions.enabled():
        lines.append("Conclusions are off (self.conclusions).")
    lines.append("While she's idle she reads back her conversations, one person at a time, and notes what she "
                 "concludes about them: said (you told her) or inferred (her read). /conclusions <name> (or me) "
                 "lists them; why <n>, wrong <n>, restore <n>.")
    return "\n".join(lines)
