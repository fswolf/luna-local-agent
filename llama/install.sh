#!/usr/bin/env bash
# Build llama.cpp's server into llama/bin, from source, for this GPU.
#
#   llama/install.sh            Vulkan on Linux (the easy one on AMD),
#                               Metal on a Mac
#   llama/install.sh rocm       ROCm/HIP for the RX 6950 XT (gfx1030)
#   llama/install.sh metal      Apple GPU (any Apple-silicon Mac)
#   llama/install.sh update     pull the latest llama.cpp and rebuild
#
# Both can be built side by side; bin/ points at whichever ran last, so
# switching back is just running the other one again (it's cached).
# llama-bench is built too - run it under each to see which is faster
# on this card before settling.
set -euo pipefail
cd "$(dirname "$(realpath "$0" 2>/dev/null || echo "$0")")"

MAC=""
[ "$(uname -s)" = Darwin ] && MAC=1
KIND="${1:-$([ -n "$MAC" ] && echo metal || echo vulkan)}"
SRC=llama.cpp

if [ "$KIND" = update ]; then
    git -C "$SRC" pull --ff-only
    KIND="$(readlink bin 2>/dev/null | sed -n 's|.*/build-\(.*\)/bin|\1|p')"
    KIND="${KIND:-$([ -n "$MAC" ] && echo metal || echo vulkan)}"
fi

need() {
    local missing=()

    for tool in "$@"; do
        command -v "$tool" >/dev/null || missing+=("$tool")
    done

    if [ "${#missing[@]}" -gt 0 ]; then
        echo "Missing: ${missing[*]}" >&2
        echo "Install them with:" >&2
        echo "  $PKGS" >&2
        exit 1
    fi
}

case "$KIND" in
    vulkan)
        PKGS="sudo dnf install cmake gcc-c++ git glslc vulkan-headers vulkan-loader-devel spirv-headers-devel"
        need cmake g++ git glslc
        FLAGS=(-DGGML_VULKAN=ON)
        ;;
    rocm)
        PKGS="sudo dnf install cmake gcc-c++ git rocm-hip-devel hipblas-devel rocblas-devel rocm-cmake"
        need cmake g++ git hipconfig
        export HIPCXX="$(hipconfig -l)/clang"
        export HIP_PATH="$(hipconfig -R)"
        # gfx1030 is the RX 6950 XT. Nothing else is built, which keeps
        # the build to minutes rather than an hour.
        FLAGS=(-DGGML_HIP=ON -DGPU_TARGETS=gfx1030)
        ;;
    metal)
        # Apple's compiler comes with the Command Line Tools; cmake and a
        # newer bash (start.sh needs it - macOS ships bash 3.2) from Homebrew.
        PKGS="xcode-select --install   # then:  brew install cmake bash   (Homebrew: https://brew.sh)"
        need cmake c++ git
        FLAGS=(-DGGML_METAL=ON)
        ;;
    *)
        echo "usage: llama/install.sh [vulkan|rocm|metal|update]" >&2
        exit 1
        ;;
esac

if [ ! -d "$SRC/.git" ]; then
    git clone --depth 1 https://github.com/ggml-org/llama.cpp "$SRC"
fi

BUILD="$SRC/build-$KIND"

cmake -S "$SRC" -B "$BUILD" -DCMAKE_BUILD_TYPE=Release \
      -DLLAMA_OPENSSL=OFF -DLLAMA_BUILD_TESTS=OFF "${FLAGS[@]}"
JOBS="$(nproc 2>/dev/null || sysctl -n hw.ncpu 2>/dev/null || echo 4)"
cmake --build "$BUILD" --config Release -j"$JOBS" \
      --target llama-server llama-bench llama-cvector-generator

ln -sfn "$BUILD/bin" bin

echo
echo "Built for $KIND: llama/bin/llama-server"
echo "Next: put a model in llama/models (or point MODEL= in llama/server.env at"
echo "one LM Studio downloaded), then llama/start.sh"
if [ -n "$MAC" ] && [ "${BASH_VERSINFO[0]}" -lt 4 ] && ! command -v brew >/dev/null; then
    echo "start.sh needs a newer bash than the Mac's own: brew install bash"
fi
