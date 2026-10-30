// Luna's portrait: her lights take on the room behind her (portrait.match_light).
// When the background picture changes, it's read once at a tiny size: the room's
// overall colour lights her from above, the floor's from below, and its brightest
// spots (candles, a window, a lamp) become her key and rim light. Blended with her
// own white and pink light by match_light (0 = hers only, 1 = the room's), and
// eased over a second and a half. A few numbers on lights she already has: no
// extra memory, nothing extra per frame.
//
// A colour background lights her in that colour; her own gradient, see-through
// (OBS) and the fans keep her own light.

const SIZE = 48;

export function createAmbient({ THREE, hemi, key, rim, amount = 0.6 }) {
  const own = { sky: hemi.color.clone(), ground: hemi.groundColor.clone(), key: key.color.clone(), rim: rim.color.clone(),
                hemi: hemi.intensity, keyI: key.intensity, rimI: rim.intensity };
  let room = null, seen = '', run = 0;
  let mix = Math.max(0, Math.min(1, +amount || 0));

  // a colour turned into a light: its hue, a capped saturation, a set lightness
  const S = THREE.SRGBColorSpace;      // lightness as you'd see it, not in the renderer's linear space
  // Rooms are mostly greys with a cast, so the cast is drawn out (saturation x1.8) before the cap.
  const tint = (c, s, l) => { const h = {}; c.getHSL(h, S); return new THREE.Color().setHSL(h.h, Math.min(h.s * 1.8, s), l, S); };

  function read(img) {
    const cv = Object.assign(document.createElement('canvas'), { width: SIZE, height: Math.max(1, Math.round(SIZE * img.height / img.width)) });
    const g = cv.getContext('2d', { willReadFrequently: true });
    g.drawImage(img, 0, 0, cv.width, cv.height);
    let px;
    try { px = g.getImageData(0, 0, cv.width, cv.height).data; } catch (_) { return null; }   // a picture from elsewhere
    const all = [0, 0, 0], floor = [0, 0, 0], lum = [];
    let nf = 0;
    for (let i = 0, n = 0; i < px.length; i += 4, n++) {
      const r = px[i] / 255, gg = px[i + 1] / 255, b = px[i + 2] / 255, y = 0.2126 * r + 0.7152 * gg + 0.0722 * b;
      all[0] += r; all[1] += gg; all[2] += b;
      if (Math.floor(n / cv.width) >= cv.height * 0.65) { floor[0] += r; floor[1] += gg; floor[2] += b; nf++; }
      lum.push([y, r, gg, b]);
    }
    const count = px.length / 4;
    lum.sort((a, b) => b[0] - a[0]);
    const top = lum.slice(0, Math.max(1, Math.round(count * 0.08)));            // the lights in the room
    const hot = top.reduce((a, p) => [a[0] + p[1], a[1] + p[2], a[2] + p[3]], [0, 0, 0]).map(v => v / top.length);
    const avg = all.map(v => v / count), flo = nf ? floor.map(v => v / nf) : avg;
    const col = v => new THREE.Color().setRGB(v[0], v[1], v[2], S);
    const bright = lum.reduce((a, p) => a + p[0], 0) / count;
    return { sky: tint(col(avg), 0.5, 0.9), ground: tint(col(flo), 0.6, 0.25),
             key: tint(col(hot), 0.55, 0.9), rim: tint(col(hot), 0.85, 0.62), bright };
  }

  function solid(hex) {
    const c = new THREE.Color(hex);
    const hsl = {}; c.getHSL(hsl, S);
    return { sky: tint(c, 0.5, 0.9), ground: tint(c, 0.6, 0.25), key: tint(c, 0.4, 0.9), rim: tint(c, 0.85, 0.62), bright: hsl.l };
  }

  // ease from where the lights are now to what they should be
  function settle() {
    const want = room && mix > 0 ? room : null;
    const lerp = (a, b) => (want ? a.clone().lerp(b, mix) : a.clone());
    const dim = want ? 1 + mix * (Math.max(0.82, Math.min(1.08, 0.78 + want.bright * 0.6)) - 1) : 1;
    const to = { sky: lerp(own.sky, want?.sky), ground: lerp(own.ground, want?.ground), key: lerp(own.key, want?.key),
                 rim: lerp(own.rim, want?.rim), hemi: own.hemi * dim, keyI: own.keyI * dim, rimI: own.rimI };
    const from = { sky: hemi.color.clone(), ground: hemi.groundColor.clone(), key: key.color.clone(), rim: rim.color.clone(),
                   hemi: hemi.intensity, keyI: key.intensity, rimI: rim.intensity };
    const me = ++run, t0 = performance.now(), dur = 1500;
    const step = now => {
      if (me !== run) return;
      const t = Math.min(1, (now - t0) / dur), e = t * t * (3 - 2 * t);
      hemi.color.copy(from.sky).lerp(to.sky, e); hemi.groundColor.copy(from.ground).lerp(to.ground, e);
      key.color.copy(from.key).lerp(to.key, e); rim.color.copy(from.rim).lerp(to.rim, e);
      hemi.intensity = from.hemi + (to.hemi - from.hemi) * e;
      key.intensity = from.keyI + (to.keyI - from.keyI) * e;
      rim.intensity = from.rimI + (to.rimI - from.rimI) * e;
      if (t < 1) requestAnimationFrame(step);
    };
    requestAnimationFrame(step);
  }

  // what's behind her now (boot.js keeps it on the body), read only when it changes
  async function look() {
    const b = document.body, bg = b.style.getPropertyValue('--user-bg').trim();
    const off = !b.classList.contains('custom-bg') || b.classList.contains('clear') ||
                b.classList.contains('transparent') || b.classList.contains('fan');
    const now = off ? '' : bg;
    if (now === seen) return;
    seen = now;
    if (!now) room = null;
    else if (b.classList.contains('solid')) room = solid(now);
    else if (/^url\(/.test(now)) {
      const img = new Image();
      img.src = now.replace(/^url\(["']?/, '').replace(/["']?\)$/, '');
      let ok = true;
      try { await img.decode(); } catch (_) { ok = false; }
      if (seen !== now) return;                                   // changed again while it loaded
      room = ok ? read(img) : null;                               // no picture shows: her own light
    } else room = null;
    settle();
  }

  new MutationObserver(look).observe(document.body, { attributes: true, attributeFilter: ['style', 'class'] });
  look();

  return {
    // 0..1, from /settings or the control panel's slider
    set(v) { mix = Math.max(0, Math.min(1, +v || 0)); settle(); },
    get amount() { return mix; },
    get room() { return room; },
  };
}
