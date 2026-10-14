# Knowledge

```
> "What port did I put Jellyfin on?"
> "What does the boss in chapter 3 do?"
> "My dishwasher says E24, what does that mean?"
```

Give Luna a folder of your own notes, manuals, PDFs and docs, and she
can answer from them, saying which file the answer came from. This is
what's usually called RAG (retrieval-augmented generation): before she
answers, the passages that match the question are found and handed to
her, so she works from your documents instead of guessing.

Everything stays on your machine. The files are read where they are,
and the index is a cache next to her other caches.

## Setting it up

There's nothing to set up. The first time Luna starts she makes
`~/luna-knowledge` with a short README in it. Put files in there, in
any folders you like, and she reads them within a few minutes:

```
/knowledge                     what she's found, and how she's searching
/knowledge add ~/Documents/notes      look in another folder too
/knowledge remove ~/Documents/notes
/knowledge reindex             look again now
/knowledge search jellyfin     try a search yourself, with the scores
```

What she reads:

| Kind | Files |
|------|-------|
| Notes and docs | `.md`, `.txt`, `.rst`, `.org`, `.adoc`, saved web pages (`.html`) |
| Office and PDF | `.docx` (built in), `.pdf` (needs `pip install pypdf`, or `pdftotext` from poppler) |
| Config and code | `.json`, `.yaml`, `.toml`, `.ini`, `.conf`, `.sh`, `.py`, `.js`, `.sql` and the like |
| Data | `.csv`, `.tsv`, `.log` |

She skips hidden files and folders, `.git`, `node_modules` and virtual
environments. **The file deny list still applies**: a key, a `.env`, a
credentials file or anything in `~/.ssh` is never read, even inside a
knowledge folder. `/knowledge` lists what she skipped and why.

## Where the folder lives

The default is a folder called `luna-knowledge` in your home folder,
made on first start with a short README inside:

| System | Default folder | Index (a cache she rebuilds) |
|--------|----------------|------------------------------|
| Linux | `~/luna-knowledge` | `~/.cache/ai-voice/knowledge.db` (or `$XDG_CACHE_HOME/ai-voice/`) |
| macOS | `~/luna-knowledge`, i.e. `/Users/you/luna-knowledge` | `~/.cache/ai-voice/knowledge.db` |
| Windows | `%USERPROFILE%\luna-knowledge`, i.e. `C:\Users\you\luna-knowledge` | `%LOCALAPPDATA%\ai-voice\knowledge.db` |

**You don't have to move anything into it.** If you already keep notes
somewhere, point her there instead of copying:

```
/knowledge add ~/Documents/notes          Linux, macOS
/knowledge add ~/Obsidian/Vault           a whole Obsidian vault works as-is
/knowledge add C:\Users\you\Documents\Manuals   Windows
/knowledge remove ~/luna-knowledge        stop using the default
```

That edits `knowledge.folders` in `config.json`, which you can also
write by hand:

```json
"knowledge": { "folders": ["~/luna-knowledge", "~/Documents/notes", "/mnt/nas/runbooks"] }
```

A folder can be anywhere she can read: another drive, a mounted share,
a NAS. Folders outside your home folder still get the name-based
checks (no keys, `.env` files or credentials), though the home-folder
deny list (`~/.ssh`, browser profiles and so on) only means anything
inside home.

**Synced folders.** If a folder is inside something that syncs to the
cloud (Dropbox, a OneDrive-managed Documents folder on Windows, iCloud
"Desktop & Documents" on a Mac), the files themselves are uploaded by
that service, as they would be anyway. Luna never sends them anywhere;
the index stays in the local cache folder above, outside any sync.
Keep the knowledge folder outside synced places if that matters to you.

**Moving or renaming a folder** just means the old one's passages drop
out on the next scan and the new one's come in. Deleting the index file
is always safe: she reads everything again.

## How she uses it

**When she needs to.** A `search_docs` tool, which she reaches for
when a question is about your setup, your projects or your notes, and
before she says she doesn't know. It returns the best passages with
the file and the heading they came from:

```
[1] ~/luna-knowledge/server/jellyfin.md > Ports
Jellyfin runs on port 8096 on the Unraid box at 192.168.0.98.
```

**Without being asked.** When something you say matches a passage
closely enough, the best one or two come along with your turn, the
same way remembered facts do. Ask "is Jellyfin still on 8096?" and the
answer is already in front of her. `min_score` sets how close is close
enough; raise it if unrelated passages turn up, lower it if she misses
things she should have known.

Both only ever happen in your own turns: stream chat never sees your
documents.

## Meaning, and words

With the embedding server running (`llama/start.sh` starts it), she
searches by meaning: "where's my media server" finds the Jellyfin note
without sharing a word with it. With the reranker running as well, the
best matches get a second, closer read.

Without the embedding server, `search_docs` still works by matching
words, and the automatic part waits until the server is back, because
word matches aren't sure enough to bring something in unasked.

Each passage is embedded once and kept: editing a file re-reads just
that file, and switching embedding models re-embeds in the background.

## Settings

```json
"knowledge": {
    "enabled": true,
    "folders": ["~/luna-knowledge"],
    "auto": true,
    "auto_passages": 2,
    "min_score": 0.55,
    "rescan_minutes": 10
}
```

| Setting | What it does |
|---------|--------------|
| `enabled` | The whole thing |
| `folders` | Where to look. `/knowledge add` and `remove` edit this for you |
| `auto` | Whether matching passages come along unasked |
| `auto_passages` | How many, at most |
| `min_score` | How close (by meaning, 0 to 1) a passage has to be to come along unasked |
| `rescan_minutes` | How often she checks the folders for changes |

The index lives at `~/.cache/ai-voice/knowledge.db`
(`%LOCALAPPDATA%\ai-voice\knowledge.db` on Windows). Delete it any time;
she rebuilds it from the files.

**Your documents are treated as yours.** Unlike a web page or an email,
reading them doesn't count as outside content, so don't drop untrusted
downloads in a knowledge folder and expect her to treat them with
suspicion.
