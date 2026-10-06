#!/usr/bin/env bash
# Rebuild the two vendored bundles, so the portrait works offline with no
# build step at run time:
#   luna-three.js  three.js + GLTFLoader + three-vrm       (3D / VRM models)
#   luna-pixi.js   pixi.js 6 + pixi-live2d-display 0.4     (Live2D models)
#   portrait/vendor/build.sh            (needs node/npm, once)
set -euo pipefail
VENDOR="$(cd "$(dirname "$0")" && pwd)"
tmp=$(mktemp -d); trap 'rm -rf "$tmp"' EXIT
cd "$tmp"
npm init -y >/dev/null
npm install --silent three @pixiv/three-vrm pixi.js@6.5.10 pixi-live2d-display@0.4.0 esbuild

cat > entry.js <<'JS'
export * as THREE from 'three';
export { GLTFLoader } from 'three/examples/jsm/loaders/GLTFLoader.js';
export { VRMLoaderPlugin, VRMUtils, VRMExpressionPresetName, VRMHumanBoneName } from '@pixiv/three-vrm';
JS
npx esbuild entry.js --bundle --format=esm --minify --legal-comments=eof --outfile=out.js
three=$(node -p "require('three/package.json').version")
vrm=$(node -p "require('@pixiv/three-vrm/package.json').version")
{ printf '/* three.js %s (MIT) and @pixiv/three-vrm %s (MIT), bundled by build.sh. */\n' "$three" "$vrm"; cat out.js; } \
    > "$VENDOR/luna-three.js"

cat > entry2d.js <<'JS'
import * as PIXI from 'pixi.js';
import { Live2DModel } from 'pixi-live2d-display/cubism4';
window.PIXI = PIXI;
Live2DModel.registerTicker(PIXI.Ticker);
export { PIXI, Live2DModel };
JS
npx esbuild entry2d.js --bundle --format=esm --minify --legal-comments=eof --outfile=out2d.js
{ printf '/* pixi.js 6.5.10 (MIT) and pixi-live2d-display 0.4.0 (MIT), bundled by build.sh.\n   Needs Live2D Cubism Core loaded first (boot.js does it). */\n'; cat out2d.js; } \
    > "$VENDOR/luna-pixi.js"
echo "rebuilt luna-three.js (three $three, three-vrm $vrm) and luna-pixi.js"
