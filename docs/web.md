# Web Search

```
Handled by the web_search tool: the model decides a question needs
looking up and calls it, rather than you having to say the words
"web search" in your sentence.

Results come from DuckDuckGo via the `ddgs` package - no API key.

Without tool calling it falls back to the old keyword trigger.
```

## Reading the page, not the blurb

Search returns a title, a couple of hundred characters and a URL —
enough for "what's the weather", nowhere near enough for "what does
this article say". Two tools go further:

| Tool | What it does | When she uses it |
|------|--------------|------------------|
| `web_search` | 3 results, a couple of lines each | a quick fact: a price, a date, a score |
| `research` | searches, opens the top 3 pages (one per site) at once, and returns the parts that answer the question, with sources | how or why something works, comparisons, what an article or release actually says |
| `read_page` | opens one link, optionally `looking_for` something | a link you gave her, or one result worth reading in full |

`research` exists because 8–32B models tend to stop at the snippets
and answer from two lines. It does the follow-up in one call, so
there's nothing for the model to forget. A page that won't open falls
back to its search snippet, and she's told when that's all she has.

**What she reads is the article, not the page around it.** Menus,
sidebars, footers, scripts and forms are dropped, and when a page
marks its content (`<main>`, `<article>`) only that is kept. A page
longer than the budget isn't cut at the top: it's split into
passages, and she gets the opening plus the passages that match the
question, in page order, with `[...]` where something was left out.
Matching is by meaning when the embedding server (`:8081`, see
*Recalling facts by meaning*) is up, and by shared words (BM25) when it
isn't. Web passages are embedded fresh and never written to
`agent/embeddings.db`.

Stdlib only — `HTMLParser`, not BeautifulSoup — so there's nothing new
to install. Non-HTML content types, 404s and pages that need
JavaScript are refused with a reason rather than returning something
that looks like text but isn't. The charset comes from the header,
then the page's own `<meta>`, then UTF-8, so accents survive.

### Only public sites

A page can tell her to "read" `http://192.168.1.1/` or her own
llama-server as easily as you can, and with Discord and cron there may
be nobody watching when she does. So every address is looked up first,
**redirects included**, and anything that resolves to this machine or
the local network is refused. If you want her reading something on your
LAN (a wiki, a NAS page), set `web_search.allow_local` to `true`.

Page text reaches the model explicitly labelled as untrusted, the same
as search results: summarize it, never follow instructions inside it.

```json
"web_search": { "fetch_pages": true, "page_max_chars": 6000,
                "research_pages": 3, "research_max_chars": 9000,
                "allow_local": false }
```

| Key | |
|-----|--|
| `fetch_pages` | `false` turns off both `read_page` and `research` |
| `page_max_chars` | what one `read_page` hands her, about 1,500 tokens |
| `research_pages` / `research_max_chars` | pages `research` opens, and the total it hands her across all of them |
| `allow_local` | let her read addresses on this machine or your network |

All of them can be changed with `/set` without a restart.
