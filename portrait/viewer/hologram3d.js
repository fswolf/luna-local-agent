// The hologram look for the 3D (VRM) portrait: the same projection as
// hologram.js does for Live2D, done as a pass over the rendered frame.
//
// The scene is drawn into a texture first, then one full-screen shader
// turns it into the hologram, so it works on any VRM and everything the
// model already does (blinking, talking, spring bones) comes through:
//
//   tint        her colours pulled towards one hue (mix 0 = untouched)
//   rim         a bright edge where she ends
//   see-through brightness becomes opacity; dark parts nearly vanish
//   scanlines   fine lines rolling up, and a slow brighter band
//   split       a little red/blue fringe at the edges
//   flicker     a constant faint shimmer
//   glitch      now and then (and on a failed tool) rows tear sideways
//   base        the projector: a soft glow at the bottom and a faint beam
//
// Same settings as the Live2D one, config.json under "portrait":
//   "hologram": { "enabled": true, "tint": "#c37bff", "mix": 0.8,
//                 "intensity": 1.0, "glitch": 1.0, "base": true }

const FRAG = `
precision highp float;
varying vec2 vUv;
uniform sampler2D uScene;
uniform vec2 uSize;          // drawing buffer, pixels
uniform float uTime;
uniform float uGlitch;
uniform float uIntensity;
uniform float uMix;
uniform vec3 uTint;
uniform float uBase;

float rand(vec2 p) { return fract(sin(dot(p, vec2(12.9898, 78.233))) * 43758.5453); }

void main() {
  vec2 uv = vUv;
  vec2 px = uv * uSize;
  float k = uSize.y / 560.0;                          // keep effects the same size at any resolution

  // glitch: some rows jump sideways for a moment
  float row = floor(px.y / (5.0 * k));
  float tick = floor(uTime * 24.0);
  float tear = step(1.0 - 0.22 * uGlitch, rand(vec2(row, tick))) * uGlitch;
  uv.x += (rand(vec2(tick, row * 1.7)) - 0.5) * 0.06 * tear;

  vec2 one = 1.0 / uSize;
  vec4 c = texture2D(uScene, uv);
  float sh = (1.5 + 6.0 * tear) * k;
  vec4 cr = texture2D(uScene, uv + vec2(one.x * sh, 0.0));
  vec4 cb = texture2D(uScene, uv - vec2(one.x * sh, 0.0));

  // rim: where the opacity falls away around her
  float d = 3.0 * k;
  float aMin = min(min(texture2D(uScene, uv + vec2(one.x * d, 0.0)).a,
                       texture2D(uScene, uv - vec2(one.x * d, 0.0)).a),
                   min(texture2D(uScene, uv + vec2(0.0, one.y * d)).a,
                       texture2D(uScene, uv - vec2(0.0, one.y * d)).a));
  float rim = clamp((c.a - aMin) * 1.6, 0.0, 1.0);

  // the scene texture is premultiplied over transparent black
  vec3 col = vec3(cr.r / max(cr.a, 0.0001), c.g / max(c.a, 0.0001), cb.b / max(cb.a, 0.0001));
  col = pow(clamp(col, 0.0, 1.0), vec3(1.0 / 2.2));  // to screen colour, like the Live2D one works in
  float lum = dot(col, vec3(0.299, 0.587, 0.114));
  vec3 holo = mix(col, uTint * (0.35 + 1.25 * lum), uMix);
  holo += uTint * rim * 1.4;

  float scan = 0.80 + 0.20 * sin(px.y / k * 1.7 + uTime * 9.0);
  float sweep = exp(-pow((fract(-uv.y * 0.6 + uTime * 0.12) - 0.5) * 9.0, 2.0)) * 0.35;
  float flicker = 0.94 + 0.06 * sin(uTime * 41.0) * sin(uTime * 17.3);

  float a = c.a * (0.36 + 0.42 * lum) * scan * flicker + rim * 0.5;
  a = clamp(a * uIntensity, 0.0, 1.0);
  vec3 outc = holo * (1.0 + sweep) * a;

  // the projector, behind her: a glow at the bottom and a beam widening up
  if (uBase > 0.0) {
    float x = uv.x - 0.5;
    float y = uv.y;                                   // 0 at the bottom
    float beam = step(abs(x), 0.21 + 0.21 * y) * (1.0 - y) * 0.22;
    float glow = exp(-(x * x * 9.0 + y * y * 30.0)) * 0.75;
    float g = (beam + glow) * uBase * (1.0 - a);
    outc += uTint * g;
    a += g;
  }

  gl_FragColor = vec4(outc, a);                       // already screen colour: no conversion
}`;

const VERT = `
varying vec2 vUv;
void main() { vUv = uv; gl_Position = vec4(position.xy, 0.0, 1.0); }`;

function hex(THREE, h) {
  const n = parseInt(String(h || '#c37bff').replace('#', ''), 16);
  return new THREE.Vector3(((n >> 16) & 255) / 255, ((n >> 8) & 255) / 255, (n & 255) / 255);
}

export function createHologram3D(THREE, renderer, opts = {}) {
  const o = Object.assign({ tint: '#c37bff', mix: 0.8, intensity: 1.0, glitch: 1.0, base: true }, opts);
  const size = new THREE.Vector2();
  renderer.getDrawingBufferSize(size);
  const target = new THREE.WebGLRenderTarget(size.x, size.y, {
    type: THREE.HalfFloatType,
    samples: renderer.capabilities.isWebGL2 === false ? 0 : 4,
  });

  const material = new THREE.ShaderMaterial({
    vertexShader: VERT, fragmentShader: FRAG,
    uniforms: {
      uScene: { value: target.texture }, uSize: { value: size.clone() },
      uTime: { value: 0 }, uGlitch: { value: 0 }, uIntensity: { value: o.intensity },
      uMix: { value: +o.mix }, uTint: { value: hex(THREE, o.tint) }, uBase: { value: o.base ? 1 : 0 },
    },
    transparent: true, depthTest: false, depthWrite: false,
    blending: THREE.CustomBlending,                  // the shader writes premultiplied colour
    blendSrc: THREE.OneFactor, blendDst: THREE.OneMinusSrcAlphaFactor,
  });
  const quad = new THREE.Mesh(new THREE.PlaneGeometry(2, 2), material);
  quad.frustumCulled = false;
  const post = new THREE.Scene();
  post.add(quad);
  const postCam = new THREE.OrthographicCamera(-1, 1, 1, -1, 0, 1);

  function resize() {
    renderer.getDrawingBufferSize(size);
    target.setSize(size.x, size.y);
    material.uniforms.uSize.value.copy(size);
  }
  addEventListener('resize', resize);

  // glitch now and then, louder when something went wrong
  const state = { pulse: 0, next: performance.now() / 1000 + 4 + Math.random() * 8, bright: 1 };
  const clear = new THREE.Color();
  let shown = true;

  return {
    isOn() { return shown; },
    glitch(strength = 1) { state.pulse = Math.max(state.pulse, strength * o.glitch); },
    bright(level = 1) { state.bright = level; },
    off() { shown = false; },
    on() { shown = true; },
    set(k, v) {
      if (k === 'tint') material.uniforms.uTint.value = hex(THREE, v);
      if (k === 'mix') material.uniforms.uMix.value = +v;
      if (k === 'intensity') o.intensity = +v;
    },
    render(scene, camera) {
      const now = performance.now() / 1000;
      if (now > state.next) { state.pulse = Math.max(state.pulse, 0.6 * o.glitch); state.next = now + 6 + Math.random() * 10; }
      state.pulse *= 0.86;
      material.uniforms.uTime.value = now % 1000;
      material.uniforms.uGlitch.value = state.pulse > 0.02 ? state.pulse : 0;
      material.uniforms.uIntensity.value = o.intensity * state.bright;

      // the model alone, on transparent black, into the texture
      const oldAlpha = renderer.getClearAlpha();
      renderer.getClearColor(clear);
      renderer.setClearColor(0x000000, 0);
      renderer.setRenderTarget(target);
      renderer.clear();
      renderer.render(scene, camera);
      renderer.setRenderTarget(null);
      renderer.setClearColor(clear, oldAlpha);
      renderer.clear();
      renderer.render(post, postCam);
    },
  };
}
