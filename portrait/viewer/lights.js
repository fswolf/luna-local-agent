// Her light strips: the LED paint on a robot model glows, in her mood's
// colour, and reacts - dark at rest, pulsing with her voice, a sweep
// down her body while she thinks, a flicker when a tool fails, the part
// you touch lighting up.
//
// The maps come from portrait/lights.py, in a lights/ folder beside the
// model: per material a glow map (white = lit) and a zone map (which part
// of her a pixel is), plus lights.json. A model without that folder has no
// lights. The glow around each strip is worked out here from the glow map,
// so a hand-painted strip gets one too.
//
// Settings (config.json portrait.lights, live):
//   enabled     off by default
//   color       "" (follows her mood), "own" (the paint's colour), or #hex
//   brightness  0..2
//   voice       pulse with her voice
//   private     light the chest and groin (never on a tame stream, either way)
//   style       "neon" (white-hot cores in the colour) or "plain"

const N = 16;                                   // zones; the order lights.py writes them in
const SWEEP = ['ears', 'neck', 'chest', 'arm_l', 'arm_r', 'torso', 'hand_l', 'hand_r', 'navel',
               'groin', 'leg_l', 'leg_r', 'foot_l', 'foot_r', 'tail'];
const TOUCH = { head: ['ears'], nose: ['ears'], mouth: ['ears'], neck: ['ears', 'neck'], chest: ['chest'],
                tummy: ['navel', 'torso'], groin: ['groin'], legs: ['leg_l', 'leg_r', 'foot_l', 'foot_r'],
                arms: ['arm_l', 'arm_r', 'hand_l', 'hand_r'], back: ['torso'], butt: ['torso'], tail: ['tail'] };
const MOOD = { sad: '#3d6dff', angry: '#ff2414', tired: '#7a5cff', lewd: '#ff1e8c', excited: '#ff9de2' };

const SHADER = `
#ifndef OUTLINE
  {   // Luna's light strips (lights.js)
    vec2 lunaG = texture2D( lunaGlow, uv ).rg;
    int lunaZ = clamp( int( texture2D( lunaZone, uv ).r * 255.0 + 0.5 ), 0, ${N - 1} );
    float lunaL = lunaLevel[ lunaZ ];
    vec3 lunaC = lunaColor[ lunaZ ];
    float lunaOn = min( lunaL, 1.0 );
    // the light falls on the panels around it: they take its colour (on her
    // pale shell an added glow alone would only read as white)
    col = mix( col, col * ( 0.3 + 0.7 * lunaC ), min( 1.0, lunaG.g * lunaTint * lunaOn ) );
    col *= 1.0 - lunaDarken * lunaG.r * lunaOn;                       // the paint under a lit strip steps back
    col += lunaC * lunaG.g * lunaHalo * lunaL
         + mix( lunaC, vec3( 1.0 ), lunaWhite ) * lunaG.r * lunaCore * lunaL;
  }
#endif
`;
const UNIFORMS = `
uniform sampler2D lunaGlow;
uniform sampler2D lunaZone;
uniform vec3 lunaColor[ ${N} ];
uniform float lunaLevel[ ${N} ];
uniform float lunaCore;
uniform float lunaHalo;
uniform float lunaWhite;
uniform float lunaDarken;
uniform float lunaTint;
`;

function pixels(img) {
  const c = document.createElement('canvas');
  c.width = img.width; c.height = img.height;
  const g = c.getContext('2d', { willReadFrequently: true });
  g.drawImage(img, 0, 0);
  return g.getImageData(0, 0, c.width, c.height).data;
}

function image(url) {
  return new Promise((ok, bad) => {
    const i = new Image();
    i.onload = () => ok(i);
    i.onerror = () => bad(new Error(`couldn't load ${url}`));
    i.src = url;
  });
}

// running-sum box blur, three passes ~ a gaussian. In place on a Float32Array.
function blur(a, w, h, r) {
  const tmp = new Float32Array(Math.max(w, h));
  const pass = (n, len, step, start) => {
    for (let line = 0; line < n; line++) {
      const o = start(line);
      let sum = 0;
      for (let i = -r; i <= r; i++) sum += a[o + Math.min(len - 1, Math.max(0, i)) * step];
      for (let i = 0; i < len; i++) {
        tmp[i] = sum / (2 * r + 1);
        sum += a[o + Math.min(len - 1, i + r + 1) * step] - a[o + Math.max(0, i - r) * step];
      }
      for (let i = 0; i < len; i++) a[o + i * step] = tmp[i];
    }
  };
  for (let k = 0; k < 3; k++) {
    pass(h, w, 1, y => y * w);
    pass(w, h, w, x => x);
  }
}

async function maps(THREE, dir, entry, manifest) {
  const glowImg = await image(dir + entry.glow);
  const w = glowImg.width, h = glowImg.height;
  const glow = pixels(glowImg);
  const core = new Float32Array(w * h);
  for (let i = 0; i < w * h; i++) core[i] = glow[i * 4] / 255;
  const halo = Float32Array.from(core);
  blur(halo, w, h, Math.max(2, Math.round(w / 220)));

  // zones: the nearest of the legend's colours (GIMP's soft brushes blend them)
  const zone = new Uint8Array(w * h);
  const legend = manifest.zones.map(n => {
    const v = parseInt((manifest.zone_colors[n] || '#000000').slice(1), 16);
    return [v >> 16, (v >> 8) & 255, v & 255];
  });
  let zimg = null;
  try { if (entry.zones) zimg = await image(dir + entry.zones); } catch { zimg = null; }
  if (zimg && zimg.width === w && zimg.height === h) {
    const z = pixels(zimg), seen = new Map();
    for (let i = 0; i < w * h; i++) {
      const key = (z[i * 4] << 16) | (z[i * 4 + 1] << 8) | z[i * 4 + 2];
      let id = seen.get(key);
      if (id === undefined) {
        let best = 1e9;
        legend.forEach(([r, g, b], k) => {
          const d = (r - z[i * 4]) ** 2 + (g - z[i * 4 + 1]) ** 2 + (b - z[i * 4 + 2]) ** 2;
          if (d < best) { best = d; id = k; }
        });
        seen.set(key, id);
      }
      zone[i] = id;
    }
  } else {
    zone.fill(Math.max(0, manifest.zones.indexOf((entry.lit || [])[0] || 'torso')));
  }

  const lit = new Uint8Array(w * h * 4);
  for (let i = 0; i < w * h; i++) {
    lit[i * 4] = core[i] * 255;
    lit[i * 4 + 1] = Math.min(1, halo[i] * 2.2) * 255;
    lit[i * 4 + 3] = 255;
  }
  const glowTex = new THREE.DataTexture(lit, w, h, THREE.RGBAFormat);
  glowTex.magFilter = THREE.LinearFilter; glowTex.minFilter = THREE.LinearMipmapLinearFilter;
  glowTex.generateMipmaps = true; glowTex.flipY = false; glowTex.needsUpdate = true;
  const zoneTex = new THREE.DataTexture(zone, w, h, THREE.RedFormat);
  zoneTex.magFilter = zoneTex.minFilter = THREE.NearestFilter;
  zoneTex.flipY = false; zoneTex.needsUpdate = true;
  return { glowTex, zoneTex };
}

export async function createLights(THREE, vrm, modelUrl, settings = {}) {
  const dir = modelUrl.replace(/[^/]*$/, '') + 'lights/';
  const manifest = await fetch(dir + 'lights.json').then(r => r.ok ? r.json() : null).catch(() => null);
  if (!manifest?.materials || !Array.isArray(manifest.zones)) return null;
  // made for one model: the others in the folder share its material names, not its paint
  if (manifest.model && manifest.model !== decodeURIComponent(modelUrl.split('/').pop().split('?')[0])) return null;
  const id = Object.fromEntries(manifest.zones.map((n, i) => [n, i]));
  // the paint's colour, as a light: more saturated than the paint, or pink on pink washes out
  const own = new THREE.Color(Object.values(manifest.materials)[0]?.color || '#ff4fb4');
  { const hsl = {}; own.getHSL(hsl); own.setHSL(hsl.h, Math.max(hsl.s, 0.95), Math.min(hsl.l, 0.55)); }

  // shared by every lit material: one update a frame
  const color = { value: Array.from({ length: N }, () => new THREE.Color(0, 0, 0)) };
  const level = { value: new Array(N).fill(0) };
  const looks = { lunaCore: { value: 2.4 }, lunaHalo: { value: 1.8 }, lunaWhite: { value: 0.35 }, lunaDarken: { value: 1 },
                  lunaTint: { value: 5 } };

  const done = new Map(), patched = [];
  const jobs = [];
  vrm.scene.traverse(o => {
    if (!o.isMesh) return;
    for (const m of [].concat(o.material)) {
      const name = (m.name || '').replace(/\s*\(Instance\)/, '').replace(/\s*\(Outline\)/, '');
      const entry = manifest.materials[name];
      if (!entry || !m.isShaderMaterial || m.isOutline || /Outline/.test(m.name) || patched.includes(m)) continue;
      if (!m.fragmentShader.includes('// -- MToon: Emission')) continue;   // not MToon: leave it be
      patched.push(m);
      if (!done.has(name)) done.set(name, maps(THREE, dir, entry, manifest));
      jobs.push(done.get(name).then(({ glowTex, zoneTex }) => {
        Object.assign(m.uniforms, looks, { lunaGlow: { value: glowTex }, lunaZone: { value: zoneTex },
                                           lunaColor: color, lunaLevel: level });
        m.fragmentShader = m.fragmentShader
          .replace('void main', UNIFORMS + '\nvoid main')
          .replace('// -- MToon: Emission', SHADER + '\n  // -- MToon: Emission');
        m.needsUpdate = true;
      }));
    }
  });
  if (!jobs.length) return null;
  await Promise.all(jobs);

  // ---- what drives them ----------------------------------------------------
  let cfg = {};
  const st = { t: 0, on: 0, tint: own.clone(), flicker: 0, pulse: new Array(N).fill(0), think: 0, phase: 0 };
  const target = new THREE.Color();
  const pick = new THREE.Color();

  function set(s) {
    cfg = { enabled: false, color: '', brightness: 1, voice: true, private: true, style: 'neon', ...(s || {}) };
    const plain = cfg.style === 'plain';
    looks.lunaWhite.value = plain ? 0.1 : 0.35;          // toned down 2026-10-23: was 0.55 / 4 / 3.5
    looks.lunaCore.value = plain ? 1.8 : 2.4;
    looks.lunaHalo.value = plain ? 1.0 : 1.8;
  }
  set(settings);

  function moodColour(m) {
    if (m.row === 'lewd') return pick.set(MOOD.lewd);
    if (m.warmth < -0.35) return pick.set(MOOD.angry);
    if (m.energy < -0.45) return pick.set(m.warmth > 0.3 ? MOOD.tired : MOOD.sad);
    if (m.energy > 0.55 && m.warmth > 0.3) return pick.set(MOOD.excited);
    return pick.copy(own);
  }

  // m: { stage, energy, warmth, row, tame, talking (0..1), glow (0..~1.5: a gesture's lights curve) }
  function update(dt, m) {
    st.t += dt;
    st.on += ((cfg.enabled ? 1 : 0) - st.on) * Math.min(1, dt * 3);           // fade in and out
    if (st.on < 0.002 && !cfg.enabled) { if (level.value[1] !== 0) level.value.fill(0); st.pulse.fill(0); return; }

    if (/^#[0-9a-f]{6}$/i.test(cfg.color || '')) target.set(cfg.color);
    else if (cfg.color === 'own') target.copy(own);
    else target.copy(moodColour(m));
    st.tint.lerp(target, Math.min(1, dt * 1.5));

    const bright = Math.max(0, Math.min(2, +cfg.brightness || 0));
    // Off at rest (Ryan, 2026-10-23: a glow that stays on looks rough): they
    // only light for something - her voice, a think sweep, her ears while she
    // listens, a touch, a failed tool, a gesture's throb - and go dark after.
    let base = 0;
    if (m.stage === 'speaking' && cfg.voice !== false) base += 0.55 * (m.talking || 0);
    if (m.energy < -0.45) base *= 0.75;                                       // low: dimmer
    // a gesture throbs them: a slow beat, brighter and a little quicker as it
    // builds (about 1.5 a second at a peak), dark between beats and after
    const glow = Math.min(1.5, Math.max(0, m.glow || 0));
    st.phase += dt * Math.PI * 2 * (0.45 + glow * 0.7);
    if (glow) base += 0.9 * glow * (0.5 + 0.5 * Math.sin(st.phase)) ** 2;   // on, off, on: fully dark between beats
    st.think = m.stage === 'thinking' ? st.think + dt : 0;
    st.flicker = Math.max(0, st.flicker - dt);
    const flick = st.flicker > 0 ? (Math.random() < 0.35 ? 0.1 : 1) : 1;
    const dark = m.tame || cfg.private === false;

    for (let z = 1; z < N; z++) {
      const name = manifest.zones[z];
      let v = base;
      if (st.think > 0) {                                                     // a sweep, head to tail
        const k = SWEEP.indexOf(name);
        const pos = ((st.think * 0.9) % 1.4) * SWEEP.length;
        if (k >= 0) v += 0.6 * Math.max(0, 1 - Math.abs(pos - k) / 2.2);
      }
      if (name === 'ears' && m.stage === 'listening') v += 0.35;
      st.pulse[z] = Math.max(0, st.pulse[z] - dt * 0.9);
      v += st.pulse[z];
      if (dark && manifest.private.includes(name)) v = 0;
      level.value[z] = v * bright * st.on * flick;
      color.value[z].copy(st.tint);
    }
  }

  return {
    set,
    update,
    get enabled() { return !!cfg.enabled; },
    failed() { st.flicker = 1.2; },                                          // a tool failed
    touched(zone) { for (const n of TOUCH[zone] || []) if (n in id) st.pulse[id[n]] = 0.9; },
    zones: manifest.zones,
  };
}
