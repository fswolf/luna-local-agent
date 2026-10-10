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
import { createLook } from './look.js';
import { createHologram } from './hologram.js';

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

// The hologram look: config.json "hologram": {"enabled": true}, or ?holo=1.
const holoCfg = cfg.hologram || {};
const holoOn = params.has('holo') ? params.get('holo') !== '0' : !!holoCfg.enabled;
let holo = holoOn ? createHologram(PIXI, app, model, holoCfg) : null;
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
  // (width: how much of the canvas must fit across). The defaults suit a
  // full-body canvas; a half-body model sets its own in its luna.json.
  const crop = Object.assign({ top: face ? 0.035 : 0.02, height: face ? 0.25 : 0.42, centerX: 0.5,
                               width: face ? 0.28 : 0.45 },
                             (face ? L2.crop_face : L2.crop) || {});
  const w0 = model.width / model.scale.x, h0 = model.height / model.scale.y;
  // by height; the sides may run off a narrow window - it's a portrait
  const s = Math.min(innerHeight / (h0 * crop.height), innerWidth / (w0 * crop.width));
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
  if (ev.t !== 'gaze') act.lastEvent = performance.now() / 1000;

  switch (ev.t) {
    case 'stage': {
      const next = stageOf(ev.status);
      if (next === 'listening' && mind.stage !== 'listening') {
        twitch(1);
        // Talked over mid-sentence: a startled look before she listens.
        if (mind.stage === 'speaking') { react('surprised', 0.9); holo?.glitch(0.5); }
        else kick(nod, -0.35);
      }
      mind.stage = next;
      look.setStage(next);
      holo?.bright(next === 'speaking' ? 1.12 : next === 'thinking' ? 0.9 : 1);
      break;
    }
    case 'holo':        // /holo or the tools pane, while the page is open
      if (params.has('holo')) break;            // the URL said, the URL wins
      if (ev.on) { holo ? holo.on() : (holo = createHologram(PIXI, app, model, holoCfg)); }
      else holo?.off();
      break;
    case 'gaze': look.setTarget(ev); break;
    case 'turn': twitch(0.7); break;
    case 'mood': {
      const w = +ev.warmth || 0;
      if (w > 0.85 && mind.warmth <= 0.85) showExpression('flustered');   // that landed
      if (w - mind.warmth > 0.2) { kick(bounce, 1); react('pleased', 1.6); }
      mind.energy = +ev.energy || 0;
      mind.warmth = w;
      break;
    }
    case 'tool': twitch(0.8); look.glance(0.6); break;
    case 'flags': {
      const flags = ev.flags || [];
      const hit = re => flags.some(f => re.test(f));
      if (hit(/^(tool failed|no answer|cut off)/)) { showExpression('confused'); react('furrow', 2.5); holo?.glitch(1); }
      else if (hit(/^(ungrounded|guessed|overconfident)/)) react('skeptical', 3);
      else if (hit(/^low confidence/)) react('worried', 3);
      else if (flags.length) tilt.target = 6;
      break;
    }
    case 'voice':
      if (ev.stop) { mind.voice.length = 0; break; }
      // A sentence starting after a pause gets a breath in first.
      if (!mind.voice.length) breath.inhale = true;
      mind.voice.push({ env: ev.env || [], zcr: ev.zcr || [], fps: ev.fps || 30, start: performance.now() });
      if (mind.voice.length > 3) mind.voice.shift();
      break;
    case 'done': tilt.target = 0; break;
    case 'reload': location.reload(); break;     // /portrait use switched the model
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

// gaze: -1..1 like ParamEyeBallX/Y. Where it aims comes from look.js;
// this is just the damped value the eyes actually show.
const look = createLook();
const gaze = { x: 0, y: 0 };

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

// ---------------------------------------------------------------------------
// Making more of the rig
//
// Sigewinne's physics hangs the hair and ears off the head angles and the
// apron, bow and hem off the BODY angles, all of it nudged by breathing.
// So a body that moves on its own, and breathing you can see, swing far
// more of her than the head alone ever did. Everything below is tunable
// from config.json's "live2d" block (and live, on the ?debug=1 page):
//
//   "breath": 1     how visible her breathing is (0 = off, 2 = deep)
//   "motion": 1     how much the body and gestures move overall
//   "flip_lean": false   if leaning in looks like leaning back on a rig
// ---------------------------------------------------------------------------
const tune = { breath: +(L2.breath ?? 1), motion: +(L2.motion ?? 1) };
const lean = L2.flip_lean ? -1 : 1;
const clampR = (id, v) => { if (!has(id)) return v; const [a, b] = range(id); return Math.max(a, Math.min(b, v)); };
const setR = (id, v) => set(id, clampR(id, v));
const eyeMax = has('ParamEyeLOpen') ? range('ParamEyeLOpen')[1] : 1;

// springs: a value that's kicked and settles back to 0
const spring = (k, c) => ({ v: 0, vel: 0, k, c });
const nod = spring(120, 14);       // head dips (negative = down)
const bounce = spring(90, 9);      // a little hop of the body, pleased
const browKick = spring(70, 10);   // brows lift on a stressed word
function kick(sp, amount) { sp.vel += amount * 10; }
function stepSpring(sp, dt) { sp.vel += (-sp.k * sp.v - sp.c * sp.vel) * dt; sp.v += sp.vel * dt; }

// reactions: a face held for a moment - brows, eyes, a lean
const REACT = {
  //            brow L/R height, angle (+ worried, - cross), form (- cross, + soft), eyes, lean
  surprised: { yL: 1, yR: 1, ang: 0.2, form: 0.2, eyes: 1.25, lean: 2 },
  pleased:   { yL: 0.3, yR: 0.3, ang: 0.1, form: 0.6, eyes: 1, lean: 1.5 },
  furrow:    { yL: -0.5, yR: -0.5, ang: -0.8, form: -0.7, eyes: 0.85, lean: -1 },
  skeptical: { yL: 0.8, yR: -0.3, ang: -0.2, form: -0.2, eyes: 0.9, lean: 0 },
  worried:   { yL: 0.4, yR: 0.4, ang: 0.8, form: -0.1, eyes: 1, lean: -0.5 },
};
const act = { react: null, until: 0, lastEvent: performance.now() / 1000, lastLook: 0, lookGap: 8,
              stretchAt: performance.now() / 1000 + rand(150, 300), stretch: -1 };
function react(name, seconds = 2) {
  act.react = REACT[name] ? name : null;
  act.until = performance.now() / 1000 + seconds;
}

// the body: its own sway, and a change of posture every half minute or so
const body = { x: 0, y: 0, z: 0, px: 0, pz: 0, next: rand(15, 30) };

// breathing: a phase that runs faster or slower with her state, a
// shorter breath in than out, and a quick top-up before she speaks
const breath = { phase: rand(0, 6.28), rate: 0.24, inhale: false, value: 0, jitter: 1 };
function stepBreath(now, dt, talking, sleepy) {
  let rate = mind.stage === 'thinking' ? 0.3 : talking ? 0.32 : sleepy ? 0.17 : 0.23;
  rate *= 1 + mind.energy * 0.15;
  if (breath.inhale) {                 // jump to the start of a breath in
    breath.inhale = false;
    const p = breath.phase % (Math.PI * 2);
    if (p > Math.PI * 0.6) breath.phase += Math.PI * 2 - p;
  }
  const before = breath.phase % (Math.PI * 2);
  breath.phase += Math.PI * 2 * rate * breath.jitter * dt;
  if (breath.phase % (Math.PI * 2) < before) breath.jitter = rand(0.85, 1.15);   // each breath a little different
  const p = breath.phase % (Math.PI * 2);
  // in over the first 40% of the cycle, out over the rest
  const k = p / (Math.PI * 2);
  breath.value = k < 0.4 ? (1 - Math.cos(Math.PI * k / 0.4)) / 2 : (1 + Math.cos(Math.PI * (k - 0.4) / 0.6)) / 2;
  return breath.value;
}

// listening: a small "mm-hm" nod now and then while you talk
const listen = { next: 0 };
// emphasis: a nod and a brow lift on the louder syllables
const voiceTrack = { avg: 0, cool: 0 };

// overrides from the debug sliders: id -> value (wins over everything)
const override = {};

model.internalModel.on('beforeModelUpdate', () => {
  const nowMs = performance.now();
  const dt = Math.min((nowMs - last) / 1000, 0.05);
  last = nowMs;
  const now = nowMs / 1000;
  const M = tune.motion;
  const hour = new Date().getHours();
  const sleepy = (hour >= 23 || hour < 6) && mind.stage === 'idle';
  const idleFor = now - act.lastEvent;

  const L = look.update(now);
  if (L2.flip_gaze) { L.x = -L.x; L.wander.x = -L.wander.x; L.tilt = -L.tilt; }   // a rig built mirrored
  gaze.x = damp(gaze.x, L.x, 20, dt);
  gaze.y = damp(gaze.y, L.y, 20, dt);

  // --- voice
  const v = voiceNow();
  const level = v ? Math.min(1, v.level * 1.3) : 0;
  mouth.level = damp(mouth.level, level, level > mouth.level ? 30 : 16, dt);
  const talking = mouth.level > 0.05;

  voiceTrack.avg = damp(voiceTrack.avg, level, 3, dt);
  voiceTrack.cool -= dt;
  if (v && level > 0.55 && level > voiceTrack.avg + 0.25 && voiceTrack.cool <= 0) {
    kick(nod, -rand(0.25, 0.5) * M);
    kick(browKick, rand(0.3, 0.6));
    voiceTrack.cool = rand(0.45, 1.1);
  }

  // --- listening nods
  if (mind.stage === 'listening' && now > listen.next) {
    if (listen.next) kick(nod, -rand(0.2, 0.4) * M);
    listen.next = now + rand(2.5, 5);
  } else if (mind.stage !== 'listening') listen.next = 0;

  // --- idle: look around more after a quiet minute, a stretch now and then
  if (mind.stage === 'idle' && idleFor > 60 && now - act.lastLook > act.lookGap) {
    look.glance(rand(0.6, 1)); act.lastLook = now; act.lookGap = rand(6, 12);
  }
  if (mind.stage === 'idle' && idleFor > 90 && act.stretch < 0 && now > act.stretchAt) act.stretch = 0;
  let st = 0;                       // 0..1..0 over the stretch
  if (act.stretch >= 0) {
    act.stretch += dt / 3.2;
    st = Math.sin(Math.PI * Math.min(1, act.stretch));
    if (act.stretch >= 1 || mind.stage !== 'idle') { act.stretch = -1; act.stretchAt = now + rand(180, 360); }
  }

  stepSpring(nod, dt); stepSpring(bounce, dt); stepSpring(browKick, dt);
  const b = stepBreath(now, dt, talking, sleepy);
  const B = tune.breath;

  // --- reaction being held
  if (act.react && now > act.until) act.react = null;
  const R = act.react ? REACT[act.react] : null;
  const rf = R ? Math.min(1, (act.until - now) * 2) : 0;   // fades out over the last half second

  // --- head
  tilt.v = damp(tilt.v, tilt.target + L.tilt * 10, 3, dt);
  const sway = Math.sin(now * 0.7) * 3 + Math.sin(now * 0.31 + 1) * 2;
  head.x = damp(head.x, (gaze.x * L.headGain + L.wander.x) * 18 + sway, L.thinking ? 2.5 : 3.5, dt);
  head.y = damp(head.y, (gaze.y * L.headGain + L.wander.y) * 14 + (mind.stage === 'listening' ? -4 : 0)
                + mouth.level * 4 * Math.sin(now * 9), L.thinking ? 2.5 : 4, dt);
  head.z = damp(head.z, tilt.v + Math.sin(now * 0.45) * 2, 3, dt);

  // --- body: follows the head a little, sways on its own, shifts its weight
  if (now > body.next) {
    body.px = rand(-4, 4); body.pz = rand(-3, 3);
    body.next = now + rand(18, 40);
  }
  const ownSway = Math.sin(now * 0.23) * 2 + Math.sin(now * 0.11 + 2) * 1.5;
  const leanTo = (mind.stage === 'listening' ? -3 : mind.stage === 'thinking' ? 1 : 0)
                 + (R ? R.lean * rf : 0) + st * 6;
  body.x = damp(body.x, head.x * 0.25 + (ownSway + body.px) * M, 1.2, dt);
  body.y = damp(body.y, leanTo * M, 2, dt);
  body.z = damp(body.z, head.z * 0.3 + body.pz * M, 1, dt);

  // --- face
  const w = mind.warmth, e = mind.energy;
  face.smile = damp(face.smile, Math.max(0, Math.min(1, w * 0.6 + e * 0.2 + (talking ? 0.15 : 0)
                    + (act.react === 'pleased' ? 0.3 * rf : 0))), 2.5, dt);
  face.cheek = damp(face.cheek, Math.max(0, Math.min(1, w * 0.8)), 1.5, dt);
  face.brow = damp(face.brow, Math.max(-1, Math.min(1, e * 0.5 + w * 0.3 + L.brow)), 2, dt);
  face.form = damp(face.form, talking ? (v && v.zcr > 0.15 ? 1 : 0.3)
                   : face.smile * 0.8 - (w < -0.4 ? 0.6 : 0) + L.purse, 6, dt);

  // brows: mood sets the resting shape, a reaction takes over for a moment
  const restAng = (e < -0.4 ? 0.5 : 0) + (L.thinking ? 0.15 : 0);
  const restForm = w * 0.4 - (e < -0.6 ? 0.2 : 0);
  const side = L.thinking ? Math.sign(L.tilt || 1) * 0.15 : 0;   // the brow on the side she looks to, higher
  const brows = {
    yL: face.brow * 0.6 + browKick.v + side + (R ? (R.yL - face.brow * 0.6) * rf : 0),
    yR: face.brow * 0.6 + browKick.v - side + (R ? (R.yR - face.brow * 0.6) * rf : 0),
    ang: restAng + (R ? (R.ang - restAng) * rf : 0),
    form: restForm + (R ? (R.form - restForm) * rf : 0),
  };

  // eyes: blinks, a little heavier when sleepy, wide when startled, shut in a stretch
  const blinkNow = mind.stage === 'waking' ? 1 : blinkOpen(now, dt);
  let open = blinkNow * (1 - face.smile * 0.25) * (sleepy ? 0.78 : 1);
  if (R && R.eyes !== 1) open *= 1 + (R.eyes - 1) * rf;
  open *= 1 - st * 0.9;

  setR('ParamAngleX', head.x);
  setR('ParamAngleY', head.y + nod.v * 12 + b * 1.5 * B + st * 10);
  setR('ParamAngleZ', head.z);
  setR('ParamBodyAngleX', body.x);
  setR('ParamBodyAngleY', lean * (body.y + bounce.v * 3) + b * 2.5 * B);
  setR('ParamBodyAngleZ', body.z);
  set('ParamEyeBallX', gaze.x);
  set('ParamEyeBallY', gaze.y + st * 0.4);
  setR('ParamEyeLOpen', Math.min(eyeMax, open));
  setR('ParamEyeROpen', Math.min(eyeMax, open));
  set('ParamEyeLSmile', face.smile * 0.8);
  set('ParamEyeRSmile', face.smile * 0.8);
  set('ParamMouthOpenY', Math.max(mouth.level, st * 0.6));
  set('ParamMouthForm', face.form);
  set('ParamCheek', face.cheek);
  setR('ParamBrowLY', brows.yL);
  setR('ParamBrowRY', brows.yR);
  setR('ParamBrowLAngle', brows.ang);
  setR('ParamBrowRAngle', brows.ang);
  setR('ParamBrowLForm', brows.form);
  setR('ParamBrowRForm', brows.form);
  set('ParamBreath', B > 0 ? b : 0);

  updateEars(now, dt);
  for (const ear of ears) add(ear.id, ear.v * ear.span * 0.06);

  for (const [id, val] of Object.entries(override)) set(id, val);

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
    'you: left': () => handle({ t: 'gaze', x: -0.8, y: -0.1 }),
    'you: right': () => handle({ t: 'gaze', x: 0.8, y: -0.1 }),
    'you: ahead': () => handle({ t: 'gaze', none: true }),
  };
  Object.assign(buttons, {
    nod: () => kick(nod, -0.45), hop: () => kick(bounce, 1), 'breath in': () => { breath.inhale = true; },
    stretch: () => { act.stretch = 0; },
  });
  Object.assign(buttons, { glitch: () => holo?.glitch(1),
    'holo on/off': () => { if (holo && holo.isOn()) holo.off(); else if (holo) holo.on();
                           else holo = createHologram(PIXI, app, model, holoCfg); } });
  for (const name of Object.keys(REACT)) buttons[name] = () => react(name, 2.5);
  for (const role of Object.keys(exprFor)) buttons[role] = () => showExpression(role, 3);
  for (const [label, fn] of Object.entries(buttons)) {
    const b = document.createElement('button'); b.textContent = label; b.onclick = fn; box.appendChild(b);
  }
  // sliders: breathing and motion strength, and any one parameter by hand
  const tuneBox = document.getElementById('dtune');
  const slider = (label, min, max, step, value, onInput) => {
    const row = document.createElement('label');
    row.style.display = 'block';
    const input = Object.assign(document.createElement('input'), { type: 'range', min, max, step, value });
    const out = document.createElement('span');
    const show = () => { out.textContent = ` ${label} ${(+input.value).toFixed(2)}`; };
    input.oninput = () => { onInput(+input.value); show(); };
    show();
    row.append(input, out);
    tuneBox.appendChild(row);
    return input;
  };
  slider('breath', 0, 3, 0.05, tune.breath, x => { tune.breath = x; });
  slider('motion', 0, 2, 0.05, tune.motion, x => { tune.motion = x; });
  const pick = document.createElement('select');
  // the raw Cubism model lists every parameter id; the display file names them
  const raw = core.getModel ? core.getModel() : core._model;
  let ids = Array.from(raw?.parameters?.ids || []);
  const cdiNames = {};
  try {
    const cdi = await fetch(cfg.model.replace(/model3\.json$/, 'cdi3.json')).then(r => r.json());
    for (const p of cdi.Parameters || []) cdiNames[p.Id] = p.Name;
    if (!ids.length) ids = Object.keys(cdiNames);
  } catch (_) {}
  pick.add(new Option('pick a parameter to hold', ''));
  for (const id of ids.filter(Boolean)) pick.add(new Option(cdiNames[id] ? `${id} (${cdiNames[id]})` : id, id));
  tuneBox.appendChild(pick);
  let held = null;
  const hand = slider('value', -30, 30, 0.01, 0, x => { if (held) override[held] = x; });
  pick.onchange = () => {
    if (held) delete override[held];
    held = pick.value || null;
    if (!held || !has(held)) { held = null; return; }
    const [a, b] = range(held);
    Object.assign(hand, { min: a, max: b, step: (b - a) / 200, value: core.getParameterValueById(held) });
    override[held] = +hand.value;
    hand.oninput();
  };
  const release = document.createElement('button');
  release.textContent = 'let go';
  release.onclick = () => { if (held) delete override[held]; held = null; };
  tuneBox.appendChild(release);

  document.getElementById('dears').textContent = ears.map(e => e.id).join(', ') || 'none found';
  document.getElementById('dexpr').textContent = Object.entries(exprFor).map(([k, v]) => `${k}: ${v}`).join('\n') || 'none';
  document.querySelector('#debug h4:last-of-type').textContent = 'model';
  document.getElementById('dbones').textContent = `${cfg.model}\n${core.getParameterCount()} parameters`;
  setInterval(() => { document.getElementById('dstate').textContent =
    `${mind.stage} · energy ${mind.energy.toFixed(2)} warmth ${mind.warmth.toFixed(2)}`; }, 300);
}
window.portrait = { handle, twitch, fakeVoice, blink, mind, model, showExpression, look, get holo() { return holo; } };

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
