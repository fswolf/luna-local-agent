#!/usr/bin/env bash
# Build llama.cpp's server into llama/bin, from source, for this GPU.
#
#   llama/install.sh            Vulkan on Linux (the easy one on AMD),
#                               Metal on a Mac
#   llama/install.sh rocm       ROCm/HIP, for the AMD card(s) rocminfo finds
#                               (GPU_TARGETS=gfx1100 to pick by hand)
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

# Which package manager, so a missing piece comes with the line that
# installs it on this system rather than on Fedora's.
PM=""
for p in dnf apt-get pacman zypper brew; do
    command -v "$p" >/dev/null && { PM="$p"; break; }
done

stop() {
    echo "$1" >&2
    case "$PKGS" in
        "") ;;
        sudo*|xcode*) echo "Install them with:" >&2; echo "  $PKGS" >&2 ;;
        *) echo "It needs $PKGS." >&2 ;;
    esac
    exit 1
}

need() {
    local missing=()

    for tool in "$@"; do
        command -v "$tool" >/dev/null || missing+=("$tool")
    done
    [ "${#missing[@]}" -eq 0 ] || stop "Missing: ${missing[*]}"
}

# header FILE -> found in any of the usual include folders. cmake only
# finds these halfway through and says "Could NOT find Vulkan", which
# doesn't say what to install.
header() {
    local d
    for d in /usr/include /usr/local/include /opt/homebrew/include ${VULKAN_SDK:+"$VULKAN_SDK/include"}; do
        [ -f "$d/$1" ] && return 0
    done
    return 1
}

case "$KIND" in
    vulkan)
        case "$PM" in
            dnf)     PKGS="sudo dnf install cmake gcc-c++ git glslc vulkan-headers vulkan-loader-devel spirv-headers-devel" ;;
            apt-get) PKGS="sudo apt-get install cmake g++ git glslc libvulkan-dev spirv-headers" ;;
            pacman)  PKGS="sudo pacman -S --needed cmake gcc git shaderc vulkan-headers vulkan-icd-loader spirv-headers" ;;
            zypper)  PKGS="sudo zypper install cmake gcc-c++ git shaderc vulkan-devel spirv-headers" ;;
            *)       PKGS="cmake, a C++ compiler, git, glslc (shaderc), and the Vulkan and SPIR-V headers" ;;
        esac
        need cmake g++ git glslc
        header vulkan/vulkan.h || stop "Missing: the Vulkan headers"
        header spirv/unified1/spirv.hpp || stop "Missing: the SPIR-V headers"
        FLAGS=(-DGGML_VULKAN=ON)
        ;;
    rocm)
        case "$PM" in
            dnf) PKGS="sudo dnf install cmake gcc-c++ git rocm-hip-devel hipblas-devel rocblas-devel rocm-cmake" ;;
            *)   PKGS="cmake, a C++ compiler, git and ROCm's HIP, hipBLAS and rocBLAS development packages" ;;
        esac
        need cmake g++ git hipconfig
        export HIPCXX="$(hipconfig -l)/clang"
        export HIP_PATH="$(hipconfig -R)"
        # Only this machine's cards are built, which keeps the build to
        # minutes rather than an hour. GPU_TARGETS=gfx1100 picks by hand.
        TARGETS="${GPU_TARGETS:-}"
        if [ -z "$TARGETS" ]; then
            TARGETS="$( { amdgpu-arch 2>/dev/null || rocminfo 2>/dev/null; } \
                        | grep -o 'gfx[0-9a-f]\+' | grep -v '^gfx000$' | sort -u | paste -sd ';' -)"
        fi
        [ -n "$TARGETS" ] || { PKGS=""; stop "Couldn't tell which AMD GPU this is (rocminfo found none).
Name it yourself, e.g.:  GPU_TARGETS=gfx1100 llama/install.sh rocm
(gfx1100 is the RX 7900 series, gfx1030 the RX 6800/6900 series)"; }
        echo "building for: $TARGETS"
        FLAGS=(-DGGML_HIP=ON "-DGPU_TARGETS=$TARGETS")
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

# read-acts: the introspection lab's layer reader (introspection/read.py).
# Only the lab needs it, so a failure here never stops the install.
if [ -f ../introspection/reader/build.sh ]; then
    bash ../introspection/reader/build.sh || echo "read-acts didn't build - only introspection/read.py needs it"
fi

echo
echo "Built for $KIND: llama/bin/llama-server"
echo "Next: put a model in llama/models (or point MODEL= in llama/server.env at"
echo "one LM Studio downloaded). ./start.sh starts it with Luna; llama/start.sh"
echo "runs it on its own."
if [ -n "$MAC" ] && [ "${BASH_VERSINFO[0]}" -lt 4 ] && ! command -v brew >/dev/null; then
    echo "start.sh needs a newer bash than the Mac's own: brew install bash"
fi
