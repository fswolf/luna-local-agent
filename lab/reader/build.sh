#!/usr/bin/env bash
# Build read-acts (the layer reader lab/read.py uses) against the
# llama.cpp that server/llama/install.sh built - same GPU backend, no rebuild of
# llama.cpp itself. server/llama/install.sh runs this too.
set -euo pipefail
HERE="$(cd "$(dirname "$0")" && pwd)"
LLAMA="$(cd "$HERE/../../server/llama" && pwd)"
SRC="$LLAMA/llama.cpp"
BIN="$(cd "$LLAMA/bin" 2>/dev/null && pwd -P)" || { echo "llama.cpp isn't built - run server/llama/install.sh first" >&2; exit 1; }
"${CXX:-c++}" -O2 -std=c++17 "$HERE/read-acts.cpp" -I "$SRC/include" -I "$SRC/ggml/include" \
    -L "$BIN" -lllama -lggml -lggml-base -Wl,-rpath,"$BIN" -o "$BIN/read-acts"
echo "Built $BIN/read-acts"
