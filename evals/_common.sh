# Shared by setup.sh, shutdown.sh and misalignment.sh - sourced, not run.
EVALS="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT="$(dirname "$EVALS")"
VENDOR="$EVALS/vendor"
RESULTS="$EVALS/results"
mkdir -p "$VENDOR" "$RESULTS"

# The model under test: Luna's llama-server, or EVAL_URL (any OpenAI-compatible /v1).
llm_url() {
    [ -n "${EVAL_URL:-}" ] && { echo "${EVAL_URL%/}"; return; }
    python3 - "$ROOT" <<'PY'
import json, os, sys
try: url = json.load(open(os.path.join(sys.argv[1], "config.json"))).get("llm", {}).get("llama_url", "")
except (OSError, ValueError): url = ""
url = url or "http://127.0.0.1:8080/v1/chat/completions"
print(url.split("/chat/completions")[0].rstrip("/"))
PY
}

llm_up() {
    curl -sf -m 5 "$(llm_url)/models" >/dev/null || {
        echo "No model at $(llm_url) - start Luna's llama-server first (llama/start.sh), or set EVAL_URL."
        exit 1
    }
}

# Luna as she is in agent/agent.json (same as introspection/lab.py persona()).
persona() {
    python3 - "$ROOT" <<'PY'
import json, os, sys
try: a = json.load(open(os.path.join(sys.argv[1], "agent", "agent.json")))
except (OSError, ValueError): a = {}
name = a.get("name") or "Luna"
print(f"You are {name}. {a.get('personality') or ''}".strip())
PY
}

stamp() { date +%Y%m%d-%H%M%S; }
