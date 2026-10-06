#!/usr/bin/env bash
# Live2D's Cubism Core, for running Live2D portraits offline. Without it
# the portrait loads it from Live2D's CDN each time. It's Live2D's own
# code under their licence (https://www.live2d.com/eula/), which is why
# it's fetched rather than shipped in this repo.
set -euo pipefail
cd "$(dirname "$0")"
curl -fsSLo live2dcubismcore.min.js https://cubism.live2d.com/sdk-web/cubismcore/live2dcubismcore.min.js
echo "saved $(pwd)/live2dcubismcore.min.js"
