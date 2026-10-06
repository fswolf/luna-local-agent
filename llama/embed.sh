#!/usr/bin/env bash
# The embedding server: lets Luna recall facts by meaning instead of by
# shared words. Optional - without it she matches words like before.
# A small model (~0.6 GB of VRAM), so it runs beside llama/start.sh or
# beside LM Studio, on :8081.
#
# Get the model once, either way - this finds it in both places:
#   in LM Studio, search "Qwen3-Embedding-0.6B" and download the Q8_0 GGUF
#   or: mkdir -p llama/models && curl -L -o llama/models/Qwen3-Embedding-0.6B-Q8_0.gguf \
#       https://huggingface.co/Qwen/Qwen3-Embedding-0.6B-GGUF/resolve/main/Qwen3-Embedding-0.6B-Q8_0.gguf
set -uo pipefail
cd "$(dirname "$(realpath "$0")")" || exit 1

# shellcheck disable=SC1091
source ./server.env
# shellcheck disable=SC1091
source ./common.sh

BIN=./bin/llama-server
[ -x "$BIN" ] || { echo "llama-server isn't built yet - run llama/install.sh first." >&2; exit 1; }

[ -n "$EMBED_MODEL" ] || EMBED_MODEL="$(find_model "$EMBED_MATCH")" || exit 1
[ -f "$EMBED_MODEL" ] || { echo "Model file not found: $EMBED_MODEL" >&2; exit 1; }

check_free "$HOST" "$EMBED_PORT"
ensure_key

echo "embeddings: $(basename "$EMBED_MODEL" .gguf)"
echo "  http://$HOST:$EMBED_PORT  (Ctrl+C stops it)"
echo

# One fact is a sentence; the whole input has to fit one batch, so the
# batch is the context. Pooling comes from the model unless set.
args=(
    -m "$EMBED_MODEL" --alias "$(basename "$EMBED_MODEL" .gguf)"
    --host "$HOST" --port "$EMBED_PORT"
    --embeddings -c "$EMBED_CTX" -b "$EMBED_CTX" -ub "$EMBED_CTX"
    -ngl "$NGL" -t "$THREADS"
    --api-key-file .api_key --cors-origins localhost
)

[ -n "$EMBED_POOLING" ] && args+=(--pooling "$EMBED_POOLING")

exec "$BIN" "${args[@]}" "$@"
