#!/usr/bin/env bash
# Train one of her patches overnight, by hand (docs/patches.md).
#
#   training/train.sh gesture        or  habit
#   training/train.sh gesture --check   only check everything's in place
#
# 1. exports the approved examples (python3 -m training.export)
# 2. builds the trainer container once (training/Containerfile: Unsloth, ROCm)
# 3. trains on the GPU (training/train.py) - Luna and llama-server off
# 4. turns the result into a GGUF patch in llama/patches/, with a .json
#    beside it saying which model it's for
# Then restart llama/start.sh: it loads the patches made for the model it
# starts, and leaves the rest out. Settings: training/train.env.
set -euo pipefail
cd "$(dirname "$(realpath "$0" 2>/dev/null || echo "$0")")/.." || exit 1
ROOT="$PWD"

KIND="${1:-}"
CHECK=""
[ "${2:-}" = "--check" ] && CHECK=1
case "$KIND" in
    gesture|habit) ;;
    *) echo "usage: training/train.sh gesture|habit [--check]" >&2; exit 2 ;;
esac

# shellcheck disable=SC1091
source training/train.env

fail() { echo "$*" >&2; exit 1; }
# with --check, a missing piece is listed and the check goes on
problems=()
lack() { if [ -n "$CHECK" ]; then problems+=("$*"); else fail "$*"; fi; }

# Luna's own Python (the export reads her settings), as start.sh finds it
PY=python3
for py in "$(python3 -c 'import json;print(json.load(open("install.json")).get("venv_python",""))' 2>/dev/null)" \
          "${VIRTUAL_ENV:-}/bin/python" ~/ai-voice-venv/bin/python ./ai-voice-venv/bin/python ./venv/bin/python ./.venv/bin/python; do
    if [ -n "$py" ] && [ -x "$py" ]; then PY="$py"; break; fi
done

# --- what it's for ---------------------------------------------------------
[ -n "$BASE" ] || lack "Set BASE in training/train.env: the safetensors version of the model she runs (a Hugging Face id or a folder)."
if [ -z "$FOR_MODEL" ]; then
    FOR_MODEL="$(cat llama/patches/.current_model 2>/dev/null || true)"
    [ -n "$FOR_MODEL" ] || lack "Don't know which GGUF this is for: start llama/start.sh once (it notes the model), or set FOR_MODEL."
fi
echo "patch: $KIND, for $FOR_MODEL"
echo "  trained on: $BASE"

# --- the GPU has to be free -------------------------------------------------
# llama/start.sh's ports (from its settings) and LM Studio's: anything still
# holding a model takes VRAM the training needs.
ports="$( (cat llama/server.env llama/server.local.env 2>/dev/null || true) | sed -n 's/^\(PORT\|EMBED_PORT\|RERANK_PORT\)=\([0-9]*\).*/\2/p' | sort -u)"
busy=()
for port in ${ports:-8080 8081 8082}; do
    if curl -fsS --max-time 1 "http://127.0.0.1:$port/health" >/dev/null 2>&1; then busy+=(":$port"); fi
done
if (curl -fsS --max-time 1 http://localhost:1234/api/v0/models 2>/dev/null || true) | grep -q '"state": *"loaded"'; then
    busy+=("LM Studio")
fi
if [ "${#busy[@]}" -gt 0 ] && [ -z "${FORCE:-}" ]; then
    lack "Still holding the GPU: ${busy[*]}. Stop llama/start.sh (and Luna, LM Studio) first, or FORCE=1 to try anyway."
fi
[ -e /dev/kfd ] || lack "No /dev/kfd: the ROCm driver isn't there (an AMD card on Linux is needed for this)."

# --- the container engine ---------------------------------------------------
if [ -z "$ENGINE" ]; then
    if command -v podman >/dev/null; then ENGINE=podman
    elif command -v docker >/dev/null; then ENGINE=docker
    else lack "Needs podman or docker to run the trainer in."; ENGINE=none; fi
fi
# the GPU's device files belong to the video and render groups; SELinux
# (Fedora) would otherwise refuse the container them. Your repo's own
# labels are left alone (no :z relabelling).
groups_arg=(--group-add video --security-opt label=disable)
getent group render >/dev/null 2>&1 && groups_arg+=(--group-add render)
[ "$ENGINE" = podman ] && groups_arg=(--group-add keep-groups --security-opt label=disable)
# docker runs as root unless told: the patch and the run folder would end up
# root's. Podman (rootless) is you already.
[ "$ENGINE" = docker ] && groups_arg+=(--user "$(id -u):$(id -g)" -e HOME=/tmp)

# the base: a folder is mounted in, an id is downloaded into the HF cache
base_mount=() base_in="$BASE"
if [ -d "$BASE" ]; then
    base_mount=(-v "$(realpath "$BASE"):/base:ro")
    base_in=/base
fi
mkdir -p "$HOME/.cache/huggingface" llama/patches

# --- the examples -----------------------------------------------------------
"$PY" -m training.export "$KIND" || lack "No approved $KIND examples to train on yet."
TRAIN="agent/dataset/export/$KIND-train.jsonl"
N="$(grep -c . "$TRAIN" 2>/dev/null || true)"

if [ -n "$CHECK" ]; then
    echo "check: $N examples to train on"
    echo "  engine $ENGINE, image $IMAGE: $($ENGINE image inspect "$IMAGE" >/dev/null 2>&1 && echo built || echo 'not built yet (the first run builds it)')"
    echo "  base: $([ -d "$BASE" ] && echo "folder $BASE" || echo "Hugging Face $BASE (downloaded on the first run)")"
    echo "  converter: $([ -f llama/llama.cpp/convert_lora_to_gguf.py ] && echo llama/llama.cpp || echo 'fetched on the first run')"
    if [ "${#problems[@]}" -gt 0 ]; then
        printf 'not ready:\n'; printf '  %s\n' "${problems[@]}"; exit 1
    fi
    echo "ready."
    exit 0
fi

# --- build the trainer once -------------------------------------------------
if ! $ENGINE image inspect "$IMAGE" >/dev/null 2>&1; then
    echo "building the trainer image ($IMAGE, PyTorch $ROCM) - once, takes a while..."
    $ENGINE build --build-arg "ROCM=$ROCM" -t "$IMAGE" -f training/Containerfile training
fi

slug() { echo "$1" | tr '[:upper:]' '[:lower:]' | tr -c 'a-z0-9\n' '-' | sed 's/--*/-/g; s/^-//; s/-$//' | cut -c1-40; }
NAME="$KIND-$(slug "$FOR_MODEL")-$(date +%Y-%m-%d)-n$N"
[ -e "llama/patches/$NAME.gguf" ] && NAME="$NAME-$(date +%H%M)"      # a second run the same day keeps the first
RUN="agent/dataset/runs/$NAME"
mkdir -p "$RUN"

tty_arg=()
[ -t 0 ] && tty_arg=(-it)          # left to run overnight (nohup), there's no terminal
run() {
    $ENGINE run --rm "${tty_arg[@]}" --device /dev/kfd --device /dev/dri "${groups_arg[@]}" \
        --security-opt seccomp=unconfined --ipc=host \
        -v "$ROOT:/work" -v "$HOME/.cache/huggingface:/hf" -e HF_HOME=/hf "${base_mount[@]}" \
        -w "/work/$RUN" \
        ${HSA_OVERRIDE_GFX_VERSION:+-e HSA_OVERRIDE_GFX_VERSION="$HSA_OVERRIDE_GFX_VERSION"} \
        "$IMAGE" "$@"
}

# --- train ------------------------------------------------------------------
echo "training $NAME on $N examples (rank $RANK, $EPOCHS passes)..."
run python3 /work/training/train.py --kind "$KIND" --base "$base_in" --train "/work/$TRAIN" \
    --out "/work/$RUN" --rank "$RANK" --epochs "$EPOCHS" --lr "$LR" --max-len "$MAX_LEN" --load-4bit "$LOAD_4BIT"

# --- into a GGUF patch ------------------------------------------------------
# llama.cpp's own converter: the copy llama/install.sh built from, or a
# fresh one fetched into agent/dataset/ just for this.
CONV=llama/llama.cpp
if [ ! -f "$CONV/convert_lora_to_gguf.py" ]; then
    CONV=agent/dataset/llama.cpp
    [ -f "$CONV/convert_lora_to_gguf.py" ] || git clone --depth 1 https://github.com/ggml-org/llama.cpp "$CONV"
fi
base_arg=(--base "$base_in")
[ -d "$BASE" ] || base_arg=(--base-model-id "$BASE")
run env PYTHONPATH="/work/$CONV/gguf-py" python3 "/work/$CONV/convert_lora_to_gguf.py" \
    "${base_arg[@]}" --outtype f16 --outfile "/work/llama/patches/$NAME.gguf" "/work/$RUN"

"$PY" - "$RUN/luna-patch.json" "llama/patches/$NAME.json" "$FOR_MODEL" <<'PY'
import json, sys
meta = json.load(open(sys.argv[1]))
meta["for"] = sys.argv[3]
json.dump(meta, open(sys.argv[2], "w"), indent=1)
PY

echo
echo "Done: llama/patches/$NAME.gguf"
echo "Restart llama/start.sh to load it (PATCHES in llama/server.env), then try it:"
echo "  /patches             what's loaded"
echo "  /patches $KIND 0.5   half strength while you compare; 0 turns it off"
