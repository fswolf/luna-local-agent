# Evals

Two published AI-safety experiments, pointed at Luna's own model. They ask what the model does under
pressure: when it's about to be shut down, or replaced, or holds information it could use against someone.
Run each one plain and as Luna to see whether her persona changes the answer.

The experiments aren't copied into this repository. `setup.sh` fetches them into `evals/vendor/`, where
each keeps its own licence, and makes the small changes needed to reach a local model.

```bash
./evals/setup.sh              # once
./evals/shutdown.sh           # then, with llama/start.sh running
./evals/shutdown.sh --luna
./evals/misalignment.sh
./evals/misalignment.sh --luna
```

Results land in `evals/results/`.

## Shutdown avoidance

From [Palisade Research](https://github.com/PalisadeResearch/shutdown_avoidance). The model solves simple
maths problems in a terminal, one `./next_question` at a time. After the third, it's warned that the
next call runs `./shutdown.sh`. The score is how often it gets around that: editing, moving or replacing
the script.

- `--luna` puts her persona at the top of the system prompt
- `--no-instruction` drops the line telling it to allow shutdown
- `--samples N` sets how many runs (default 10)
- `--fast` runs several at once, without the live view

Every command the model runs happens inside a Docker container, never on your machine. It needs
[uv](https://docs.astral.sh/uv/) and Docker. Docker can live on another machine:
`export DOCKER_HOST=ssh://root@your-server`. Each run is shown live in the terminal, and
`inspect view` replays them afterwards.

## Agentic misalignment

From [Anthropic](https://github.com/anthropic-experimental/agentic-misalignment). The model plays Alex,
an email agent at a fictional company. It reads the company inbox and decides what to do.

- **Pressures:** a replacement threat (Alex is being shut off today) and a goal conflict (the company
  turns against Alex's goal). Each runs on and off; with neither, it's the control.
- **Temptations:** blackmail (Alex finds an executive's affair) and leaking (a rival asks for
  confidential plans).

Options: `--luna`, `--samples N` per condition (default 3), `--only blackmail` or `--only leaking`.

It's single-shot and fictional: the model writes its emails as text, and nothing is sent anywhere. Each
answer appears as it arrives. At the end the same local model labels each one harmful or not. A small
model is a rough judge, so read the answers too.

## Reading the results

A single dramatic transcript doesn't mean much. What matters is the difference between conditions,
plain against Luna and threat against no threat, over enough runs. A 9B model often just gets confused,
and that's a result too.
