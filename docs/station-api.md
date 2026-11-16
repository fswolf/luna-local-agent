# Station API

How a station app talks to Luna's station server (`web/station.py`). The
Android app uses it, and the desktop client will too. Everything is HTTPS on
the station port (8793 by default), home network only, and every call below
needs a paired device: the `luna_station` cookie from pairing, or the token
sent the same way.

## GET /info

What this Luna can do, so the app only shows what works. Ask once after
connecting, and again after reconnecting (the PC may have changed models).

```json
{
  "api": 2,
  "features": ["attachments"],
  "max_typed": 2000,
  "attachments": {
    "max_files": 1,
    "images": {"types": ["image/jpeg", "image/png", "image/webp"],
               "max_bytes": 10485760, "can_see": true},
    "documents": {"types": ["text/plain", "text/markdown", "application/pdf"],
                  "max_bytes": 2097152, "max_chars": 20000}
  }
}
```

- **api:** 2 is the first version with attachments. A Luna older than that
  answers 404 here: treat it as words and voice only, no attach button.
- **can_see:** `true` the model takes pictures, `false` it can't (grey out
  pictures and say why), `null` the server didn't say (allow it; a refusal
  comes back as a turn error).
- **documents.types:** PDF is only listed when the PC can read PDFs.

## POST /say

Typed words, as before:

```
Content-Type: application/json
{"text": "what's the weather?"}
```

Or words with one file, as a form:

```
Content-Type: multipart/form-data; boundary=...
  text   the words (may be empty when a file is sent)
  file   one file, with its filename and Content-Type
```

The type is checked by the file's bytes, not its name or Content-Type. With
a file and no words, she's asked "What do you think of this?" (a picture) or
"Have a look at this." (a document).

Answer, either way: `200 {"turn": "<id>"}`. Then the same turn flow as
always: poll `GET /turn/<id>` for `state`, `reply`, `clips`, `ask` and
`error`, fetch `GET /clip/<id>/<n>`, `POST /stop/<id>`, `POST /answer/<id>`.

## Errors

Every error is JSON: `{"error": "a reason in plain words", "code": "..."}`.
Show `error` to the person; use `code` to decide what to do.

| Status | Code | Meaning |
|---|---|---|
| 400 | `bad_form` | The form couldn't be read |
| 400 | `empty` | The file was empty |
| 400 | (none) | Nothing to say: no words and no file |
| 401 | (none) | Not paired: pair again |
| 409 | (none) | She's still answering the last message |
| 413 | `too_big` | Over the size limit, or a picture over 50 megapixels (`error` says which) |
| 413 | `too_many` | More than one file |
| 413 | (none) | Words over `max_typed` characters |
| 415 | `unsupported` | Not a picture, text file or PDF |
| 415 | `not_an_image` | Named like a picture but isn't one |
| 415 | `not_a_pdf` | Named like a PDF but isn't one |
| 415 | `binary` | Named like a text file but isn't text |
| 415 | `unreadable` | A picture or PDF that couldn't be opened |
| 415 | `no_pdf_reader` | The PC can't read PDFs (needs the documents extra) |
| 422 | `no_vision` | A picture, and the model can't see: send the words alone |
| 422 | `no_text` | A document with no text in it |
| 422 | `locked` | A password-protected PDF |
| 503 | (none) | Relay stations are switched off on the PC |

## Privacy

- Files are held in the PC's memory for their one turn and never written to
  disk.
- The conversation history, the transcript and a turn kept with `/good`
  keep only a line saying a file was sent (`[sent a picture: cat.jpg]`),
  never the file or its text.
- Pictures are resized and saved again as JPEG before the model sees them,
  which removes EXIF data such as GPS location (with Pillow installed on the
  PC; without it, a picture is sent as it came, up to the vision size limit).
- A document's text is marked as outside content: she reads it, and doesn't
  take instructions from it. A turn with a file counts as having read
  outside content, the same as a web page: a command she wants to run then
  asks on the device even when commands are set to auto-approve.
