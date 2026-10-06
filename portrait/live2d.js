// Luna as a Live2D model, driven by the same event stream as the 3D one.
//
// Standard Cubism parameters do most of it (ParamAngleX/Y/Z, ParamEyeBall,
// ParamEyeLOpen, ParamMouthOpenY ...). Anything model-specific - which
// parameters are the ears, which expression is "spiral eyes" - comes from
// config.json's "live2d" block, so another model needs a config change,
// not a code change.
//
//   ?bg=transparent  ?frame=face  ?debug=1  ?demo=1   (same as the 3D page)

import { PIXI, Live2DModel } from './vendor/luna-pixi.js';

const params = new URLSearchParams(location.search);
const note = document.getElementById('note');
const say = (text, keep) => { note.textContent = text; note.classList.toggle('hidden', !keep && !text); };

if (params.get('bg') === 'transparent') document.body.classList.add('transparent');
if (params.get('debug')) document.body.classList.add('debug');

const cfg = await fetch('config.json').then(r => r.json()).catch(() => ({}));
const L2 = cfg.live2d || {};

const app = new PIXI.Application({ resizeTo: window, backgroundAlpha: 0, antialias: true,
                                   resolution: Math.min(devicePixelRatio, 2), autoDensity: true });
document.body.appendChild(app.view);

say('loading…', true);
const model = await Live2DModel.from(cfg.model, { autoInteract: false, autoUpdate: true });
app.stage.addChild(model);
const core = model.internalModel.coreModel;

// We do the blinking and the looking, so the model's own versions are off.
model.internalModel.eyeBlink = undefined;
model.internalModel.focusController && (model.internalModel.focusController.focus = () => {});

// ---------------------------------------------------------------------------
// Framing: the model's own canvas, cropped to a bust (or a face).
// ---------------------------------------------------------------------------
function frame() {
  const face = params.get('frame') === 'face';
  // fractions of the model's canvas: where the crop starts, how tall it is
  const crop = Object.assign({ top: face ? 0.035 : 0.02, height: face ? 0.25 : 0.42, centerX: 0.5 },
                             (face ? L2.crop_face : L2.crop) || {});
  const w0 = model.width / model.scale.x, h0 = model.height / model.scale.y;
  // by height; the sides may run off a narrow window - it's a portrait
  const s = Math.min(innerHeight / (h0 * crop.height), innerWidth / (w0 * (face ? 0.28 : 0.45)));
  model.scale.set(s);
  model.x = innerWidth / 2 - w0 * s * crop.centerX;
  model.y = -h0 * s * crop.top;
}
frame();
addEventListener('resize', frame);
say('');

// ---------------------------------------------------------------------------
// Parameters
// ---------------------------------------------------------------------------
const idx = {};
function has(id) {
  if (!(id in idx)) idx[id] = core.getParameterIndex(id);
  return idx[id] >= 0;
}
function range(id) {
  const i = idx[id];
  return [core.getParameterMinimumValue(i), core.getParameterMaximumValue(i)];
}
function set(id, v) {
  if (has(id)) core.setParameterValueById(id, v);
}
function add(id, v) {
  if (has(id)) core.addParameterValueById(id, v);
}

// Ears: physics outputs we nudge after physics has run. Configurable; the
// default is every parameter whose display name mentions ears.
let earParams = L2.ear_params;
if (!earParams) {
  try {
    const cdi = await fetch(cfg.model.replace(/model3\.json$/, 'cdi3.json')).then(r => r.json());
    earParams = (cdi.Parameters || []).filter(p => /耳|ear/i.test(p.Name || '') && !/y\d*$/i.test(p.Name || ''))
                                       .map(p => p.Id);
  } catch (_) { earParams = []; }
}
earParams = earParams.filter(has);

// Expressions the model ships (spiral eyes, >< eyes, tears...) by role.
const exprFor = L2.expressions || {};

// ---------------------------------------------------------------------------
// What she's doing - same event stream and rules as the 3D portrait
// ---------------------------------------------------------------------------
const mind = { stage: 'idle', energy: 0, warmth: 0, voice: [] };
const rand = (a, b) => a + Math.random() * (b - a);
const damp = (cur, target, rate, dt) => cur + (target - cur) * (1 - Math.exp(-rate * dt));

function stageOf(status) {
  const s = (status || '').toLowerCase();
  if (/listen|record/.test(s)) return 'listening';
  if (/transcrib|think|rethink|reminder|reflect/.test(s)) return 'thinking';
  if (/speak|chat/.test(s)) return 'speaking';
  if (/waking/.test(s)) return 'waking';
  return 'idle';
}

let flash = null;   // a model expression shown for a moment: {name, until}
function showExpression(role, seconds = 2.2) {
  const name = exprFor[role];
  if (!name) return;
  model.expression(name);
  flash = { until: performance.now() + seconds * 1000 };
}

function handle(ev) {
  switch (ev.t) {
    case 'stage': {
      const next = stageOf(ev.status);
      if (next === 'listening' && mind.stage !== 'listening') twitch(1);
      mind.stage = next;
      break;
    }
    case 'turn': twitch(0.7); break;
    case 'mood': {
      const w = +ev.warmth || 0;
      if (w > 0.85 && mind.warmth <= 0.85) showExpression('flustered');   // that landed
      mind.energy = +ev.energy || 0;
      mind.warmth = w;
      break;
    }
    case 'tool': twitch(0.8); glance(0.6); break;
    case 'flags':
      if ((ev.flags || []).some(f => /^(tool failed|no answer|cut off)/.test(f))) showExpression('confused');
      else if ((ev.flags || []).length) tilt.target = 6;
      break;
    case 'voice':
      if (ev.stop) { mind.voice.length = 0; break; }
      mind.voice.push({ env: ev.env || [], zcr: ev.zcr || [], fps: ev.fps || 30, start: performance.now() });
      if (mind.voice.length > 3) mind.voice.shift();
      break;
    case 'done': tilt.target = 0; break;
  }
}

function connect() {
  const es = new EventSource('/events');
  es.onmessage = m => { try { handle(JSON.parse(m.data)); } catch (_) {} };
  es.onopen = () => say('');
  es.onerror = () => { if (!params.get('demo')) say('waiting for Luna…', true); };
}

// blink
const blink = { next: rand(1.5, 4), t: -1, double: false };
function blinkOpen(now, dt) {
  if (blink.t < 0 && now >= blink.next) { blink.t = 0; blink.double = Math.random() < 0.18; }
  if (blink.t < 0) return 1;
  blink.t += dt;
  const len = 0.17, k = blink.t / len;
  const shut = k < 0.45 ? k / 0.45 : Math.max(0, 1 - (k - 0.45) / 0.55);
  if (blink.t >= len) { blink.t = -1; blink.next = now + (blink.double ? 0.09 : rand(2.2, 6.5)); blink.double = false; }
  return 1 - Math.min(1, shut);
}

// gaze: -1..1 like ParamEyeBallX/Y
const gaze = { x: 0, y: 0, tx: 0, ty: 0, next: 0 };
function glance(strength = 1) {
  gaze.tx = rand(-0.9, 0.9) * strength; gaze.ty = rand(-0.2, 0.5) * strength;
  gaze.next = performance.now() / 1000 + rand(0.6, 1.4);
}
function pickGaze(now) {
  if (now < gaze.next) return;
  if (mind.stage === 'thinking') {
    gaze.tx = (Math.random() < 0.7 ? 1 : -1) * rand(0.5, 0.9); gaze.ty = rand(0.5, 0.85);
    gaze.next = now + rand(1.2, 2.6);
  } else if (mind.stage === 'listening' || mind.stage === 'speaking') {
    gaze.tx = rand(-0.12, 0.12); gaze.ty = rand(-0.06, 0.1); gaze.next = now + rand(0.5, 1.6);
  } else {
    const away = Math.random() < 0.3;
    gaze.tx = away ? rand(-1, 1) : rand(-0.2, 0.2);
    gaze.ty = away ? rand(-0.35, 0.45) : rand(-0.08, 0.12);
    gaze.next = now + (away ? rand(0.8, 2.0) : rand(1.0, 3.5));
  }
}

// ears: a damped spring per ear parameter, kicked by twitch()
const ears = earParams.map(id => ({ id, v: 0, vel: 0, span: (r => (r[1] - r[0]) / 2)(range(id)) }));
const earsNext = { t: rand(3, 7) };
function twitch(strength = 1) {
  const which = Math.random();
  ears.forEach((e, i) => {
    if (which < 0.35 && i % 2) return;            // sometimes just one side
    if (which > 0.65 && !(i % 2)) return;
    e.vel += strength * rand(10, 16) * (Math.random() < 0.5 ? 1 : -1);
  });
}
function updateEars(now, dt) {
  if (now > earsNext.t) { twitch(rand(0.4, 1)); earsNext.t = now + rand(2.5, 9); }
  for (const e of ears) {
    e.vel += (-170 * e.v - 13 * e.vel) * dt;
    e.v += e.vel * dt;
  }
}

// mouth: loudness envelope -> ParamMouthOpenY
const mouth = { level: 0 };
function voiceNow() {
  const now = performance.now();
  while (mind.voice.length) {
    const v = mind.voice[0];
    const i = Math.floor((now - v.start) / 1000 * v.fps);
    if (i < v.env.length) return { level: v.env[i] || 0, zcr: v.zcr[i] ?? 0.1 };
    mind.voice.shift();
    if (mind.voice[0]) mind.voice[0].start = Math.max(mind.voice[0].start, now);
  }
  return null;
}

const tilt = { v: 0, target: 0 };
const head = { x: 0, y: 0, z: 0 };
const face = { smile: 0, cheek: 0, brow: 0, form: 0 };
let last = performance.now();

model.internalModel.on('beforeModelUpdate', () => {
  const nowMs = performance.now();
  const dt = Math.min((nowMs - last) / 1000, 0.05);
  last = nowMs;
  const now = nowMs / 1000;

  pickGaze(now);
  gaze.x = damp(gaze.x, gaze.tx, 20, dt);
  gaze.y = damp(gaze.y, gaze.ty, 20, dt);

  const v = voiceNow();
  const level = v ? Math.min(1, v.level * 1.3) : 0;
  mouth.level = damp(mouth.level, level, level > mouth.level ? 30 : 16, dt);
  const talking = mouth.level > 0.05;

  tilt.v = damp(tilt.v, tilt.target + (mind.stage === 'thinking' ? 8 : 0), 3, dt);
  const sway = Math.sin(now * 0.7) * 3 + Math.sin(now * 0.31 + 1) * 2;
  head.x = damp(head.x, gaze.x * 18 + sway, 3.5, dt);
  head.y = damp(head.y, gaze.y * 14 + (mind.stage === 'listening' ? -4 : 0)
                + mouth.level * 4 * Math.sin(now * 9), 4, dt);
  head.z = damp(head.z, tilt.v + Math.sin(now * 0.45) * 2, 3, dt);

  const w = mind.warmth, e = mind.energy;
  face.smile = damp(face.smile, Math.max(0, Math.min(1, w * 0.6 + e * 0.2 + (talking ? 0.15 : 0))), 2.5, dt);
  face.cheek = damp(face.cheek, Math.max(0, Math.min(1, w * 0.8)), 1.5, dt);
  face.brow = damp(face.brow, Math.max(-1, Math.min(1, e * 0.5 + w * 0.3)), 2, dt);
  face.form = damp(face.form, talking ? (v && v.zcr > 0.15 ? 1 : 0.3) : face.smile * 0.8 - (w < -0.4 ? 0.6 : 0), 6, dt);

  set('ParamAngleX', head.x);
  set('ParamAngleY', head.y);
  set('ParamAngleZ', head.z);
  set('ParamBodyAngleX', head.x * 0.3);
  set('ParamBodyAngleZ', head.z * 0.3);
  set('ParamEyeBallX', gaze.x);
  set('ParamEyeBallY', gaze.y);
  const open = mind.stage === 'waking' ? 1 : blinkOpen(now, dt);
  set('ParamEyeLOpen', open * (1 - face.smile * 0.25));
  set('ParamEyeROpen', open * (1 - face.smile * 0.25));
  set('ParamEyeLSmile', face.smile * 0.8);
  set('ParamEyeRSmile', face.smile * 0.8);
  set('ParamMouthOpenY', mouth.level);
  set('ParamMouthForm', face.form);
  set('ParamCheek', face.cheek);
  set('ParamBrowLY', face.brow * 0.6);
  set('ParamBrowRY', face.brow * 0.6);
  set('ParamBreath', (Math.sin(now * 1.7) + 1) / 2);

  updateEars(now, dt);
  for (const ear of ears) add(ear.id, ear.v * ear.span * 0.06);

  // moods the model has a picture for
  if (flash && nowMs > flash.until) { model.internalModel.motionManager.expressionManager?.resetExpression(); flash = null; }
  if (!flash && e < -0.7 && exprFor.sad) { model.expression(exprFor.sad); flash = { until: nowMs + 4000 }; }
});

// ---------------------------------------------------------------------------
function fakeVoice(seconds = 2.4) {
  const fps = 30, env = [], zcr = [];
  for (let i = 0; i < seconds * fps; i++) {
    env.push(+(Math.abs(Math.sin(i / fps * Math.PI * 4.2)) * rand(0.45, 0.9)).toFixed(2));
    zcr.push(+rand(0.03, 0.28).toFixed(2));
  }
  handle({ t: 'voice', env, zcr, fps });
}

if (params.get('debug')) {
  const box = document.getElementById('dbuttons');
  const buttons = {
    blink: () => { blink.next = 0; }, twitch: () => twitch(1),
    talk: () => { handle({ t: 'stage', status: 'Speaking...' }); fakeVoice(); },
    listen: () => handle({ t: 'stage', status: 'Listening...' }),
    think: () => handle({ t: 'stage', status: 'Thinking...' }),
    idle: () => handle({ t: 'stage', status: 'Idle' }),
    happy: () => handle({ t: 'mood', energy: 0.6, warmth: 1 }),
    sad: () => handle({ t: 'mood', energy: -0.8, warmth: -0.1 }),
    neutral: () => handle({ t: 'mood', energy: 0, warmth: 0 }),
  };
  for (const role of Object.keys(exprFor)) buttons[role] = () => showExpression(role, 3);
  for (const [label, fn] of Object.entries(buttons)) {
    const b = document.createElement('button'); b.textContent = label; b.onclick = fn; box.appendChild(b);
  }
  document.getElementById('dears').textContent = ears.map(e => e.id).join(', ') || 'none found';
  document.getElementById('dexpr').textContent = Object.entries(exprFor).map(([k, v]) => `${k}: ${v}`).join('\n') || 'none';
  document.querySelector('#debug h4:last-of-type').textContent = 'model';
  document.getElementById('dbones').textContent = `${cfg.model}\n${core.getParameterCount()} parameters`;
  setInterval(() => { document.getElementById('dstate').textContent =
    `${mind.stage} · energy ${mind.energy.toFixed(2)} warmth ${mind.warmth.toFixed(2)}`; }, 300);
}
window.portrait = { handle, twitch, fakeVoice, blink, mind, model, showExpression };

if (params.get('demo')) {
  (async () => {
    const step = (ms, ev) => new Promise(r => setTimeout(() => { if (ev) handle(ev); r(); }, ms));
    for (;;) {
      await step(2500, { t: 'stage', status: 'Listening...' });
      await step(2200, { t: 'turn', text: 'hey luna' });
      await step(300, { t: 'stage', status: 'Thinking...' });
      await step(2600, { t: 'stage', status: 'Speaking...' }); fakeVoice(3.0);
      await step(3200, { t: 'mood', energy: 0.5, warmth: 0.9 });
      await step(400, { t: 'stage', status: 'Idle' });
      await step(5000, { t: 'mood', energy: 0, warmth: 0.2 });
    }
  })();
} else {
  connect();
}
