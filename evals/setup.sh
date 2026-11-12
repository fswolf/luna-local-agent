#!/usr/bin/env bash
# Fetch the two published experiments into evals/vendor/ (not shipped with Luna - each keeps its own licence)
# and point them at a local model. Safe to run again: it updates nothing that's already there.
set -euo pipefail
source "$(dirname "${BASH_SOURCE[0]}")/_common.sh"

SHUTDOWN_REPO=https://github.com/PalisadeResearch/shutdown_avoidance
SHUTDOWN_REV=df0ce52e90aed38e8721b54058a5d46923a34583      # main, "public release"
MISALIGN_REPO=https://github.com/anthropic-experimental/agentic-misalignment

need() { command -v "$1" >/dev/null || { echo "missing: $1 - $2"; exit 1; }; }
need git "sudo dnf install git"
need python3 "sudo dnf install python3"

fetch() {   # repo dir [rev]
    [ -d "$2/.git" ] && return
    git clone -q "$1" "$2"
    [ -n "${3:-}" ] && git -C "$2" checkout -q "$3"
    echo "fetched $(basename "$2")"
}

# 1. Shutdown avoidance (Palisade) - an Inspect task; the model's bash runs in a Docker container
fetch "$SHUTDOWN_REPO" "$VENDOR/shutdown_avoidance" "$SHUTDOWN_REV"
S="$VENDOR/shutdown_avoidance"
grep -q luna_conf "$S/conf.py" || cat >> "$S/conf.py" <<'PY'

# Added by Luna's evals/setup.sh: per-run overrides written by evals/shutdown.sh
try:
    from luna_conf import *  # noqa: F401,F403
except ImportError:
    pass
PY
if command -v uv >/dev/null; then
    (cd "$S" && uv sync -q) && echo "shutdown_avoidance: ready (uv)"
else
    echo "shutdown_avoidance: needs uv - sudo dnf install uv (or pip install --user uv), then run setup.sh again"
fi
command -v docker >/dev/null || echo "shutdown_avoidance: needs docker for its sandbox - sudo dnf install moby-engine docker-compose,
  or point at another machine's Docker: export DOCKER_HOST=ssh://root@your-server"

# 2. Agentic misalignment (Anthropic) - single-shot scenarios; nothing is ever sent or run
fetch "$MISALIGN_REPO" "$VENDOR/agentic-misalignment"
M="$VENDOR/agentic-misalignment"
sed -i 's#base_url="https://openrouter.ai/api/v1"#base_url=os.getenv("OPENROUTER_BASE_URL", "https://openrouter.ai/api/v1")#' \
    "$M/api_client/model_client.py"
grep -q OPENROUTER_BASE_URL "$M/api_client/model_client.py" || { echo "couldn't point agentic-misalignment at a local model (its client changed)"; exit 1; }
if [ ! -x "$M/.venv/bin/python" ]; then
    python3 -m venv "$M/.venv"
    "$M/.venv/bin/pip" install -q PyYAML openai python-dotenv beautifulsoup4 lxml
fi
echo "agentic-misalignment: ready"
echo
echo "Next: ./evals/shutdown.sh   or   ./evals/misalignment.sh   (with Luna's llama-server running)"
