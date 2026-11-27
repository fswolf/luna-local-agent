import re
from concurrent.futures import ThreadPoolExecutor

import config
from core import logbook

_TRIGGER_PATTERN = re.compile(r"\bweb[\s\-_]*search\b", re.IGNORECASE)

_LEADING_FILLER = re.compile(r"^(for|about|on|up)\b\s*", re.IGNORECASE)
_TRAILING_FILLER = re.compile(r"\b(please|nya|thanks|thank you)\W*$", re.IGNORECASE)


def looks_like_search(text: str) -> bool:
    return bool(config.WEB_SEARCH_ENABLED and _TRIGGER_PATTERN.search(text))


def extract_query(text: str) -> str:
    """Everything after the trigger phrase, lightly cleaned up.

    e.g. "agent please web search current bitcoin price nya" ->
    "current bitcoin price"
    """
    after = _TRIGGER_PATTERN.split(text, maxsplit=1)[-1].strip()
    after = _LEADING_FILLER.sub("", after)
    after = _TRAILING_FILLER.sub("", after).strip()
    after = after.strip(" ?.!,\"'")
    return after or text.strip()


def engines() -> list:
    """web_search.engines as a list of names; [] is auto."""
    raw = getattr(config, "WEB_SEARCH_ENGINES", "auto") or "auto"
    names = raw if isinstance(raw, (list, tuple)) else str(raw).split(",")
    names = [str(n).strip().lower() for n in names if str(n).strip()]
    return [] if not names or "auto" in names else list(dict.fromkeys(names))


def known_engines() -> list:
    """The text engines the installed ddgs has (google, yandex, mojeek...)."""
    try:
        from ddgs.engines import ENGINES
        return sorted(ENGINES["text"])
    except Exception:
        return []


def search(query: str, max_results: int = None) -> list:
    """A live web search through ddgs. Returns [] on any failure
    (missing package, no internet, rate limit, timeout) instead of
    raising, so a flaky search never breaks the conversation - Luna
    just answers without it, or says she couldn't find anything.

    web_search.engines "auto": ddgs picks (Wikipedia first, then engines
    in a random order until it has enough). Named engines: each is asked
    for max_results on its own, at the same time, and every result says
    which engines returned it ("engines"), so she can tell you where
    something came from and where it didn't show up.
    """
    max_results = max_results or config.WEB_SEARCH_MAX_RESULTS

    # print() here painted over the screen; the log has it, and the one
    # thing you can fix yourself is said once in the conversation.
    try:
        from ddgs import DDGS
    except ImportError:
        logbook.warn("websearch", "ddgs isn't installed")
        logbook.tell("Web search needs the ddgs package: pip install ddgs")
        return []

    names = engines()
    if names:
        known = known_engines()
        unknown = [n for n in names if known and n not in known]
        if unknown:
            logbook.warn("websearch", "no such search engine: %s (there are: %s)",
                         ", ".join(unknown), ", ".join(known))
            names = [n for n in names if n not in unknown]
    if not names:
        try:
            with DDGS() as ddgs:
                return list(ddgs.text(query, max_results=max_results))
        except Exception as e:
            logbook.warn("websearch", "search failed: %s", e)
            return []

    def ask(name):
        try:
            with DDGS() as ddgs:    # one each: they run in threads
                return name, list(ddgs.text(query, max_results=max_results, backend=name))
        except Exception as e:
            logbook.warn("websearch", "%s failed: %s", name, e)
            return name, []

    with ThreadPoolExecutor(max_workers=len(names)) as pool:
        answers = list(pool.map(ask, names))
    return merge(answers)


def merge(answers) -> list:
    """[(engine, results)] -> one list, taking each engine's next result in
    turn so none drowns the others out; a page more than one returned is
    listed once, with all their names."""
    out, by_url = [], {}
    longest = max((len(results) for _, results in answers), default=0)
    for rank in range(longest):
        for name, results in answers:
            if rank >= len(results):
                continue
            r = results[rank]
            url = (r.get("href") or "").strip().rstrip("/")
            if url and url in by_url:
                if name not in by_url[url]["engines"]:
                    by_url[url]["engines"].append(name)
                continue
            r = dict(r, engines=[name])
            out.append(r)
            if url:
                by_url[url] = r
    return out


def result_line(i: int, r: dict) -> str:
    """One result as she reads it, with the engines that returned it when
    she was asked to search named ones."""
    title = (r.get("title") or "").strip()
    body = (r.get("body") or "").strip()
    if len(body) > _MAX_SNIPPET_CHARS:
        body = body[:_MAX_SNIPPET_CHARS].rsplit(" ", 1)[0] + "..."
    url = (r.get("href") or "").strip()
    found = f" [{', '.join(r['engines'])}]" if r.get("engines") else ""
    return f"{i}. {title} - {body} ({url}){found}"


_MAX_SNIPPET_CHARS = 220  # keeps each result's token cost predictable


def format_results(query: str, results: list) -> str:
    """Builds the system-role context block injected for this turn."""
    if not results:
        return (
            f'(A web search for "{query}" was attempted but returned no '
            "results. Tell the user you couldn't find anything for that - "
            "don't make up an answer.)"
        )

    lines = [
        f'(Live web search results for "{query}". Use these to answer '
        "naturally in your own voice and mention you looked it up - "
        "don't read them out verbatim or list every result, just work "
        "the relevant bits into a normal spoken reply.)"
    ]
    lines += engines_note(results)
    for i, r in enumerate(results, 1):
        lines.append(result_line(i, r))
    return "\n".join(lines)


def engines_note(results) -> list:
    """When results carry their engines: which were asked, and what the
    brackets mean."""
    asked = engines()
    if not asked or not any(r.get("engines") for r in results):
        return []
    answered = {e for r in results for e in r.get("engines", ())}
    quiet = [e for e in asked if e not in answered]
    note = (f"Searched {', '.join(asked)}. The engines in brackets returned that result; "
            "a result only some returned may be one the others leave out.")
    if quiet:
        note += f" No results from {', '.join(quiet)}."
    return [note]
