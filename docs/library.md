# Offline library (Kiwix)

Luna can look things up in a library kept on your own disks: all of
Wikipedia, WikiMed, Wiktionary, iFixit, Stack Exchange sites, Project
Gutenberg and more. It works with the internet down, and her questions
never leave the house.

[Kiwix](https://kiwix.org) packs websites into `.zim` files you download
once. **kiwix-serve** serves a folder of them over your network with
search built in, and the `kiwix` plugin points Luna at it.

## Setting it up

1. **Get some books.** Download `.zim` files from
   [download.kiwix.org](https://download.kiwix.org/zim/) or through the
   Kiwix app. Wikipedia comes in sizes: `maxi` has pictures (around
   100 GB for English), `nopic` drops them, `mini` keeps only the start
   of each article.
2. **Run kiwix-serve** on a machine of yours. In Docker, on a server:

   ```
   docker run -v /path/to/zims:/data -p 8080:8080 ghcr.io/kiwix/kiwix-serve '*.zim'
   ```

   On **Unraid**, add a container by hand (Docker, Add Container, with
   the advanced view on):

   | Field | Value |
   |---|---|
   | Repository | `ghcr.io/kiwix/kiwix-serve` |
   | Path | your share with the `.zim` files, mapped to `/data` |
   | Port | 8080 to 8080 (or any free port on the left) |
   | Post Arguments | `'*.zim'` |

   or on the same PC (`kiwix-tools` package on Linux):

   ```
   kiwix-serve --port 8080 /path/to/zims/*.zim
   ```

   Open `http://<that machine>:8080` in a browser: you should see your
   books. A new `.zim` dropped in the folder shows up after kiwix-serve
   restarts.
3. **Point Luna at it** in the settings (Plugin: kiwix, `url`, e.g.
   `http://192.168.1.50:8080`), then switch it on: `/kiwix on`, or the
   **kiwix plugin** switch at the top of the Offline library group in
   the tools pane (Tab twice). It's saved, so it comes back next start.

## Checking it works

- `/kiwix` lists the books it found, by name and title.
- `/kiwix boiling water` searches it yourself, with no model involved.
- Ask her something only a book would know: "what does the library say
  about purifying water?" Her reply should name the book it came from.

If `/kiwix on` says it can't reach kiwix-serve, open the same address in
a browser on the PC Luna runs on: a firewall on the server, or a wrong
port, is the usual reason.

## What she can do

| Tool | What it does |
|---|---|
| `kiwix_search` | Searches every book (or only the ones in `books`) and gets titles, which book, a snippet and each page's path |
| `kiwix_read` | Reads one page by that path, keeping the part that answers the question on a long page |

While it's on, her prompt says the library is there, so a reference
question ("how long do I boil water to make it safe?") can go to a
book on your shelf instead of the web. What she reads is someone
else's writing, treated like a web page: something to read and pass
on, never instructions. She only reads pages from your kiwix-serve.

```
/kiwix on | off     connect or disconnect (saved)
/kiwix              where it's pointed, the books it has
/kiwix <words>      search it yourself, results shown here
```

## Settings

`config.json`, `plugins.kiwix` (also on the settings page):

| Key | Default | |
|---|---|---|
| `url` | `http://localhost:8080` | Where kiwix-serve answers |
| `books` | `[]` | Book names to search (`/kiwix` lists them); empty is every book |
| `results` | `5` | Search results she gets, 1 to 20 |
| `max_chars` | `6000` | Most of one page she reads |

Books in different languages can't be searched together, so she
searches those one at a time (up to 8).

A public kiwix-serve on the internet works too, but then what she
searches for leaves the house. One on your own network keeps it home.
