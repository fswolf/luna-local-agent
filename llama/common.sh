# Shared by start.sh and embed.sh - sourced, not run.

# find_model PATTERN -> the one GGUF matching it in llama/models or LM
# Studio's model folders (the normal install, the old cache, the
# Flatpak), or an
# explanation and exit. mmproj files are vision adapters, never models.
find_model() {
    local pattern="$1" found=()

    mapfile -t found < <(
        find ./models "$HOME/.lmstudio/models" "$HOME/.cache/lm-studio/models" \
             "$HOME/.var/app/ai.lmstudio.lm-studio/.lmstudio/models" \
             -maxdepth 5 -iname "${pattern}.gguf" ! -iname "*mmproj*" \
             2>/dev/null | sort
    )

    if [ "${#found[@]}" -eq 0 ]; then
        echo "No GGUF matching $pattern in LM Studio's model folders." >&2
        echo "Looked in llama/models, ~/.lmstudio/models, ~/.cache/lm-studio/models and the Flatpak's." >&2
        echo "Set the full path in llama/server.env instead." >&2
        exit 1
    fi

    if [ "${#found[@]}" -gt 1 ]; then
        echo "More than one file matches $pattern - set the path in llama/server.env:" >&2
        printf '  %s\n' "${found[@]}" >&2
        exit 1
    fi

    echo "${found[0]}"
}

# The API key. Made once, random, readable only by you; Luna reads the
# same file. Without one, any web page open in your browser can talk to
# a server on localhost - and this one can write files (saved slots)
# and keep the GPU busy. CORS is limited to localhost on top of it.
ensure_key() {
    if [ ! -s .api_key ]; then
        umask 077
        head -c 32 /dev/urandom | base64 | tr -d '/+=\n' > .api_key
        echo "Made llama/.api_key - Luna picks it up on her next start." >&2
    fi

    chmod 600 .api_key
}

check_free() {
    if curl -fsS --max-time 1 "http://$1:$2/health" >/dev/null 2>&1; then
        echo "Something is already serving on $1:$2." >&2
        exit 1
    fi
}
