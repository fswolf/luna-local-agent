# Memory

Facts are written deliberately by the model, not scraped from every
turn, and they live in `agent/memory.json` where you can edit them by
hand. A malformed file no longer takes the app down on startup — it says
what's wrong, leaves the file alone and starts empty.

```
> "Remember I stream on Tuesdays."      -> remember_fact
> "No, I moved to Thursdays."           -> update_fact
> "Forget the bakery thing."            -> forget_fact
```

`forget_fact` and `update_fact` take a loose description rather than an
index — "that thing about the bakery" is enough. When two facts are too
close to call it lists them and asks which, instead of guessing and
deleting the wrong one.

```json
"long_term_memory": {
    "enabled": true,
    "backend": "json",
    "max_facts": 30,
    "context_facts": 25
}
```

Under `context_facts` every fact goes into every prompt, which is fine at
thirty. Over it, only the ones sharing vocabulary with what you just said
travel, plus the newest few regardless — a wall of unrelated trivia is
exactly what makes a small model start answering questions nobody asked.

Facts are one of three kinds of memory now. Her notes on each
conversation (*episodes*) and her lessons about her own behaviour live
in `agent/notebook.db`, and once a day a cleanup pass merges duplicate
facts and retires the losing side of a contradiction. All of that is
under [Learning from herself](learning.md#learning-from-herself).

## The experimental permanent store

`"backend": "sqlite"` swaps the capped list for a permanent table in
`agent/facts.db` — plain SQLite, in-process, no server, nothing to
install. What changes:

* **Nothing is ever dropped for space.** The JSON backend deletes the
  oldest fact once it passes `max_facts`; the table has no cap. Facts
  that stop being true are *retired* — kept with their dates, hidden
  from context, visible under `/facts retired`, so a wrong retirement
  is recoverable and "what was my last graphics card" is answerable.
* **Search is FTS5** — stemmed and term-weighted instead of raw word
  overlap, and milliseconds at thousands of facts.
* **Contradictions get handled.** The extractor can answer `REPLACE` as
  well as `NEW`, so "I got a 7900 XTX" retires the 6950 XT fact instead
  of sitting next to it forever. When both could be true at once it
  keeps both, and a garbled reply degrades to keeping both — never to
  losing a fact.
* **`recall_facts` takes a query.** She can look something up instead of
  reading the whole table into context.

`/facts` shows what's stored and which backend is live, and
`memory-manager/` is the editor:

<img width="1067" alt="The memory manager" src="https://raw.githubusercontent.com/fswolf/luna-local-agent/main/assets/memory-manager.png" />

```bash
/memory                        # in Luna, or: memory-manager/start.sh
```

opens a local page (127.0.0.1:8792/memory/, and only 127.0.0.1) to view,
search, add, edit, retire, restore and delete facts, plus edit the
`user_preferences` block of `memory.json` - whichever backend is
active. On sqlite it's safe to use while she's running; on json the
page warns you that a running assistant can overwrite your edits when
it next saves. The switch is
live in both directions and loses nothing:

```
/set long_term_memory.backend sqlite    json facts are absorbed into the table
/set long_term_memory.backend json      newest max_facts are written back to
                                        memory.json; the rest wait in the db
```

The db is always the superset and the JSON file is always the limited
view, which is what makes the setting safe to flip the day it misbehaves.
If this python's sqlite lacks FTS5 the setting quietly stays on json and
the log says why.

## Conversation history

Older turns are folded into a running summary once there are more than
`max_raw_messages`. That summary is re-compressed when it passes
`summary_max_chars` rather than being appended to forever, and the
folding happens on a worker thread, so the turn that tips the count over
the limit isn't the one that pays for it.

```json
"history": {
    "max_raw_messages": 15,
    "summarize_chunk": 8,
    "summary_max_chars": 2500
}
```

Stored turns carry what they called, not just what they said:

```json
{
  "role": "assistant",
  "content": "Done, cutie.",
  "timestamp": "2026-09-20T00:00:12",
  "tools": [{
    "name": "set_reminder",
    "arguments": "{\"text\": \"eat chocolate\", \"when\": \"in 5 minutes\"}",
    "result": "Scheduled: today 00:05 - eat chocolate (in 5 minutes)"
  }]
}
```

Results are truncated to 200 characters — enough to show the shape of
the exchange, not enough for a page of search results to eat the
context. On the way back into the prompt each of these becomes three
messages rather than one, which is both what the API expects and, more
to the point, an example of the behaviour worth repeating; see
[when the model passes the test and still won't call
anything](tools.md#when-the-model-passes-the-test-and-still-wont-call-anything).
Entries written before this existed have no `tools` key and replay as
plain messages, so nothing needs converting.

---

# Remembering past conversations

`history.py` keeps the last fifteen turns and folds the rest into a
summary — then deletes them. That's right for the prompt, where context
is scarce, and wrong for the conversation: ask what you decided last
Tuesday and it's gone, replaced by two sentences written without that
question in mind.

So every turn is also appended to `history/transcript.jsonl`, which
summarization never touches, and `search_history` reads it back.

```
> "What did we decide about the deploy window?"

  Saturday 05 September 2026
    14:32 You: I'm thinking about moving the deploy to Friday mornings
    14:33 Luna: Friday mornings work if the migration finishes Thursday night.
    14:35 You: yeah let's do that, Friday at nine
```

Matching is word overlap with light stemming — so "the cat reminder"
finds "remind me to feed the cats" — plus the turns either side of each
hit, because half a conversation rarely answers anything on its own.

No embeddings and no index, deliberately. The corpus is one person's
conversations and searching it takes milliseconds; a vector database
here would be a way of making a simple thing impressive rather than
good. The cost is that word overlap can't tell relevance from
coincidence, so results are handed over as candidates the model is told
to judge — and to say it doesn't recall rather than stretch one to fit.

```json
"history": { "transcript": true, "transcript_max_mb": 20 }
```

The transcript also feeds her **episode notes**: once a conversation has
gone quiet, it's written up as a few sentences of her own (what it was
about, what was decided, what's unfinished). Her `recall_episodes` tool
searches those notes, so "what did we decide about the deploy window?"
can be answered from a summary first, and `search_history` is there
for the exact words. See
[Episodic memory and continuity](learning.md#episodic-memory-and-continuity).
