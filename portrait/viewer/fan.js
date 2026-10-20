// Luna live on a Holoscope WiFi hologram fan (P56, PD42...; holofan.py does the
// talking to it). Each frame: render her with a camera of its own (black
// background, centred, square), then unroll that picture around its centre
// into the fan's own layout - one strip per LED arm, outside-in - on the GPU,
// read it back, JPEG it under 20 KB and post it to the portrait server.
// The layout is p56-studio's transcode.rs (github.com/trackerr/p56-studio).
//
// Runs only while a fan is connected (it asks the server every 2 s) and the
// page is showing; a page with ?nocast never casts.

const SRC = 512;          // the square picture she's rendered into

const FRAG = `
precision highp float;
uniform sampler2D uSrc;
uniform float uS, uRad, uAng, uArms, uH, uCx, uCy, uMaxR, uTurn, uMirror, uSoft;
uniform vec4 uOrder;
float toSrgb(float c) { return c <= 0.0031308 ? 12.92 * c : 1.055 * pow(c, 1.0 / 2.4) - 0.055; }
// Holoscope dims the innermost LEDs (they're closest together): per byte, R G B of LED 0, 1...
float radial(float i) {
  if (i < 3.0 && uSoft > 0.5) return 0.6;
  if (i < 19.0) return 0.73; if (i < 24.0) return 0.74; if (i < 27.0) return 0.77; if (i < 30.0) return 0.80;
  if (i < 33.0) return 0.83; if (i < 36.0) return 0.86; if (i < 39.0) return 0.89; if (i < 42.0) return 0.92;
  if (i < 45.0) return 0.95; if (i < 48.0) return 0.98; return 1.0;
}
void main() {
  float X = floor(gl_FragCoord.x), Yt = uH - 1.0 - floor(gl_FragCoord.y);   // pixel, rows from the top
  float rho, phi; bool swap = false;
  if (uArms > 1.5) {                       // 2 or 4 arms: their strips side by side
    float seg = floor(X / uRad), x = X - seg * uRad, q = uAng / uArms;
    float k = seg < 0.5 ? uOrder.x : seg < 1.5 ? uOrder.y : seg < 2.5 ? uOrder.z : uOrder.w;
    phi = k * q + (q - 1.0 - Yt); rho = uRad - 1.0 - x;
  } else if (uArms > 0.5) {                // 1 arm: radius and rows reversed, BGR
    rho = uRad - 1.0 - X; phi = uAng - 1.0 - Yt; swap = true;
  } else {                                 // older fans: the plain polar picture
    rho = X; phi = Yt;
  }
  float a = phi * 6.283185307 / uAng - uTurn, m = rho * uMaxR / uRad;
  float sx = uCx + m * cos(a), sy = uCy + m * sin(a);
  if (uMirror > 0.5) sx = uS - 1.0 - sx;
  vec3 c = vec3(0.0);
  if (sx >= -0.5 && sy >= -0.5 && sx <= uS - 0.5 && sy <= uS - 0.5) {
    c = texture2D(uSrc, vec2((sx + 0.5) / uS, 1.0 - (sy + 0.5) / uS)).rgb;
    c = vec3(toSrgb(c.r), toSrgb(c.g), toSrgb(c.b));
  }
  c *= vec3(radial(rho * 3.0), radial(rho * 3.0 + 1.0), radial(rho * 3.0 + 2.0));
  if (rho < mod(phi, 8.0)) c = vec3(0.0);  // Holoscope's sawtooth black centre
  gl_FragColor = vec4(swap ? c.bgr : c, 1.0);
}`;

export function createFan({ THREE, renderer, scene, cfg = {}, place }) {
  const id = Math.random().toString(36).slice(2, 10);
  // multisampled so her edges don't stair-step on the fan
  const src = new THREE.WebGLRenderTarget(SRC, SRC, { type: THREE.HalfFloatType, depthBuffer: true, samples: 4 });
  src.texture.generateMipmaps = false;
  const cam = new THREE.PerspectiveCamera(22, 1, 0.05, 20);
  const mat = new THREE.ShaderMaterial({
    fragmentShader: FRAG,
    vertexShader: 'void main() { gl_Position = vec4(position.xy, 0.0, 1.0); }',
    uniforms: Object.fromEntries(['uSrc', 'uS', 'uRad', 'uAng', 'uArms', 'uH', 'uCx', 'uCy', 'uMaxR', 'uTurn',
                                  'uMirror', 'uSoft'].map(k => [k, { value: 0 }]).concat([['uOrder', { value: new THREE.Vector4() }]])),
    depthTest: false, depthWrite: false,
  });
  const quad = new THREE.Mesh(new THREE.PlaneGeometry(2, 2), mat);
  quad.frustumCulled = false;
  const flat = new THREE.Scene(); flat.add(quad);
  const flatCam = new THREE.OrthographicCamera(-1, 1, 1, -1, 0, 1);
  let out = null, pixels = null, canvas = null, ctx = null, img = null, geo = null;
  let status = { connected: false }, busy = false, last = 0, rest = 0, quality = 0.8, sent = 0, polled = 0;
  const color = new THREE.Color();
  const opt = (k, d) => (cfg[k] ?? d);

  async function poll() {
    try { status = await fetch('fan/status').then(r => r.json()); } catch (_) { status = { connected: false }; }
    const g = status.connected ? status.geometry : null;
    if (!g) geo = null;
    else if (!geo || g.type !== geo.type) setGeometry(g);
  }
  function setGeometry(g) {
    geo = g;
    out?.dispose();
    out = new THREE.WebGLRenderTarget(g.width, g.height, { depthBuffer: false });
    pixels = new Uint8Array(g.width * g.height * 4);
    canvas = Object.assign(document.createElement('canvas'), { width: g.width, height: g.height });
    ctx = canvas.getContext('2d');
    img = ctx.createImageData(g.width, g.height);
  }

  // after the page's own render, at most fps times a second
  function update(now) {
    if (now - polled > 2000) { polled = now; poll(); }
    if (!geo || busy || document.hidden || now < rest || now - last < 1000 / Math.max(8, Math.min(25, +opt('fps', 15) || 15))) return;
    last = now;
    busy = true;
    let read;
    try {
      read = draw();
    } catch (e) {
      console.warn('hologram fan:', e);
      busy = false;
      rest = now + 5000;
      return;
    }
    read.then(encode).then(send).catch(e => { console.warn('hologram fan:', e); rest = performance.now() + 5000; })
        .finally(() => { busy = false; });
  }

  // 1. her, on black, centred and square; 2. unrolled into the fan's layout
  function draw() {
    place(cam, opt('framing', 'full'));
    const prevTarget = renderer.getRenderTarget(), prevAlpha = renderer.getClearAlpha();
    renderer.getClearColor(color);
    try {
      renderer.setRenderTarget(src);
      renderer.setClearColor(0x000000, 1);
      renderer.clear();
      renderer.render(scene, cam);
      const u = mat.uniforms, half = Math.floor(SRC / 2);
      u.uSrc.value = src.texture; u.uS.value = SRC;
      u.uRad.value = geo.radius; u.uAng.value = geo.angles; u.uArms.value = geo.arms; u.uH.value = geo.height;
      u.uCx.value = half + (+opt('x', 0) || 0) * SRC; u.uCy.value = half + (+opt('y', 0) || 0) * SRC;
      u.uMaxR.value = (half + 0.5) * Math.max(0.05, +opt('scale', 1) || 1);
      u.uTurn.value = ((+opt('rotation', 0) || 0) % 360) * Math.PI / 180;
      u.uMirror.value = opt('mirror', false) ? 1 : 0; u.uSoft.value = geo.soft ? 1 : 0;
      u.uOrder.value.fromArray(geo.order.concat([0, 0, 0, 0]));
      renderer.setRenderTarget(out);
      renderer.render(flat, flatCam);
    } finally {
      renderer.setRenderTarget(prevTarget);
      renderer.setClearColor(color, prevAlpha);
    }
    // read back without stalling the page's own drawing, where three.js can
    const g = geo, target = out, buf = pixels;
    if (renderer.readRenderTargetPixelsAsync)
      return renderer.readRenderTargetPixelsAsync(target, 0, 0, g.width, g.height, buf).then(() => g);
    renderer.readRenderTargetPixels(target, 0, 0, g.width, g.height, buf);
    return Promise.resolve(g);
  }

  // 3. Holoscope's auto brightness (fans are dim: it lifts a dark picture,
  // up to a mean of 150), rows top-down, JPEG under the size limit
  function encode(g) {
    if (g !== geo) throw new Error('the fan changed');
    const { width: w, height: h } = g, d = img.data;
    let sum = 0;
    for (let i = 0; i < pixels.length; i += 4) sum += 0.299 * pixels[i] + 0.587 * pixels[i + 1] + 0.114 * pixels[i + 2];
    const mean = sum / (w * h), boost = +opt('gain', g.gain) || g.gain;
    const k = mean < 1 ? 1 : Math.min(mean * boost, g.cap) / mean;
    for (let y = 0; y < h; y++) {
      const from = (h - 1 - y) * w * 4, to = y * w * 4;
      for (let i = 0; i < w * 4; i += 4) {
        d[to + i] = pixels[from + i] * k; d[to + i + 1] = pixels[from + i + 1] * k;
        d[to + i + 2] = pixels[from + i + 2] * k; d[to + i + 3] = 255;
      }
    }
    ctx.putImageData(img, 0, 0);
    return g;
  }
  const jpeg = q => new Promise(res => canvas.toBlob(res, 'image/jpeg', q));
  async function send(g) {
    let blob = await jpeg(quality);
    while (blob && blob.size > g.max_jpeg && quality > 0.05) { quality *= 0.85; blob = await jpeg(quality); }
    if (!blob || blob.size > g.max_jpeg) return;
    if (blob.size < g.max_jpeg * 0.7 && quality < 0.8) quality = Math.min(0.8, quality * 1.05);   // creep back up
    const r = await fetch('fan/frame', { method: 'POST', body: blob, headers: { 'Content-Type': 'image/jpeg', 'X-Fan-Sender': id } });
    const j = await r.json().catch(() => ({}));
    sent++;
    // another page has the fan (or it just left): rest a while instead of drawing for nobody
    if (j.active === false) rest = performance.now() + 3000;
  }
  return { update, status: () => ({ ...status, sent, quality: +quality.toFixed(2) }) };
}
