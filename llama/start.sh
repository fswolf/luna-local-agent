#!/usr/bin/env bash
# Serve the model with llama.cpp's own server - and, when its model is
# there, the small embedding server beside it. Luna finds both by herself.
#
#   llama/start.sh                 both (embeddings only if the model is found)
#   llama/start.sh --verbose       anything extra goes to the chat server
#
# Chat on :8080 in this terminal; embeddings on :8081 in the background,
# logging to llama/embed.log. Ctrl+C stops both. Settings: server.env.
set -uo pipefail
cd "$(dirname "$(realpath "$0")")" || exit 1

# shellcheck disable=SC1091
source ./server.env

BIN=./bin/llama-server
[ -x "$BIN" ] || { echo "llama-server isn't built yet - run llama/install.sh first." >&2; exit 1; }

# find_model PATTERN -> the one GGUF matching it in llama/models or LM
# Studio's model folders (normal install, old cache, Flatpak). Prints
# why on stderr and fails if there's none, or more than one to choose
# between. mmproj files are vision adapters, never models.
find_model() {
    local pattern="$1" found=()

    mapfile -t found < <(
        find ./models "$HOME/.lmstudio/models" "$HOME/.cache/lm-studio/models" \
             "$HOME/.var/app/ai.lmstudio.lm-studio/.lmstudio/models" \
             -maxdepth 5 -iname "${pattern}.gguf" ! -iname "*mmproj*" \
             2>/dev/null | sort
    )

    if [ "${#found[@]}" -eq 0 ]; then
        echo "No GGUF matching $pattern in llama/models or LM Studio's model folders." >&2
        return 1
    fi

    if [ "${#found[@]}" -gt 1 ]; then
        echo "More than one file matches $pattern - set the path in llama/server.env:" >&2
        printf '  %s\n' "${found[@]}" >&2
        return 1
    fi

    echo "${found[0]}"
}

serving() { curl -fsS --max-time 1 "http://$HOST:$1/health" >/dev/null 2>&1; }

# --- the chat model -------------------------------------------------------
[ -n "$MODEL" ] || MODEL="$(find_model "$MODEL_MATCH")" || {
    echo "Set MODEL= in llama/server.env to the file's full path." >&2; exit 1; }
[ -f "$MODEL" ] || { echo "Model file not found: $MODEL" >&2; exit 1; }
[ -n "$ALIAS" ] || ALIAS="$(basename "$MODEL" .gguf)"

# The vision adapter. LM Studio downloads it beside the model as
# mmproj-*.gguf, so the model's own folder is the first place to look.
MMPROJ="${MMPROJ:-}"
MMPROJ_MATCH="${MMPROJ_MATCH:-}"
if [ "$MMPROJ" = off ]; then
    MMPROJ=""
elif [ -z "$MMPROJ" ]; then
    mapfile -t mm < <(find "$(dirname "$MODEL")" -maxdepth 1 -iname "*mmproj*.gguf" 2>/dev/null | sort)
    if [ "${#mm[@]}" -eq 0 ] && [ -n "$MMPROJ_MATCH" ]; then
        mapfile -t mm < <(find ./models "$HOME/.lmstudio/models" "$HOME/.cache/lm-studio/models" \
                               "$HOME/.var/app/ai.lmstudio.lm-studio/.lmstudio/models" \
                               -maxdepth 5 -iname "${MMPROJ_MATCH}.gguf" -iname "*mmproj*" 2>/dev/null | sort)
    fi
    if [ "${#mm[@]}" -gt 1 ]; then
        echo "More than one mmproj found - set MMPROJ= in llama/server.env:" >&2
        printf '  %s\n' "${mm[@]}" >&2
        exit 1
    fi
    MMPROJ="${mm[0]:-}"
elif [ ! -f "$MMPROJ" ]; then
    echo "MMPROJ in server.env doesn't exist: $MMPROJ" >&2; exit 1
fi

serving "$PORT" && { echo "Something is already serving on $HOST:$PORT." >&2; exit 1; }

# The 16 GB card holds one copy of a 10 GB model, not two.
if curl -fsS --max-time 2 http://localhost:1234/api/v0/models 2>/dev/null |
   grep -q '"state": *"loaded"'; then
    echo "LM Studio has a model loaded - eject it first, or both won't fit in VRAM." >&2
    echo >&2
fi

# The API key. Made once, random, readable only by you; Luna reads the
# same file. Without one, any web page open in your browser can talk to
# a server on localhost - and this one can write files (saved slots)
# and keep the GPU busy. CORS is limited to localhost on top of it.
if [ ! -s .api_key ]; then
    ( umask 077; head -c 32 /dev/urandom | base64 | tr -d '/+=\n' > .api_key )
    echo "Made llama/.api_key - Luna picks it up on her next start." >&2
fi
chmod 600 .api_key
mkdir -p slots

# --- the embedding model, if it's there -----------------------------------
# EMBED=auto starts it when the model is found and says so when it isn't;
# off never starts it; on refuses to start without it.
embed_pid=""
EMBED="${EMBED:-auto}"

if [ "$EMBED" != off ]; then
    why=""

    if [ -z "$EMBED_MODEL" ]; then
        EMBED_MODEL="$(find_model "$EMBED_MATCH" 2>/tmp/.embed_why.$$)" || EMBED_MODEL=""
        why="$(cat /tmp/.embed_why.$$ 2>/dev/null)"; rm -f /tmp/.embed_why.$$
    elif [ ! -f "$EMBED_MODEL" ]; then
        why="EMBED_MODEL in server.env doesn't exist: $EMBED_MODEL"
        EMBED_MODEL=""
    fi

    if [ -z "$EMBED_MODEL" ]; then
        [ "$EMBED" = on ] && { echo "$why" >&2; exit 1; }
        echo "embeddings: off - $why"
        echo "  (fact recall falls back to matching words; EMBED=off in server.env hides this)"
    elif serving "$EMBED_PORT"; then
        echo "embeddings: something is already on :$EMBED_PORT - leaving it be."
    else
        # One fact is a sentence; the whole input must fit one batch, so
        # the batch is the context.
        eargs=(
            -m "$EMBED_MODEL" --alias "$(basename "$EMBED_MODEL" .gguf)"
            --host "$HOST" --port "$EMBED_PORT"
            --embeddings -c "$EMBED_CTX" -b "$EMBED_CTX" -ub "$EMBED_CTX"
            -ngl "$NGL" -t "$THREADS"
            --api-key-file .api_key --cors-origins localhost
        )
        [ -n "$EMBED_POOLING" ] && eargs+=(--pooling "$EMBED_POOLING")

        "$BIN" "${eargs[@]}" > embed.log 2>&1 &
        embed_pid=$!

        # A background job in a script ignores Ctrl+C, so it has to be
        # stopped by hand - on Ctrl+C, on kill, and when the chat server
        # exits by itself. Bash won't reliably run an EXIT trap after an
        # interrupt, hence the separate INT/TERM one.
        stop_embed() { [ -n "$embed_pid" ] && kill "$embed_pid" 2>/dev/null; embed_pid=""; }
        trap stop_embed EXIT
        trap 'stop_embed; exit 130' INT TERM
        echo "embeddings: $(basename "$EMBED_MODEL" .gguf) on http://$HOST:$EMBED_PORT (log: llama/embed.log)"
    fi
fi

# --- the chat server, in the foreground -----------------------------------
args=(
    -m "$MODEL" --alias "$ALIAS"
    --host "$HOST" --port "$PORT"
    -c "$CTX" -ngl "$NGL" -t "$THREADS"
    -b "$BATCH" -ub "$UBATCH"
    -np "$PARALLEL" --ctx-checkpoints "$CTX_CHECKPOINTS"
    -fa auto
    # Tool calling needs the model's own chat template, not a built-in one.
    --jinja
    --reasoning-format "$REASONING_FORMAT" --reasoning-budget "$REASONING_BUDGET"
    # The research side: /metrics, /slots, and somewhere to save a slot's
    # KV cache so a long conversation can be resumed without re-reading it.
    --metrics --slots --slot-save-path ./slots
    --api-key-file .api_key --cors-origins localhost
)

[ "$KV_UNIFIED" = 1 ] && args+=(--kv-unified)
[ -n "$MMPROJ" ] && args+=(--mmproj "$MMPROJ")

# shellcheck disable=SC2206
[ -n "$EXTRA" ] && args+=($EXTRA)

# From the environment rather than server.env: introspection/blind.py
# passes a control vector here for one session without editing a file.
# shellcheck disable=SC2206
[ -n "${EXTRA_ARGS:-}" ] && args+=($EXTRA_ARGS)

echo "chat: $ALIAS"
echo "  $MODEL"
if [ -n "$MMPROJ" ]; then
    echo "  vision: $(basename "$MMPROJ")"
else
    echo "  vision: off - no mmproj next to the model (see MMPROJ in server.env)"
fi
echo "  http://$HOST:$PORT  (Ctrl+C stops both)"
echo

# Not exec: this shell has to outlive the server, to stop the embedding
# one when it goes.
#
# QUIET_LOG sends the server's own output to a file instead of this
# terminal. A blind session needs it: llama-server announces the control
# vector it loaded, which would give the game away.
if [ -n "${QUIET_LOG:-}" ]; then
    echo "  (server output is going to ${QUIET_LOG} - don't read it until you reveal)"
    "$BIN" "${args[@]}" "$@" > "$QUIET_LOG" 2>&1
else
    "$BIN" "${args[@]}" "$@"
fi
