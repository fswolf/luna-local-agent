// The hologram look for the Live2D portrait: Luna as a projection.
//
// A PIXI filter over the whole model, so it works on any Live2D model and
// everything the model already does (blinking, talking, physics) comes
// through it. What it does, per pixel:
//
//   tint       her colours pulled towards one hue (mix 0 = untouched)
//   rim        a bright edge where she ends, the thing that sells it
//   see-through brightness becomes opacity; dark parts nearly vanish
//   scanlines  fine lines rolling up, and a slow brighter band
//   split      a little red/blue fringe at the edges
//   flicker    a constant faint shimmer
//   glitch     now and then (and on a failed tool) rows tear sideways
//
// Plus a projector: a soft glow under her and a faint beam up.
//
// config.json, under "portrait":
//   "hologram": { "enabled": true, "tint": "#c37bff", "mix": 0.8,
//                 "intensity": 1.0, "glitch": 1.0, "base": true }
// ?holo=1 / ?holo=0 on the page URL overrides "enabled".

const FRAG = `
precision highp float;
varying vec2 vTextureCoord;
uniform sampler2D uSampler;
uniform vec4 inputSize;
uniform vec4 outputFrame;
uniform float uTime;
uniform float uGlitch;
uniform float uIntensity;
uniform float uMix;
uniform vec3 uTint;
uniform float uScreenH;

float rand(vec2 p) { return fract(sin(dot(p, vec2(12.9898, 78.233))) * 43758.5453); }

void main() {
  vec2 uv = vTextureCoord;
  vec2 px = uv * inputSize.xy + outputFrame.xy;      // screen pixels

  // glitch: some rows jump sideways for a moment
  float row = floor(px.y / 5.0);
  float tick = floor(uTime * 24.0);
  float tear = step(1.0 - 0.22 * uGlitch, rand(vec2(row, tick))) * uGlitch;
  uv.x += (rand(vec2(tick, row * 1.7)) - 0.5) * 0.06 * tear;

  vec2 one = inputSize.zw;                            // one pixel in uv
  vec4 c = texture2D(uSampler, uv);
  float r = texture2D(uSampler, uv + vec2(one.x * (1.5 + 6.0 * tear), 0.0)).r;
  float b = texture2D(uSampler, uv - vec2(one.x * (1.5 + 6.0 * tear), 0.0)).b;

  // rim: where the opacity falls away around her
  float aMin = min(min(texture2D(uSampler, uv + vec2(one.x * 3.0, 0.0)).a,
                       texture2D(uSampler, uv - vec2(one.x * 3.0, 0.0)).a),
                   min(texture2D(uSampler, uv + vec2(0.0, one.y * 3.0)).a,
                       texture2D(uSampler, uv - vec2(0.0, one.y * 3.0)).a));
  float rim = clamp((c.a - aMin) * 1.6, 0.0, 1.0);

  vec3 col = vec3(r, c.g, b) / max(c.a, 0.0001);      // PIXI hands us premultiplied colour
  float lum = dot(col, vec3(0.299, 0.587, 0.114));
  vec3 holo = mix(col, uTint * (0.35 + 1.25 * lum), uMix);
  holo += uTint * rim * 1.4;

  float scan = 0.80 + 0.20 * sin(px.y * 1.7 - uTime * 9.0);
  float sweep = exp(-pow((fract(px.y / uScreenH * 0.6 + uTime * 0.12) - 0.5) * 9.0, 2.0)) * 0.35;
  float flicker = 0.94 + 0.06 * sin(uTime * 41.0) * sin(uTime * 17.3);

  float a = c.a * (0.36 + 0.42 * lum) * scan * flicker + rim * 0.5;
  a = clamp(a * uIntensity, 0.0, 1.0);
  gl_FragColor = vec4(holo * (1.0 + sweep) * a, a);
}`;

function hex(h) {
  const n = parseInt(String(h || '#c37bff').replace('#', ''), 16);
  return [((n >> 16) & 255) / 255, ((n >> 8) & 255) / 255, (n & 255) / 255];
}

export function createHologram(PIXI, app, model, opts = {}) {
  const o = Object.assign({ tint: '#c37bff', mix: 0.8, intensity: 1.0, glitch: 1.0, base: true }, opts);
  const filter = new PIXI.Filter(undefined, FRAG, {
    uTime: 0, uGlitch: 0, uIntensity: o.intensity, uMix: o.mix, uTint: hex(o.tint), uScreenH: innerHeight,
  });
  filter.padding = 6;
  model.filters = [filter];

  // the projector: a glow at the bottom of the window and a faint beam
  let base = null;
  if (o.base) {
    const cv = document.createElement('canvas');
    cv.width = 512; cv.height = 512;
    const g = cv.getContext('2d');
    const [tr, tg, tb] = hex(o.tint).map(v => Math.round(v * 255));
    const beam = g.createLinearGradient(0, 512, 0, 0);
    beam.addColorStop(0, `rgba(${tr},${tg},${tb},0.22)`);
    beam.addColorStop(1, `rgba(${tr},${tg},${tb},0)`);
    g.fillStyle = beam;
    g.beginPath(); g.moveTo(150, 512); g.lineTo(362, 512); g.lineTo(470, 0); g.lineTo(42, 0); g.closePath(); g.fill();
    const glow = g.createRadialGradient(256, 500, 4, 256, 500, 170);
    glow.addColorStop(0, `rgba(${tr},${tg},${tb},0.75)`);
    glow.addColorStop(1, `rgba(${tr},${tg},${tb},0)`);
    g.fillStyle = glow;
    g.fillRect(0, 300, 512, 212);
    base = new PIXI.Sprite(PIXI.Texture.from(cv));
    base.blendMode = PIXI.BLEND_MODES.ADD;
    app.stage.addChildAt(base, 0);
  }

  function layout() {
    filter.uniforms.uScreenH = innerHeight;
    if (base) {
      base.width = innerWidth * 1.1;
      base.height = innerHeight * 0.9;
      base.x = innerWidth * -0.05;
      base.y = innerHeight * 0.1;
    }
  }
  layout();
  addEventListener('resize', layout);

  // glitch now and then, louder when something went wrong
  const state = { pulse: 0, next: performance.now() / 1000 + 4 + Math.random() * 8, bright: 1 };
  app.ticker.add(() => {
    const now = performance.now() / 1000;
    if (now > state.next) { state.pulse = Math.max(state.pulse, 0.6 * o.glitch); state.next = now + 6 + Math.random() * 10; }
    state.pulse *= 0.86;
    filter.uniforms.uTime = now % 1000;
    filter.uniforms.uGlitch = state.pulse > 0.02 ? state.pulse : 0;
    filter.uniforms.uIntensity = o.intensity * state.bright;
  });

  let shown = true;
  return {
    isOn() { return shown; },
    glitch(strength = 1) { state.pulse = Math.max(state.pulse, strength * o.glitch); },
    bright(level = 1) { state.bright = level; },
    off() { shown = false; model.filters = null; if (base) base.visible = false; },
    on() { shown = true; model.filters = [filter]; if (base) base.visible = true; },
    set(k, v) {
      if (k === 'tint') filter.uniforms.uTint = hex(v);
      if (k === 'mix') filter.uniforms.uMix = +v;
      if (k === 'intensity') o.intensity = +v;
    },
  };
}
