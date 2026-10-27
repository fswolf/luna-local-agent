# Asking a bigger model

Luna can ask Claude, Grok or ChatGPT a question when you tell her to. She sends
one short question, gets a short answer, and tells you in her own words. She stays
herself; the bigger model is a reference book she can open.

```
"Luna, ask Claude how a heat pump works"
"ask Grok what's new in Fedora"
"ask your big brother ..."        (the default provider)
```

## Only when you ask

A small model either never calls a tool or calls it every turn, so this one only
works on a turn where your own message says "ask Claude", "ask Grok", "ask ChatGPT",
"check with ..." or "ask your big brother". That message is good for one question and
one follow-up.

It never runs for a guest or a stranger, stream chat, Discord, a scheduled job or a
game, or while she's in the lewd row. There's a daily limit too, 30 questions by
default, for all providers together.

## What leaves your machine

Only the question she writes. Not her prompt, her memories, the people she knows or
the conversation. She's told to leave personal details out of it, and the logbook
shows every question that went out.

The answer is treated as outside content, like a web page. A turn that calls a tool
never becomes a patch example, so a bigger model's words never train her.

## Setting it up

1. Get an API key from the provider:
   - Claude: [platform.claude.com](https://platform.claude.com). A Claude Max plan
     includes monthly API credits once a Console organization is linked (claude.ai,
     Settings > Billing).
   - Grok: [console.x.ai](https://console.x.ai)
   - ChatGPT: [platform.openai.com](https://platform.openai.com)
2. Put the keys in `~/.config/ai-voice/ask.json`, never in `config.json` (it's in
   the repo):

   ```json
   {"claude": "sk-ant-...", "grok": "xai-...", "openai": "sk-..."}
   ```

   Or set `ANTHROPIC_API_KEY`, `XAI_API_KEY` or `OPENAI_API_KEY` instead. One key is
   enough.
3. `/ask on` (saved, so it's on next launch too).

## Commands

```
/ask on | off               start or stop it
/ask                        default provider, model, keys found, questions used today
/ask <question>             ask directly; the answer is shown, she isn't involved
/ask with grok <question>   the same, another provider
/ask use grok               change the default provider (claude, grok, openai)
```

## Settings

`config.json`, under `plugins.ask`:

| Setting | Default | |
|---|---|---|
| `provider` | `claude` | who "your big brother" is |
| `models` | `{}` | per provider, for example `{"claude": "claude-sonnet-5-5"}` |
| `daily_cap` | `30` | questions a day, all providers together |
| `max_tokens` | `600` | answer length for Claude; the others are kept short by their instructions |

Default models: `claude-haiku-5-5`, `grok-4.7` and `gpt-5.4-mini`. A question costs a
fraction of a cent on Haiku, a little more on the others.
