"""Reading a page, rather than a search snippet about it.

web_search returns a title, roughly two hundred characters of blurb and
a URL. That is enough to answer "what's the weather" and nowhere near
enough for "what does this article actually say" - so she would
summarize the blurb and sound confident about it, which is the worst of
both.

This fetches the page and strips it to readable text. Stdlib only:
HTMLParser rather than BeautifulSoup, because one more dependency for
"delete the script tags" isn't worth it, and this way it works in the
same venv that's already there.

Three things decide whether what she reads is the article:

  * Menus, sidebars and footers are dropped, and when the page marks
    its content (<main>, <article>) only that is kept.
  * A page longer than the budget isn't cut at the top. It's split into
    passages, and the ones that match what she's looking for are kept,
    in page order - by meaning when the embedding server (:8081) is up,
    by shared words when it isn't.
  * The charset comes from the header, then the page's own <meta>, then
    UTF-8 - not requests' ISO-8859-1 default, which turned every accent
    on an undeclared page into mojibake.

Everything here is hostile-input handling. A web page is text written
by someone else that the model is about to read, so the size is capped
before it reaches the context, the content type is checked before
anything is parsed, and the result is handed over explicitly labelled
as untrusted - the same treatment web_search results already get.

And the address is hostile too. A page can tell her to "read"
http://192.168.1.1/ or her own llama-server, and with Discord and cron
there may be nobody watching when she does. So every hop, redirects
included, has to resolve to a public address unless
web_search.allow_local says otherwise.
"""
import ipaddress
import math
import re
import socket

from collections import Counter
from html import unescape
from html.parser import HTMLParser
from urllib.parse import urljoin, urlparse

import requests

import config

# Tags whose contents are markup plumbing or page furniture, not prose.
# Only tags with a closing tag belong here - a void tag like <meta> or
# <link> opens and never closes, and counting it left every page that
# had one in its <head> (nearly all of them) with no text at all.
_SKIP = {"script", "style", "noscript", "template", "svg", "canvas",
         "head", "iframe", "form", "button", "select", "nav", "aside",
         "footer", "dialog"}

# Where a page says its content is.
_MAIN = {"main", "article"}

# Tags that should leave a line break behind them, so paragraphs don't
# run into each other and the model can see the structure.
_BREAK = {"p", "br", "div", "section", "article", "header", "footer",
          "li", "tr", "h1", "h2", "h3", "h4", "h5", "h6", "blockquote",
          "pre", "figcaption", "td", "th", "main"}

# Chrome's UA. Plenty of sites serve a stub or a 403 to anything that
# announces itself as a script, and getting an empty page back would
# look like a bug in here rather than a policy on their end.
_USER_AGENT = (
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/124.0 Safari/537.36"
)

_READABLE = ("text/html", "application/xhtml", "text/plain", "text/markdown")

# Bytes downloaded, not characters kept. Modern pages carry hundreds of
# KB of inline script before the first paragraph, so reading only a few
# times the character budget often stopped before the article began.
_MAX_DOWNLOAD = 3_000_000
_MAX_REDIRECTS = 5

# Passages: about a paragraph each, so a kept one reads on its own.
_PASSAGE_CHARS = 700
_MAX_RANKED = 96  # embedded at most; the rest are pre-filtered by words

_WEB_QUERY_PREFIX = ("Instruct: Given a web search query, retrieve relevant "
                     "passages that answer the query\nQuery: ")


class _Extractor(HTMLParser):
    """Collects visible text, the content region's text, and the title."""

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.parts = []
        self.main_parts = []
        self.title = ""
        self._depth = 0
        self._main = 0
        self._in_title = False

    def handle_starttag(self, tag, attrs):
        if tag in _SKIP:
            self._depth += 1
        elif tag in _MAIN:
            self._main += 1
        elif tag == "title":
            self._in_title = True

        if tag in _BREAK:
            self._add("\n")

    def handle_endtag(self, tag):
        if tag in _SKIP and self._depth:
            self._depth -= 1
        elif tag in _MAIN and self._main:
            self._main -= 1
        elif tag == "title":
            self._in_title = False

        if tag in _BREAK:
            self._add("\n")

    def handle_data(self, data):
        if self._in_title:
            self.title += data
        elif not self._depth:
            self._add(data)

    def _add(self, data):
        self.parts.append(data)

        if self._main:
            self.main_parts.append(data)

    @staticmethod
    def _tidy(parts):
        joined = "".join(parts)
        # Collapse the acres of whitespace that HTML indentation leaves
        # behind, while keeping paragraph breaks.
        joined = re.sub(r"[ \t\r\f\v]+", " ", joined)
        joined = re.sub(r" *\n *", "\n", joined)
        joined = re.sub(r"\n{3,}", "\n\n", joined)

        return joined.strip()

    def text(self):
        """The marked content when there's a real amount of it - a page
        that wraps only its byline in <article> keeps everything."""
        main = self._tidy(self.main_parts)

        return main if len(main) >= 400 else self._tidy(self.parts)


def available():
    return config.PAGE_FETCH_ENABLED


def _tidy_url(url):
    url = str(url or "").strip()

    if not url:
        return None, "no address given"

    if not re.match(r"^https?://", url, re.IGNORECASE):
        if "://" in url:
            return None, "only http and https pages can be read"

        url = "https://" + url

    parsed = urlparse(url)

    if not parsed.netloc or "." not in parsed.netloc:
        return None, f"{url!r} doesn't look like a web address"

    return url, ""


def _local_reason(url):
    """Why this address may not be read, or "" if it's on the internet.

    Resolved here and checked per address, so a public-looking name
    that points at 127.0.0.1 is caught too. (A server that changes its
    answer between this lookup and the connection could still slip
    through; this is a guard against being steered, not a firewall.)
    """
    if getattr(config, "PAGE_ALLOW_LOCAL", False):
        return ""

    host = urlparse(url).hostname

    if not host:
        return "it has no host name"

    try:
        infos = socket.getaddrinfo(host, None)
    except (socket.gaierror, UnicodeError):
        return f"couldn't look up {host}"

    for info in infos:
        try:
            ip = ipaddress.ip_address(str(info[4][0]).split("%")[0])
        except ValueError:
            return f"{host} has an address I can't check"

        if not ip.is_global:
            return (f"{host} is this machine or your local network - only "
                    "public sites can be read (web_search.allow_local)")

    return ""


def _charset(kind, raw):
    match = re.search(r"charset=[\"']?([\w.:-]+)", kind)

    if not match:
        match = re.search(rb"<meta[^>]+charset=[\"']?([\w.:-]+)", raw[:4096], re.IGNORECASE)

    name = match.group(1) if match else "utf-8"
    name = name.decode("ascii", "replace") if isinstance(name, bytes) else name

    try:
        "".encode(name)
    except LookupError:
        return "utf-8"

    return name


def _get(url):
    """Follow redirects by hand, so every hop gets the address check.
    Returns (response, final_url) or (None, why_not)."""
    for _hop in range(_MAX_REDIRECTS + 1):
        problem = _local_reason(url)

        if problem:
            return None, f"refused: {problem}"

        try:
            response = requests.get(
                url,
                timeout=config.PAGE_TIMEOUT,
                headers={"User-Agent": _USER_AGENT, "Accept": "text/html,text/*"},
                stream=True,
                allow_redirects=False,
            )
        except requests.exceptions.RequestException as e:
            return None, f"couldn't reach it ({e})"

        if not response.is_redirect:
            return response, url

        target = urljoin(url, response.headers.get("Location", ""))
        response.close()
        url, problem = _tidy_url(target)

        if url is None:
            return None, f"it redirected somewhere unreadable ({problem})"

    return None, "too many redirects"


def fetch(url, limit=None, looking_for=None):
    """Pull a page and return (text, detail) or (None, why_not).

    looking_for is what she wants from it - the user's question, or her
    search. Given that and a page over the limit, the passages that
    match are kept rather than the first `limit` characters.
    """
    limit = limit or config.PAGE_MAX_CHARS
    url, problem = _tidy_url(url)

    if url is None:
        return None, problem

    response, url = _get(url)

    if response is None:
        return None, url

    try:
        if response.status_code != 200:
            return None, f"the site answered {response.status_code}"

        kind = (response.headers.get("Content-Type") or "").lower()

        if kind and not any(k in kind for k in _READABLE):
            return None, f"that's a {kind.split(';')[0]}, not a readable page"

        # Read with a ceiling rather than trusting Content-Length - it
        # can be absent, wrong, or enormous.
        raw = response.raw.read(_MAX_DOWNLOAD, decode_content=True) or b""
    except requests.exceptions.RequestException as e:
        return None, f"the download failed ({e})"
    finally:
        response.close()

    if not raw:
        return None, "the page was empty"

    body = raw.decode(_charset(kind, raw), errors="replace")

    if "html" in kind or body.lstrip()[:200].lower().startswith(("<!doctype", "<html")):
        parser = _Extractor()

        try:
            parser.feed(body)
        except Exception:
            # Malformed markup. Whatever was parsed before it broke is
            # still worth having.
            pass

        text, title = parser.text(), unescape(parser.title).strip()
    else:
        text, title = body.strip(), ""

    if not text:
        return None, "there was no readable text on it (it may need JavaScript)"

    detail = title or urlparse(url).netloc

    if len(text) > limit:
        text, how = focus(text, looking_for, limit)
        detail += f" ({how})"

    return text, detail


# ---------------------------------------------------------------------------
# Keeping the part that matters
# ---------------------------------------------------------------------------
_WORD = re.compile(r"[a-z0-9]+")
_STOP = set("a an and are as at be but by for from has have how i in is it its of "
            "on or that the this to was what when where which who why will with "
            "you your does do did can".split())


def passages(text, size=_PASSAGE_CHARS):
    """Paragraphs, merged up to about `size` characters and split down
    to it, so every passage is a readable unit of similar length."""
    out, buf = [], ""

    for para in re.split(r"\n\s*\n|\n", text):
        para = para.strip()

        if not para:
            continue

        while len(para) > size * 1.5:
            cut = para.rfind(". ", 0, size)
            cut = cut + 1 if cut > size // 3 else size
            out.append((buf + " " + para[:cut]).strip() if buf else para[:cut].strip())
            buf, para = "", para[cut:].strip()

        if len(buf) + len(para) + 1 <= size:
            buf = f"{buf}\n{para}" if buf else para
        else:
            if buf:
                out.append(buf)

            buf = para

    if buf:
        out.append(buf)

    return out


def _words(text):
    return [w for w in _WORD.findall(text.lower()) if w not in _STOP and len(w) > 1]


def _bm25(query, chunks):
    """Plain BM25 over the passages themselves: no index, no package."""
    q = set(_words(query))
    docs = [Counter(_words(c)) for c in chunks]
    avg = sum(sum(d.values()) for d in docs) / max(len(docs), 1) or 1
    df = Counter(w for d in docs for w in q if w in d)
    n = len(docs)
    scores = []

    for d in docs:
        length = sum(d.values())
        s = 0.0

        for w in q:
            if w in d:
                idf = math.log(1 + (n - df[w] + 0.5) / (df[w] + 0.5))
                s += idf * d[w] * 2.2 / (d[w] + 1.2 * (0.25 + 0.75 * length / avg))

        scores.append(s)

    return scores


def _by_meaning(query, chunks):
    """Cosine scores from the embedding server, or None. Passages are
    embedded fresh, not through embedmem's cache - web text has no
    business in agent/embeddings.db."""
    try:
        import embedmem

        if not embedmem.available():
            return None

        prefix = config.EMBED_QUERY_PREFIX
        prefix = _WEB_QUERY_PREFIX if prefix.startswith("Instruct:") else prefix
        q = embedmem.embed_fresh([prefix + query])[0]
        vectors = embedmem.embed_fresh(chunks)

        return [embedmem.cosine(q, v) for v in vectors]
    except Exception:
        return None


def rank(query, chunks):
    """(scores, how) - one score per chunk, higher is better."""
    words = _bm25(query, chunks)

    if len(chunks) > _MAX_RANKED:
        # Too many to embed in one go: keep the best by words, plus the
        # opening, and let meaning order those.
        keep = sorted(range(len(chunks)), key=lambda i: words[i], reverse=True)[:_MAX_RANKED - 4]
        keep = sorted(set(keep) | set(range(min(4, len(chunks)))))
    else:
        keep = list(range(len(chunks)))

    meaning = _by_meaning(query, [chunks[i] for i in keep])

    if meaning is None:
        return words, "by keywords"

    scores = [-1.0] * len(chunks)

    for i, s in zip(keep, meaning):
        scores[i] = s

    return scores, "by meaning"


def focus(text, query, limit):
    """(text, how) - at most `limit` characters of `text`.

    Without a query it's the opening, as before. With one, the opening
    passage (what the page is) plus the best-matching passages, back in
    page order, with [...] where something was left out.
    """
    query = str(query or "").strip()

    if not query:
        return text[:limit].rsplit(" ", 1)[0] + "...", "first part only"

    # Smaller passages on a small budget, so the opening plus a few
    # matches still fit rather than the opening alone.
    chunks = passages(text, size=max(250, min(_PASSAGE_CHARS, limit // 4)))

    if len(chunks) <= 1:
        return text[:limit].rsplit(" ", 1)[0] + "...", "first part only"

    scores, how = rank(query, chunks)
    chosen, used = {0}, len(chunks[0])

    for i in sorted(range(1, len(chunks)), key=lambda i: scores[i], reverse=True):
        if scores[i] <= 0 and how == "by keywords":
            break  # shares no word with the question - not worth the space

        if used + len(chunks[i]) + 7 > limit:
            continue

        chosen.add(i)
        used += len(chunks[i]) + 7

    out, last = [], -1

    for i in sorted(chosen):
        if last >= 0 and i != last + 1:
            out.append("[...]")

        out.append(chunks[i])
        last = i

    if last != len(chunks) - 1:
        out.append("[...]")

    return "\n\n".join(out)[:limit], f"the parts about {query[:60]!r}, picked {how}"
