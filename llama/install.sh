#!/usr/bin/env bash
# Build llama.cpp's server into llama/bin, from source, for this GPU.
#
#   llama/install.sh            Vulkan - the default, and the easy one on AMD
#   llama/install.sh rocm       ROCm/HIP for the RX 6950 XT (gfx1030)
#   llama/install.sh update     pull the latest llama.cpp and rebuild
#
# Both can be built side by side; bin/ points at whichever ran last, so
# switching back is just running the other one again (it's cached).
# llama-bench is built too - run it under each to see which is faster
# on this card before settling.
set -euo pipefail
cd "$(dirname "$(realpath "$0")")"

KIND="${1:-vulkan}"
SRC=llama.cpp

if [ "$KIND" = update ]; then
    git -C "$SRC" pull --ff-only
    KIND="$(readlink bin 2>/dev/null | sed -n 's|.*/build-\(.*\)/bin|\1|p')"
    KIND="${KIND:-vulkan}"
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
    *)
        echo "usage: llama/install.sh [vulkan|rocm|update]" >&2
        exit 1
        ;;
esac

if [ ! -d "$SRC/.git" ]; then
    git clone --depth 1 https://github.com/ggml-org/llama.cpp "$SRC"
fi

BUILD="$SRC/build-$KIND"

cmake -S "$SRC" -B "$BUILD" -DCMAKE_BUILD_TYPE=Release \
      -DLLAMA_OPENSSL=OFF -DLLAMA_BUILD_TESTS=OFF "${FLAGS[@]}"
cmake --build "$BUILD" --config Release -j"$(nproc)" \
      --target llama-server llama-bench

ln -sfn "$BUILD/bin" bin

echo
echo "Built for $KIND: llama/bin/llama-server"
echo "Next: llama/start.sh"
