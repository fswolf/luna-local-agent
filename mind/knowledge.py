"""Her knowledge base: your notes, manuals, PDFs and docs, searchable.

    > "What port did I put Jellyfin on?"
    > "What does the boss in chapter 3 do?"
    > "How do I reset the router again?"

Point it at folders (knowledge.folders, default agent/knowledge) and
she reads everything in them in the background: Markdown, text, code
and config files, PDFs, Word documents, web pages saved to disk. Each
file is cut into passages of a paragraph or so, and each passage gets
an embedding from the same local embedding model fact recall uses.

Two ways it reaches her:

  * search_docs, a tool: she looks something up on purpose and says
    which file the answer came from.
  * automatically: when a passage matches what you just said closely
    enough (knowledge.min_score), the best one or two travel with the
    turn, the same way remembered facts do. Your own turns only.

Without the embedding server it still works, by matching words (BM25):
search_docs keeps going, the automatic part waits until it's back.

While she's idle she also writes a sentence or two per file saying what
it covers (knowledge.summaries). A file with a "Summary: ..." line near
its top, and a folder's own index file (00-index.md, index.md,
README.md), speak for themselves, in their own words, no model call.
They never ride in her prompt: search_docs can list them (browse: what's
in the folder, or in one folder of it), and the search leans a little
towards passages from files whose summary fits the question.

The index is a cache, rebuilt from the files whenever they change:
~/.cache/ai-voice/knowledge.db (%LOCALAPPDATA%\\ai-voice on Windows).
Nothing is uploaded anywhere, and the file deny list applies: keys,
credentials and the like are skipped even if they're in a folder you
pointed it at.
"""
import math
import os
import re
import shutil
import sqlite3
import subprocess
import sys
import threading
import time
import zipfile

from array import array
from collections import Counter

import config
from core import logbook
from core import safe

TEXT_EXT = {".md", ".markdown", ".txt", ".rst", ".org", ".adoc", ".tex", ".csv", ".tsv",
            ".json", ".yaml", ".yml", ".toml", ".ini", ".conf", ".cfg",
            ".py", ".js", ".ts", ".lua", ".sh", ".bash", ".php", ".go", ".rs", ".c", ".h",
            ".cpp", ".java", ".cs", ".rb", ".sql", ".xml", ".nix", ".log"}
HTML_EXT = {".html", ".htm"}
SKIP_DIRS = {".git", "node_modules", "__pycache__", "venv", ".venv", "dist", "build",
             ".cache", ".idea", ".vscode", "target"}
MAX_TEXT_BYTES = 2_000_000
MAX_DOC_BYTES = 40_000_000
MAX_FILES = 20000
CHUNK_CHARS = 900

_lock = threading.Lock()
_state = {"files": 0, "chunks": 0, "embedded": 0, "indexed_at": 0.0, "busy": False,
          "skipped": [], "error": "", "cache": None, "cache_at": -1.0, "changed": 0.0}
_wake = threading.Event()


# ---------------------------------------------------------------------------
# Settings and storage
# ---------------------------------------------------------------------------
def enabled():
    return bool(getattr(config, "KNOWLEDGE_ENABLED", True))


def resolve(folder):
    """A folder as written (~/notes, agent/knowledge) -> its full path. A
    relative one is inside Luna's folder, wherever Luna was started from."""
    path = os.path.expanduser(str(folder))
    return os.path.realpath(path if os.path.isabs(path) else os.path.join(config.BASE_DIR, path))


def folders():
    out = []

    for f in getattr(config, "KNOWLEDGE_FOLDERS", [config.KNOWLEDGE_DEFAULT]) or []:
        path = resolve(f)

        if path not in out:
            out.append(path)

    return out


def db_path():
    base = (os.environ.get("LOCALAPPDATA") if sys.platform == "win32" else
            os.environ.get("XDG_CACHE_HOME")) or os.path.join(os.path.expanduser("~"), ".cache")

    return os.path.join(base, "ai-voice", "knowledge.db")


def _db():
    os.makedirs(os.path.dirname(db_path()), exist_ok=True)
    conn = sqlite3.connect(db_path(), timeout=10)
    conn.execute("CREATE TABLE IF NOT EXISTS files (path TEXT PRIMARY KEY, mtime REAL, size INTEGER, chunks INTEGER)")
    conn.execute("CREATE TABLE IF NOT EXISTS chunks (id INTEGER PRIMARY KEY, path TEXT, heading TEXT, "
                 "text TEXT, model TEXT, vec BLOB)")
    conn.execute("CREATE INDEX IF NOT EXISTS chunks_path ON chunks(path)")
    conn.execute("CREATE TABLE IF NOT EXISTS summaries (path TEXT PRIMARY KEY, mtime REAL, size INTEGER, "
                 "text TEXT, how TEXT, model TEXT, vec BLOB)")

    return conn


def _display(path):
    home = os.path.expanduser("~")

    return "~" + path[len(home):] if path.startswith(home + os.sep) else path


# ---------------------------------------------------------------------------
# Reading files
# ---------------------------------------------------------------------------
def _denied(path):
    """The file deny list (tools/files.py), so a key or a credentials file
    in a knowledge folder is never read into her prompt."""
    try:
        from tools import files

        name = os.path.basename(path).lower()

        if name in files._DENY_FILES or name.endswith(files._DENY_SUFFIXES) or files._DENY_NAMES.search(name):
            return True

        home = os.path.expanduser("~")

        if path.startswith(home + os.sep):
            files.resolve(path)
    except Exception as e:
        return type(e).__name__ == "Refused"

    return False


def _read_pdf(path):
    try:
        import pypdf

        reader = pypdf.PdfReader(path)

        return "\n\n".join((page.extract_text() or "") for page in reader.pages)
    except ImportError:
        pass

    tool = shutil.which("pdftotext")

    if not tool:
        raise ValueError("PDFs need pypdf (pip install pypdf) or pdftotext (poppler-utils)")

    done = subprocess.run([tool, "-layout", path, "-"], capture_output=True, timeout=60)

    return done.stdout.decode("utf-8", "replace")


def _read_docx(path):
    with zipfile.ZipFile(path) as z:
        xml = z.read("word/document.xml").decode("utf-8", "replace")

    xml = re.sub(r"</w:p>", "\n\n", xml)
    xml = re.sub(r"<w:tab/>", "\t", xml)
    text = re.sub(r"<[^>]+>", "", xml)

    import html

    return html.unescape(text)


def _read_html(raw):
    try:
        from mind import webpage

        parser = webpage._Extractor()
        parser.feed(raw)

        return parser.text()
    except Exception:
        return re.sub(r"<[^>]+>", " ", raw)


def read_text(path):
    """The file as plain text, or raise ValueError saying why not."""
    ext = os.path.splitext(path)[1].lower()
    size = os.path.getsize(path)

    if ext == ".pdf":
        if size > MAX_DOC_BYTES:
            raise ValueError("too big")
        return _read_pdf(path)

    if ext == ".docx":
        if size > MAX_DOC_BYTES:
            raise ValueError("too big")
        return _read_docx(path)

    if size > MAX_TEXT_BYTES:
        raise ValueError("too big")

    with open(path, "rb") as f:
        data = f.read()

    if b"\x00" in data[:8192]:
        raise ValueError("binary")

    text = data.decode("utf-8", "replace")

    return _read_html(text) if ext in HTML_EXT else text


def _wanted(name):
    low = name.lower()
    ext = os.path.splitext(low)[1]

    return ext in TEXT_EXT or ext in HTML_EXT or ext in (".pdf", ".docx") or low in ("readme", "notes", "todo")


def _walk():
    """Every file in the knowledge folders worth reading."""
    for root in folders():
        if not os.path.isdir(root):
            continue

        for here, dirs, names in os.walk(root):
            dirs[:] = [d for d in dirs if d not in SKIP_DIRS and not d.startswith(".")]

            for name in names:
                if name.startswith(".") or not _wanted(name):
                    continue

                yield os.path.join(here, name)


# ---------------------------------------------------------------------------
# A game's guide: what <knowledge folder>/<game>/ says about one place
# ---------------------------------------------------------------------------
# For game turns, which don't get search_docs: the lines about the room
# she's standing in, found by name, no index or embedding server needed.
# A file that says "Spoilers: yes" near its top is never used this way.
_SPOILERS = re.compile(r"^\s*spoilers?\s*:\s*yes\b", re.IGNORECASE | re.MULTILINE)
GUIDE_CHARS = 700


def _spoilers(path):
    """Does this file say "Spoilers: yes" near its top?"""
    try:
        with open(path, encoding="utf-8", errors="replace") as f:
            return bool(_SPOILERS.search(f.read(800)))
    except OSError:
        return False


def _guide_dirs(folder):
    """<knowledge folder>/<folder> for each knowledge folder that has one, or
    one level down (<knowledge folder>/games/<folder>), for guides kept
    together in a folder of their own. Only a plain folder name: nothing
    outside the knowledge folders."""
    folder = str(folder or "").strip()

    if not folder or os.sep in folder or "/" in folder or folder.startswith("."):
        return []

    out = []
    for root in folders():
        here = os.path.join(root, folder)
        if os.path.isdir(here):
            out.append(here)
            continue
        try:
            groups = sorted(d for d in os.listdir(root)
                            if not d.startswith(".") and d not in SKIP_DIRS and os.path.isdir(os.path.join(root, d)))
        except OSError:
            continue
        out += [os.path.join(root, g, folder) for g in groups if os.path.isdir(os.path.join(root, g, folder))]
    return out


def _about_in(text, name):
    """A section headed with the name, or list items that start with it:
    "## Cloud Nine Nest" (and what's under it), "- Troll Room: ...",
    "- Living Room (trophy case, ...): ..."."""
    lines, out, n = text.splitlines(), [], re.escape(name)
    head = re.compile(rf"^\s{{0,3}}(#{{1,6}})\s+{n}\s*#*\s*$", re.IGNORECASE)
    item = re.compile(rf"^\s*[-*]\s+(?:\*\*)?{n}(?:\*\*)?(?=\s*[(:]|\s*$)", re.IGNORECASE)

    for i, line in enumerate(lines):
        m = head.match(line)
        if m:
            body = []
            for nxt in lines[i + 1:]:
                h = _HEADING.match(nxt)
                if h and len(h.group(1)) <= len(m.group(1)):
                    break
                if nxt.strip():
                    body.append(nxt.strip())
            out.append("\n".join(body))
        elif item.match(line):
            out.append(re.sub(r"^\s*[-*]\s+", "", line).strip())

    return [o for o in out if o]


def about(folder, name, limit=GUIDE_CHARS):
    """What the notes in <knowledge folder>/<folder>/ say about name, or "".
    Spoiler files are skipped."""
    name = " ".join(str(name or "").split())

    if not name:
        return ""

    found = []

    for base in _guide_dirs(folder):
        for file in sorted(os.listdir(base)):
            if os.path.splitext(file)[1].lower() not in (".md", ".markdown", ".txt"):
                continue

            try:
                with open(os.path.join(base, file), encoding="utf-8", errors="replace") as f:
                    text = f.read(MAX_TEXT_BYTES)
            except OSError:
                continue

            if not _SPOILERS.search(text[:800]):
                found += _about_in(text, name)

    out = "\n".join(dict.fromkeys(found))
    return out if len(out) <= limit else out[:limit - 1].rstrip() + "…"


def guide(folder, query, limit=2, chars=600):
    """The passages in <knowledge folder>/<folder>/ that best match query,
    for a game turn that has no room to look up by name (Vibe City: what
    she's trying to do). By meaning when the embedding server is up, else
    by words. Spoiler files are skipped. "" when there's nothing."""
    dirs = _guide_dirs(folder)

    if not dirs or not enabled() or not str(query or "").strip():
        return ""

    try:
        found, _how = search(query, limit=limit, within=dirs)
    except Exception as e:
        logbook.warn("knowledge", "guide search failed: %s", e)
        return ""

    return "\n".join(f"[{i['heading'] or os.path.basename(i['path'])}]\n"
                     + (i["text"] if len(i["text"]) <= chars else i["text"][:chars - 1].rstrip() + "…")
                     for _s, i in found)


# ---------------------------------------------------------------------------
# Cutting into passages
# ---------------------------------------------------------------------------
_HEADING = re.compile(r"^\s{0,3}(#{1,6})\s+(.+?)\s*#*\s*$")


def chunks(text):
    """[(heading, passage)]: paragraphs gathered to about CHUNK_CHARS,
    each tagged with the Markdown heading it sits under."""
    out, heading, buf = [], "", ""

    def flush():
        nonlocal buf
        piece = buf.strip()

        if len(piece) > 20:
            out.append((heading, piece))

        buf = ""

    for para in re.split(r"\n\s*\n", text.replace("\r\n", "\n")):
        lines = para.strip("\n").split("\n")
        m = _HEADING.match(lines[0]) if lines else None

        if m:
            flush()
            heading = m.group(2).strip()[:120]
            para = "\n".join(lines[1:])

            if not para.strip():
                continue

        para = para.strip()

        while len(para) > CHUNK_CHARS * 1.5:            # one huge paragraph: cut at a sentence or a line
            cut = max(para.rfind(". ", 0, CHUNK_CHARS), para.rfind("\n", 0, CHUNK_CHARS))
            cut = cut + 1 if cut > CHUNK_CHARS // 3 else CHUNK_CHARS
            flush()
            buf = para[:cut]
            flush()
            para = para[cut:].strip()

        if buf and len(buf) + len(para) > CHUNK_CHARS:
            flush()

        buf = (buf + "\n\n" + para) if buf else para

    flush()

    return out


# ---------------------------------------------------------------------------
# Embeddings (the same local server fact recall uses)
# ---------------------------------------------------------------------------
def _embedder():
    try:
        from mind import embedmem

        return embedmem if embedmem.available() else None
    except Exception:
        return None


def _model():
    try:
        from mind import embedmem

        return embedmem._state.get("model") or "embed"
    except Exception:
        return ""


def _embed(texts, timeout=60):
    import requests

    response = requests.post(config.EMBED_URL, headers=config.EMBED_HEADERS,
                             json={"input": texts, "model": _model()}, timeout=timeout)
    response.raise_for_status()

    return [d["embedding"] for d in sorted(response.json()["data"], key=lambda d: d["index"])]


def _query_prefix():
    # Qwen3-Embedding wants an instruction on the query side; a model
    # configured without one (embed_query_prefix "") gets none here either.
    if not getattr(config, "EMBED_QUERY_PREFIX", ""):
        return ""

    return ("Instruct: Given a question, retrieve passages from the user's own notes "
            "and documents that answer it\nQuery: ")


def _doc_text(path, heading, text):
    """What gets embedded: where it's from, then the passage."""
    return f"{os.path.basename(path)}{' > ' + heading if heading else ''}\n{text}"


# ---------------------------------------------------------------------------
# Indexing
# ---------------------------------------------------------------------------
def index(force=False):
    """Bring the index up to date with the folders. Returns a summary."""
    if _state["busy"]:
        return "already indexing"

    _state.update(busy=True, error="")
    added = removed = failed = 0
    skipped = []

    try:
        conn = _db()

        try:
            known = {p: (m, s) for p, m, s in conn.execute("SELECT path, mtime, size FROM files")}
            seen = set()

            for n, path in enumerate(_walk()):
                if n >= MAX_FILES:
                    skipped.append(f"stopped at {MAX_FILES} files")
                    break

                seen.add(path)

                try:
                    st = os.stat(path)
                except OSError:
                    continue

                if not force and known.get(path) == (st.st_mtime, st.st_size):
                    continue

                if _denied(path):
                    skipped.append(f"{_display(path)}: on the deny list")
                    conn.execute("DELETE FROM chunks WHERE path=?", (path,))
                    conn.execute("DELETE FROM files WHERE path=?", (path,))
                    conn.execute("DELETE FROM summaries WHERE path=?", (path,))
                    continue

                try:
                    pieces = chunks(read_text(path))
                except Exception as e:
                    failed += 1
                    skipped.append(f"{_display(path)}: {e}")
                    pieces = []

                conn.execute("DELETE FROM chunks WHERE path=?", (path,))
                conn.executemany("INSERT INTO chunks (path, heading, text, model, vec) VALUES (?,?,?,NULL,NULL)",
                                 [(path, h, t) for h, t in pieces])
                conn.execute("INSERT OR REPLACE INTO files VALUES (?,?,?,?)",
                             (path, st.st_mtime, st.st_size, len(pieces)))
                conn.commit()
                added += 1

            for path in set(known) - seen:
                conn.execute("DELETE FROM chunks WHERE path=?", (path,))
                conn.execute("DELETE FROM files WHERE path=?", (path,))
                conn.execute("DELETE FROM summaries WHERE path=?", (path,))
                removed += 1

            conn.commit()
        finally:
            conn.close()

        embedded = _embed_missing()
        _count()
        _state.update(indexed_at=time.time(), skipped=skipped[-30:], changed=time.time())
        summary = (f"{_state['files']} files, {_state['chunks']} passages"
                   + (f" ({added} new or changed, {removed} gone)" if added or removed else "")
                   + (f", {embedded} embedded" if embedded else "")
                   + (f", {failed} couldn't be read" if failed else ""))

        if added or removed or embedded:
            logbook.info("knowledge", "index: %s", summary)

        return summary
    except Exception as e:
        _state["error"] = str(e)
        logbook.warn("knowledge", "indexing failed: %s", e)
        return f"indexing failed: {e}"
    finally:
        _state["busy"] = False


def _embed_missing(batch=16):
    """Embed passages that don't have a vector from the current model."""
    if _embedder() is None:
        return 0

    model, done = _model(), 0
    conn = _db()

    try:
        rows = conn.execute("SELECT id, path, heading, text FROM chunks WHERE vec IS NULL OR model != ?",
                            (model,)).fetchall()

        for start in range(0, len(rows), batch):
            part = rows[start:start + batch]

            try:
                vecs = _embed([_doc_text(p, h, t)[:2000] for _i, p, h, t in part])
            except Exception as e:
                logbook.warn("knowledge", "embedding stopped after %d: %s", done, e)
                break

            conn.executemany("UPDATE chunks SET vec=?, model=? WHERE id=?",
                             [(array("f", v).tobytes(), model, row[0]) for row, v in zip(part, vecs)])
            conn.commit()
            done += len(part)
    finally:
        conn.close()

    done += _embed_summaries()

    if done:
        _state["changed"] = time.time()

    return done


def _embed_summaries():
    """Vectors for summaries written while the embedding server was away."""
    if _embedder() is None:
        return 0

    model, done = _model(), 0
    conn = _db()

    try:
        rows = conn.execute("SELECT path, text FROM summaries WHERE vec IS NULL OR model != ?", (model,)).fetchall()

        for start in range(0, len(rows), 16):
            part = rows[start:start + 16]
            try:
                vecs = _embed([f"{os.path.basename(p)}\n{s}"[:2000] for p, s in part])
            except Exception as e:
                logbook.warn("knowledge", "embedding summaries stopped: %s", e)
                break
            conn.executemany("UPDATE summaries SET vec=?, model=? WHERE path=?",
                             [(array("f", v).tobytes(), model, row[0]) for row, v in zip(part, vecs)])
            conn.commit()
            done += len(part)
    finally:
        conn.close()

    return done


# ---------------------------------------------------------------------------
# What each file covers (written while she's idle; mind/reflect.py)
# ---------------------------------------------------------------------------
SUMMARIES_PER_PASS = 8
SUMMARY_CHARS = 320
SUMMARY_SOURCE_CHARS = 3000
INDEX_NAMES = ("00-index", "index", "readme")


def summaries_enabled():
    return enabled() and bool(getattr(config, "KNOWLEDGE_SUMMARIES", True))


def _is_index(path):
    stem, ext = os.path.splitext(os.path.basename(path).lower())
    return stem in INDEX_NAMES and ext in (".md", ".markdown", ".txt", "")


# A header line like "Audience: Luna", "Keywords: ...", "Spoilers: yes"
_META = re.compile(r"^(?:[A-Za-z][\w-]*(?: [\w-]+)?:\s*\S.{0,40}"
                   r"|(?:audience|keywords?|tags|spoilers?|author|date|updated)\s*:.*)$", re.IGNORECASE)
_SUMMARY_LINE = re.compile(r"^\s*(?:summary|about|description)\s*:\s*(\S.*)$", re.IGNORECASE | re.MULTILINE)


def _stated(rows):
    """A "Summary: ..." line near the top of the file, as it was written."""
    head = "\n".join(text for _h, text in rows[:2])[:2000]
    m = _SUMMARY_LINE.search(head)
    return m.group(1).strip() if m else ""


def _own_words(rows):
    """An index file's opening: its first paragraph that isn't a heading or a
    "Key: value" line, as it was written."""
    for _h, text in rows:
        for para in re.split(r"\n\s*\n", text):
            lines = [ln.strip() for ln in para.strip().splitlines()
                     if ln.strip() and not _META.match(ln.strip())]
            words = " ".join(ln.lstrip("-*> ").strip() for ln in lines)
            if len(words) >= 30:
                return words
    return ""


def _short_text(text, n=SUMMARY_CHARS):
    text = " ".join(str(text or "").split())
    if len(text) <= n:
        return text
    cut = text[:n].rsplit(" ", 1)[0]
    return cut.rstrip(",;:") + "…"


def summaries_due():
    """Files in the index with no summary, or one older than the file."""
    if not summaries_enabled():
        return []
    conn = _db()
    try:
        return [p for p, in conn.execute(
            "SELECT f.path FROM files f LEFT JOIN summaries s ON s.path = f.path "
            "WHERE f.chunks > 0 AND (s.path IS NULL OR s.mtime != f.mtime OR s.size != f.size) "
            "ORDER BY f.path").fetchall()]
    finally:
        conn.close()


def _summary_prompt(path, rows):
    heads = list(dict.fromkeys(h for h, _t in rows if h))[:25]
    text, used = [], 0
    for _h, body in rows:
        if used >= SUMMARY_SOURCE_CHARS:
            break
        part = body[:SUMMARY_SOURCE_CHARS - used]
        text.append(part)
        used += len(part)
    spoilers = bool(_SPOILERS.search("\n".join(text)[:800]))
    return (f"This is from a file in the user's own documents: {os.path.basename(path)}\n"
            + (f"Its headings: {'; '.join(heads)}\n" if heads else "")
            + "Its start:\n---\n" + "\n\n".join(text) + "\n---\n"
            "In one or two plain sentences (under 40 words), say what this file covers, so "
            "someone could tell whether it answers their question. Name the subjects; skip "
            "praise and preamble"
            + (", and don't give away the solutions it says are spoilers" if spoilers else "")
            + ". Only the sentences.")


def write_summaries(ask, yield_=lambda: None, report=None, limit=SUMMARIES_PER_PASS):
    """Write the summaries that are missing or stale, a few a pass. ask(prompt)
    -> text. yield_() raises to stop when a turn starts. Returns the files
    written, or None when a model call failed (the server's down)."""
    written = []
    for path in summaries_due()[:limit]:
        conn = _db()
        try:
            row = conn.execute("SELECT mtime, size FROM files WHERE path=?", (path,)).fetchone()
            rows = conn.execute("SELECT heading, text FROM chunks WHERE path=? ORDER BY id", (path,)).fetchall()
        finally:
            conn.close()
        if not row or not rows:
            continue
        how = "model"
        text = _stated(rows) or (_own_words(rows) if _is_index(path) else "")
        if text:
            how = "own words"
        else:
            yield_()
            try:
                text = ask(_summary_prompt(path, rows))
            except Exception as e:
                logbook.warn("knowledge", "summary of %s failed: %s", _display(path), e)
                return None             # the ones written stay; the rest after a rest
        text = _short_text(re.sub(r"^(summary|this file)\s*:\s*", "", str(text or "").strip(), flags=re.I))
        if len(text) < 10:
            text = "(couldn't say what this covers)"
        conn = _db()
        try:
            conn.execute("INSERT OR REPLACE INTO summaries (path, mtime, size, text, how, model, vec) "
                         "VALUES (?,?,?,?,?,NULL,NULL)", (path, row[0], row[1], text, how))
            conn.commit()
        finally:
            conn.close()
        written.append(path)
    if written:
        _embed_summaries()
        _state["changed"] = time.time()
        if report:
            report(f"Knowledge: wrote what {len(written)} file(s) cover")
    return written


def summaries():
    """{path: text} for every file that has one."""
    conn = _db()
    try:
        return dict(conn.execute("SELECT path, text FROM summaries").fetchall())
    finally:
        conn.close()


def browse(folder=""):
    """What's in the knowledge folders, with what each covers: its folders
    (each with its index file's words, or its first files') and its loose
    files. folder: a folder inside them ("games", "games/zork") for the same
    view of that one."""
    have = summaries()
    conn = _db()
    try:
        paths = [p for p, in conn.execute("SELECT path FROM files WHERE chunks > 0 ORDER BY path").fetchall()]
    finally:
        conn.close()
    if not paths:
        return "The knowledge folder is empty."
    roots = folders()

    def rel(p):
        for r in roots:
            if p.startswith(r + os.sep):
                return os.path.relpath(p, r).replace(os.sep, "/")
        return _display(p)

    want = "/".join(x for x in str(folder or "").strip().replace("\\", "/").split("/") if x and x != "..").lower()
    prefix = want + "/" if want else ""
    inside = [(rel(p)[len(prefix):], p) for p in paths if rel(p).lower().startswith(prefix)]
    if not inside:
        names = sorted({rel(p).rsplit("/", 1)[0] for p in paths if "/" in rel(p)})
        return f"No folder {folder!r} in the knowledge folder. Folders: {', '.join(names) or 'none'}."

    groups, loose = {}, []
    for r, p in inside:
        if "/" in r:
            groups.setdefault(r.split("/", 1)[0], []).append(p)
        else:
            loose.append(p)

    where = f"{folder}" if want else "The knowledge folder"
    lines = [f"{where} ({len(inside)} file{'s' if len(inside) != 1 else ''}; browse a folder by name for more):"]
    for name, files in sorted(groups.items()):
        index = next((p for p in files if _is_index(p) and p in have
                      and rel(p).count("/") == (prefix + name).count("/") + 1), None)
        subs = sorted({rel(p)[len(prefix + name) + 1:].split("/", 1)[0] for p in files
                       if "/" in rel(p)[len(prefix + name) + 1:]})
        if index:
            about = have[index]
        elif subs:                      # a folder of folders (games/zork, games/minecraft...)
            about = "folders: " + ", ".join(subs[:20]) + (f" and {len(subs) - 20} more" if len(subs) > 20 else "")
        else:
            about = "; ".join(dict.fromkeys(_short_text(have[p], 90) for p in files[:3] if p in have)) \
                or "(not summarised yet)"
        lines.append(f"- {prefix}{name}/ ({len(files)} file{'s' if len(files) != 1 else ''}): {about}")
    lines += [f"- {rel(p)}: {have.get(p, '(not summarised yet)')}" for p in loose]
    return _cap("\n".join(lines))


def _cap(text, n=4000):
    return text if len(text) <= n else text[:n].rsplit("\n", 1)[0] + "\n(more: browse one folder)"


def _summary_vecs():
    """{path: vector} for the summaries embedded with the current model."""
    model = _model()
    conn = _db()
    try:
        rows = conn.execute("SELECT path, model, vec FROM summaries WHERE vec IS NOT NULL").fetchall()
    finally:
        conn.close()
    return {p: array("f", v) for p, m, v in rows if m == model}


def _count():
    conn = _db()

    try:
        _state["files"] = conn.execute("SELECT COUNT(*) FROM files").fetchone()[0]
        _state["chunks"] = conn.execute("SELECT COUNT(*) FROM chunks").fetchone()[0]
        _state["embedded"] = conn.execute("SELECT COUNT(*) FROM chunks WHERE vec IS NOT NULL AND model=?",
                                          (_model(),)).fetchone()[0]
    finally:
        conn.close()


def _watch():
    while True:
        # Guarded and clamped: this thread used to die with a traceback on
        # screen when anything here raised, and wait() overflows on a
        # hand-edited 1e999. A minute between tries, so a failure can't spin.
        try:
            if enabled():
                index()
        except Exception:
            logbook.exception("knowledge", "rescan failed")

        minutes = safe.number(getattr(config, "KNOWLEDGE_RESCAN_MINUTES", 10), 10, lo=1, hi=24 * 60)
        _wake.wait(minutes * 60)
        _wake.clear()


def start():
    """Create the default folder if it's the only one, then index in the
    background and keep rescanning."""
    for path in folders():
        if path == os.path.realpath(config.KNOWLEDGE_DEFAULT) and not os.path.exists(path):
            try:
                os.makedirs(path, exist_ok=True)
                with open(os.path.join(path, "README.md"), "w", encoding="utf-8") as f:
                    f.write("# Luna's knowledge\n\nPut notes, manuals, PDFs and docs in this folder "
                            "and Luna can look things up in them.\n\nShe re-reads it every few minutes; "
                            "/knowledge shows what she's found.\n")
            except OSError:
                pass

    threading.Thread(target=_watch, daemon=True, name="knowledge").start()


def reindex():
    """Ask the background indexer to look again now."""
    _wake.set()


# ---------------------------------------------------------------------------
# Searching
# ---------------------------------------------------------------------------
_WORD = re.compile(r"[a-z0-9]+")


def _load():
    """Every passage (and vector, when there is one), cached until the index changes."""
    with _lock:
        if _state["cache"] is not None and _state["cache_at"] >= _state["changed"]:
            return _state["cache"]

        conn = _db()

        try:
            model = _model()
            rows = conn.execute("SELECT path, heading, text, model, vec FROM chunks").fetchall()
        finally:
            conn.close()

        items = [{"path": p, "heading": h or "", "text": t,
                  "vec": array("f", v) if v is not None and m == model else None} for p, h, t, m, v in rows]
        _state.update(cache=items, cache_at=time.time())

        return items


def _bm25(query, items):
    q = set(_WORD.findall(query.lower()))
    docs = [Counter(_WORD.findall((i["heading"] + " " + i["text"] + " " + os.path.basename(i["path"])).lower()))
            for i in items]
    n = len(docs) or 1
    avg = sum(sum(d.values()) for d in docs) / n or 1
    df = Counter(w for d in docs for w in q if w in d)
    out = []

    for d in docs:
        length = sum(d.values())
        s = 0.0

        for w in q:
            if w in d:
                idf = math.log(1 + (n - df[w] + 0.5) / (df[w] + 0.5))
                s += idf * d[w] * 2.2 / (d[w] + 1.2 * (0.25 + 0.75 * length / avg))

        out.append(s)

    return out


def _cosines(qv, vecs):
    try:
        import numpy as np

        m = np.array([list(v) for v in vecs], dtype=np.float32) if vecs else None

        if m is None:
            return []

        return list(m @ np.asarray(qv, dtype=np.float32))
    except ImportError:
        return [sum(a * b for a, b in zip(qv, v)) for v in vecs]


def search(query, limit=5, within=None):
    """([(score, item)], how) best first. how is 'by meaning', 'by meaning,
    reranked' or 'by words'. within: only these folders (a game's guide),
    and none of their spoiler files."""
    query = " ".join(str(query or "").split())[:500]
    items = _load()

    if within:
        roots = tuple(os.path.realpath(d) + os.sep for d in within)
        items = [i for i in items if os.path.realpath(i["path"]).startswith(roots)]
        items = [i for i in items if not _spoilers(i["path"])]

    if not query or not items:
        return [], ""

    with_vec = [i for i in items if i["vec"] is not None]
    embedder = _embedder() if with_vec else None

    if embedder is not None:
        try:
            qv = _embed([_query_prefix() + query], timeout=5)[0]
            scores = _cosines(qv, [i["vec"] for i in with_vec])
            # a small lift for passages from files whose summary fits the
            # question: the right file's weaker passages reach the reranker
            lift = _summary_lift(qv)
            if lift:
                scores = [s + lift.get(i["path"], 0.0) for s, i in zip(scores, with_vec)]
            scored = sorted(zip(scores, with_vec), key=lambda p: p[0], reverse=True)
            how = "by meaning"
            top = scored[:max(limit, safe.whole(getattr(config, "RERANK_CANDIDATES", 24), 24, lo=1, hi=1000))]
            better = embedder.rerank(query, [_doc_text(i["path"], i["heading"], i["text"]) for _s, i in top])

            if better is not None:
                order = {t: n for n, t in enumerate(better)}
                top.sort(key=lambda p: order.get(_doc_text(p[1]["path"], p[1]["heading"], p[1]["text"]), 1e9))
                how = "by meaning, reranked"

            return [(float(s), i) for s, i in top[:limit]], how
        except Exception as e:
            logbook.warn("knowledge", "meaning search failed, matching words: %s", e)

    scored = sorted(zip(_bm25(query, items), items), key=lambda p: p[0], reverse=True)

    return [(s, i) for s, i in scored[:limit] if s > 0], "by words"


SUMMARY_LIFT = 0.15


def _summary_lift(qv):
    """{path: bonus}: SUMMARY_LIFT times how well each file's summary fits."""
    try:
        vecs = _summary_vecs()
    except Exception:
        return {}
    if not vecs:
        return {}
    paths = list(vecs)
    return {p: SUMMARY_LIFT * max(0.0, float(s)) for p, s in zip(paths, _cosines(qv, [vecs[p] for p in paths]))}


def _where(item):
    return _display(item["path"]) + (f" > {item['heading']}" if item["heading"] else "")


def prompt_block(query):
    """Passages that match what you just said closely enough to travel
    with the turn unasked. '' when nothing does, or when it's off."""
    if not (enabled() and getattr(config, "KNOWLEDGE_AUTO", True)) or not str(query or "").strip():
        return ""

    if _embedder() is None or not _state["embedded"]:
        return ""                     # words alone aren't sure enough to bring something in unasked

    try:
        found, how = search(query, limit=safe.whole(getattr(config, "KNOWLEDGE_AUTO_PASSAGES", 2), 2, lo=0, hi=20))
    except Exception as e:
        logbook.warn("knowledge", "auto search failed: %s", e)
        return ""

    floor = float(getattr(config, "KNOWLEDGE_MIN_SCORE", 0.55))
    keep = [(s, i) for s, i in found if s >= floor]

    if not keep:
        return ""

    logbook.info("knowledge", "brought %d passage(s) into the turn (best %.2f, %s)",
                 len(keep), keep[0][0], how)

    return ("\nFrom the user's own notes and documents (use them if they answer what "
            f"{config.USER} asked, say which file; search_docs finds more):\n"
            + "\n".join(f"[{_where(i)}]\n{i['text'][:900]}" for _s, i in keep) + "\n")


def status():
    lines = [f"Knowledge: {'on' if enabled() else 'off'} - {_state['files']} files, "
             f"{_state['chunks']} passages, {_state['embedded']} embedded"
             + (" (indexing now)" if _state["busy"] else "")]

    for f in folders():
        lines.append(f"  {_display(f)}{'' if os.path.isdir(f) else '  (missing)'}")

    if summaries_enabled():
        try:
            n = len(summaries())
            lines.append(f"  what each file covers: {n} of {_state['files']} written"
                         + ("" if n >= _state["files"] else " (more while she's idle)"))
        except Exception:
            pass

    lines.append("  search: " + ("by meaning" if _embedder() else "by words (embedding server not answering)")
                 + "; automatic: " + ("on" if getattr(config, "KNOWLEDGE_AUTO", True) else "off"))

    if _state["indexed_at"]:
        lines.append(f"  last checked {time.strftime('%H:%M', time.localtime(_state['indexed_at']))}"
                     f", index at {_display(db_path())}")

    if _state["error"]:
        lines.append(f"  last error: {_state['error']}")

    for s in _state["skipped"][-5:]:
        lines.append(f"  skipped {s}")

    lines.append("  /knowledge reindex | add <folder> | remove <folder> | search <words>")

    return "\n".join(lines)


def set_folders(new):
    value, _live = config.save_setting("knowledge.folders", list(new))
    config.KNOWLEDGE_FOLDERS = list(value)
    reindex()


# ---------------------------------------------------------------------------
# The tool
# ---------------------------------------------------------------------------
def _register():
    import tools

    def run(query="", limit=5, browse=False, folder=""):
        if not enabled():
            return "The knowledge base is off."

        if browse or folder or not str(query or "").strip():
            return globals()["browse"](folder)

        try:
            limit = safe.whole(limit or 5, 5, lo=1, hi=10)
        except (TypeError, ValueError):
            limit = 5

        found, how = search(query, limit)

        if not found:
            return (f"Nothing in the user's documents matches {query!r}. Say so - don't "
                    "guess - and offer web_search if it's something public.")

        return "\n\n".join(
            [f"From the user's own documents, {how} (cite the file):"]
            + [f"[{n}] {_where(i)}\n{i['text'][:1200]}" for n, (_s, i) in enumerate(found, 1)])

    tools.register_external(
        "search_docs",
        "Search the user's own notes, manuals, PDFs and docs (their knowledge folder). Use it "
        "for anything about their setup, projects, devices or things they've written down - "
        "ports, configs, game design, how-tos - before saying you don't know. "
        "Say which file the answer came from. browse: true shows what's in it.",
        {"query": {"type": "string", "description": "What to look for, in plain words."},
         "limit": {"type": "integer", "description": "How many passages, default 5."},
         "browse": {"type": "boolean", "description": "true lists what's in the folder and what "
                    "each part covers, instead of searching."},
         "folder": {"type": "string", "description": "With browse: one folder's files."}},
        required=(), run=run, group="Knowledge",
        available=lambda: enabled() and _state["chunks"] > 0,
        why=lambda: "the knowledge base is off" if not enabled() else
        "nothing indexed yet - put files in " + ", ".join(_display(f) for f in folders()),
    )


_register()
