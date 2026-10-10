// Luna's portrait: a VRM model that follows what she's doing.
//
// Everything it reacts to comes from the live monitor's event stream
// (/events, the same one /monitor reads): the stage she's at, her mood,
// tool calls, and - while she talks - the loudness envelope of each
// sentence as it starts playing, which is what moves her mouth. Nothing
// here talks back to the assistant.
//
//   ?bg=transparent   for an OBS browser source
//   ?frame=face       closer crop (default: bust)
//   ?debug=1          bone list and test buttons
//   ?demo=1           acts out a fake conversation, no assistant needed

import { THREE, GLTFLoader, VRMLoaderPlugin, VRMUtils } from './vendor/luna-three.js';
import { createLook } from './look.js';

const params = new URLSearchParams(location.search);
const note = document.getElementById('note');
const say = (text, keep) => {
  note.textContent = text;
  note.classList.toggle('hidden', !keep && !text);
};

if (params.get('bg') === 'transparent') document.body.classList.add('transparent');
if (params.get('debug')) document.body.classList.add('debug');

const cfg = await fetch('config.json').then(r => r.json()).catch(() => ({}));

// ---------------------------------------------------------------------------
// Scene
// ---------------------------------------------------------------------------
const renderer = new THREE.WebGLRenderer({ antialias: true, alpha: true, preserveDrawingBuffer: true });
renderer.setPixelRatio(Math.min(devicePixelRatio, 2));
renderer.setSize(innerWidth, innerHeight);
renderer.outputColorSpace = THREE.SRGBColorSpace;
renderer.setClearColor(0x000000, 0);
document.body.appendChild(renderer.domElement);

const scene = new THREE.Scene();
const camera = new THREE.PerspectiveCamera(22, innerWidth / innerHeight, 0.05, 20);

scene.add(new THREE.HemisphereLight(0xf3e6ff, 0x2a1838, 1.35));
const key = new THREE.DirectionalLight(0xfff4f8, 1.6);
key.position.set(-0.6, 1.2, 1.4);
scene.add(key);
const rim = new THREE.DirectionalLight(0xd070ff, 1.4);  // the wallpaper's magenta back-light
rim.position.set(0.8, 0.6, -1.2);
scene.add(rim);

addEventListener('resize', () => {
  renderer.setSize(innerWidth, innerHeight);
  camera.aspect = innerWidth / innerHeight;
  camera.updateProjectionMatrix();
  frame();
});

// ---------------------------------------------------------------------------
// Model
// ---------------------------------------------------------------------------
let vrm = null;
const ears = [];             // {node, rest, angle, vel, side}
const has = new Set();       // expression names this model has

async function load(url) {
  const loader = new GLTFLoader();
  loader.register(parser => new VRMLoaderPlugin(parser));
  const gltf = await loader.loadAsync(url, ev => {
    if (ev.total) say(`loading ${Math.round(100 * ev.loaded / ev.total)}%`, true);
  });
  const model = gltf.userData.vrm;

  if (!model) throw new Error(`${url} isn't a VRM`);

  VRMUtils.removeUnnecessaryVertices(gltf.scene);
  VRMUtils.combineSkeletons?.(gltf.scene);

  if (model.meta?.metaVersion === '0') VRMUtils.rotateVRM0(model);

  model.scene.traverse(o => {
    o.frustumCulled = false;
    // Painted with vertex colours (some generated and hand-made models are):
    // MToon ignores them unless asked to use them.
    if (o.isMesh && o.geometry?.attributes?.color) {
      for (const m of [].concat(o.material)) { m.vertexColors = true; m.needsUpdate = true; }
    }
  });
  scene.add(model.scene);

  for (const e of model.expressionManager?.expressions || []) has.add(e.expressionName);

  // Ears: nodes called Ear_L / ear.R / ..., or whatever config.json names.
  const wanted = new Set((cfg.ear_bones || []).map(s => s.toLowerCase()));
  model.scene.traverse(o => {
    const n = (o.name || '').toLowerCase();
    const named = wanted.size ? wanted.has(n)
      : /(^|[^a-z])ear([^a-z]|$)|ear_?[lr]\b|ears?$/.test(n) && !/(hear|year|pearl|gear|earring)/.test(n) && !o.isMesh;
    if (named && !ears.some(e => e.node === o)) {
      const world = new THREE.Vector3();
      o.getWorldPosition(world);
      ears.push({ node: o, rest: o.quaternion.clone(), x: 0, vx: 0, z: 0, vz: 0,
                  side: world.x >= 0 ? 1 : -1 });
    }
  });

  return model;
}

function frame() {
  if (!vrm) return;
  const head = vrm.humanoid.getNormalizedBoneNode('head');
  const p = new THREE.Vector3();
  head.getWorldPosition(p);
  const face = params.get('frame') === 'face';
  const height = face ? 0.30 : 0.46;   // metres that should fit top to bottom
  const width = face ? 0.24 : 0.40;    // ...and side to side
  const tan = Math.tan(THREE.MathUtils.degToRad(camera.fov / 2));
  const dist = Math.max((height / 2) / tan, (width / 2) / (tan * camera.aspect));
  const lookY = p.y + (face ? 0.065 : 0.02);
  camera.position.set(0, lookY + 0.01, p.z + dist);
  camera.lookAt(0, lookY, p.z);
  base.lookY = lookY;
  base.headZ = p.z;
}

const base = { lookY: 1.45, headZ: 0 };

// ---------------------------------------------------------------------------
// What she's doing - from the event stream
// ---------------------------------------------------------------------------
const mind = {
  stage: 'idle',              // idle listening thinking speaking waking
  energy: 0, warmth: 0,       // mood dials, about -1..1
  voice: [],                  // queued {env, zcr, fps, start}
  lastEvent: 0,
};

function stageOf(status) {
  const s = (status || '').toLowerCase();
  if (/listen|record/.test(s)) return 'listening';
  if (/transcrib|think|rethink|reminder|reflect/.test(s)) return 'thinking';
  if (/speak|chat/.test(s)) return 'speaking';
  if (/waking/.test(s)) return 'waking';
  return 'idle';
}

function handle(ev) {
  mind.lastEvent = performance.now();
  switch (ev.t) {
    case 'stage': {
      const next = stageOf(ev.status);
      if (next === 'listening' && mind.stage !== 'listening') twitch(0, 1.0);  // ears up: he's talking
      mind.stage = next;
      look.setStage(next);
      break;
    }
    case 'gaze':
      look.setTarget(ev);
      break;
    case 'turn':
      twitch(0, 0.6);
      break;
    case 'mood':
      mind.energy = +ev.energy || 0;
      mind.warmth = +ev.warmth || 0;
      break;
    case 'tool':
      twitch(Math.random() < 0.5 ? 1 : -1, 0.8);
      look.glance(0.6);
      break;
    case 'flags':
      if ((ev.flags || []).length) tilt.target = 0.12;   // a "hm" tilt when the review didn't like it
      break;
    case 'voice':
      if (ev.stop) { mind.voice.length = 0; break; }
      mind.voice.push({ env: ev.env || [], zcr: ev.zcr || [], fps: ev.fps || 30, start: performance.now() });
      if (mind.voice.length > 3) mind.voice.shift();
      break;
    case 'done':
      tilt.target = 0;
      break;
  }
}

function connect() {
  const es = new EventSource('/events');
  es.onmessage = m => { try { handle(JSON.parse(m.data)); } catch (_) {} };
  es.onopen = () => say('');
  es.onerror = () => {
    if (!params.get('demo')) say('waiting for Luna…', true);
  };
}

// ---------------------------------------------------------------------------
// Little motions
// ---------------------------------------------------------------------------
const rand = (a, b) => a + Math.random() * (b - a);
const damp = (cur, target, rate, dt) => cur + (target - cur) * (1 - Math.exp(-rate * dt));

// Blinking: every few seconds, sometimes twice.
const blink = { next: rand(1.5, 4), t: -1, double: false };

function blinkValue(now, dt) {
  if (blink.t < 0 && now >= blink.next) {
    blink.t = 0;
    blink.double = Math.random() < 0.18;
  }
  if (blink.t < 0) return 0;
  blink.t += dt;
  const len = 0.16;
  const k = blink.t / len;
  let v = k < 0.45 ? k / 0.45 : Math.max(0, 1 - (k - 0.45) / 0.55);
  if (blink.t >= len) {
    blink.t = -1;
    blink.next = now + (blink.double ? 0.09 : rand(2.2, 6.5));
    blink.double = false;
  }
  return Math.max(0, Math.min(1, v));
}

// Where she looks: a target in front of her face that jumps (saccades)
// and that her head follows, slower and only part of the way.
const gaze = { x: 0, y: 0 };
const lookTarget = new THREE.Object3D();
scene.add(lookTarget);

// Where it aims comes from look.js (-1..1); these scale that to this
// scene: how far the look target moves, how far the head tilts.
const look = createLook();
const LOOK_X = 0.24, LOOK_Y = 0.2, LOOK_TILT = 0.11;

// Ears: a damped spring per ear per axis. twitch() kicks it.
function twitch(side = 0, strength = 1) {
  for (const e of ears) {
    if (side && e.side !== side) continue;
    e.vz += strength * rand(9, 14) * (Math.random() < 0.5 ? 1 : -1) * 0.6;
    e.vx += strength * rand(-6, 6);
  }
}
const earsNext = { t: rand(3, 7) };
const tilt = { v: 0, target: 0 };

function earTargets() {
  // perked forward when listening, back and down when low, flicked out when cross
  if (mind.stage === 'listening') return { x: -0.18, z: 0.05 };
  if (mind.energy < -0.35) return { x: 0.25, z: 0.35 };
  if (mind.warmth < -0.4) return { x: 0.35, z: -0.1 };
  return { x: 0, z: 0 };
}

const qa = new THREE.Quaternion();
const eul = new THREE.Euler();

function updateEars(now, dt) {
  if (now > earsNext.t) {
    twitch(Math.random() < 0.6 ? (Math.random() < 0.5 ? 1 : -1) : 0, rand(0.4, 1));
    earsNext.t = now + rand(2.5, 9) / (mind.stage === 'idle' ? 1 : 1.6);
  }
  const t = earTargets();
  for (const e of ears) {
    const k = 160, c = 14;
    e.vx += (-k * (e.x - t.x) - c * e.vx) * dt;
    e.vz += (-k * (e.z - t.z * e.side) - c * e.vz) * dt;
    e.x += e.vx * dt;
    e.z += e.vz * dt;
    eul.set(e.x, 0, e.z * e.side);
    qa.setFromEuler(eul);
    e.node.quaternion.copy(e.rest).multiply(qa);
  }
}

// Mouth: the loudness envelope of whatever's playing, shaped into the five
// VRM vowels by how hissy the sound is (zero-crossing rate).
const mouth = { level: 0, aa: 0, ih: 0, ou: 0, ee: 0, oh: 0 };

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

function updateMouth(dt) {
  const v = voiceNow();
  const level = v ? Math.min(1, v.level * 1.25) : 0;
  mouth.level = damp(mouth.level, level, level > mouth.level ? 30 : 16, dt);
  const z = v ? v.zcr : 0.1;
  const target = { aa: 0, ih: 0, ou: 0, ee: 0, oh: 0 };
  if (mouth.level > 0.02) {
    if (z > 0.22) { target.ih = 0.6; target.ee = 0.4; }
    else if (z > 0.12) { target.aa = 0.75; target.ee = 0.25; }
    else if (z > 0.06) { target.aa = 0.5; target.oh = 0.5; }
    else { target.ou = 0.55; target.oh = 0.45; }
  }
  for (const k of ['aa', 'ih', 'ou', 'ee', 'oh']) {
    mouth[k] = damp(mouth[k], target[k] * mouth.level, 22, dt);
    setExpr(k, mouth[k]);
  }
  return mouth.level;
}

function setExpr(name, v) {
  if (has.has(name)) vrm.expressionManager.setValue(name, v);
}

// Moods: gentle, never a full grin from the dials alone.
const moodNow = { happy: 0, sad: 0, angry: 0, relaxed: 0, surprised: 0 };

function updateMood(dt, talking) {
  const w = mind.warmth, e = mind.energy;
  const target = {
    happy: Math.max(0, Math.min(0.55, w * 0.45 + e * 0.15 + (talking ? 0.08 : 0))),
    relaxed: Math.max(0, Math.min(0.4, w * 0.3 - e * 0.2)),
    sad: Math.max(0, Math.min(0.45, -e * 0.35 - w * 0.1)),
    angry: Math.max(0, Math.min(0.4, -w * 0.4 - 0.1)),
    surprised: mind.stage === 'waking' ? 0.35 : 0,
  };
  for (const k in target) {
    moodNow[k] = damp(moodNow[k], target[k], 2.5, dt);
    setExpr(k, moodNow[k]);
  }
}

// ---------------------------------------------------------------------------
// The loop
// ---------------------------------------------------------------------------
const clock = new THREE.Clock();
const headRot = { x: 0, y: 0, z: 0 };

function bone(name) { return vrm.humanoid.getNormalizedBoneNode(name); }
const breathing = { phase: Math.random() * 6, jitter: 1 };
const posture = { z: 0, y: 0, cz: 0, cy: 0, next: 10 };
let armsDown = null;
function inTPose() {
  // rest pose: does the upper arm run out sideways (T-pose) or down?
  const up = vrm.humanoid.getRawBoneNode('leftUpperArm'), lo = vrm.humanoid.getRawBoneNode('leftLowerArm');
  if (!up || !lo) return true;
  const a = new THREE.Vector3(), b = new THREE.Vector3();
  up.getWorldPosition(a); lo.getWorldPosition(b);
  return Math.abs(b.x - a.x) > Math.abs(b.y - a.y);
}

function animate() {
  requestAnimationFrame(animate);
  const dt = Math.min(clock.getDelta(), 0.05);
  const now = clock.elapsedTime;

  if (vrm) {
    const L = look.update(now);
    gaze.x = damp(gaze.x, L.x * LOOK_X, 22, dt);
    gaze.y = damp(gaze.y, L.y * LOOK_Y, 22, dt);
    lookTarget.position.set(gaze.x * 1.6, base.lookY + gaze.y * 1.6, base.headZ + 0.9);
    if (vrm.lookAt) vrm.lookAt.target = lookTarget;

    const talking = updateMouth(dt);
    updateMood(dt, talking > 0.05);
    setExpr('blink', mind.stage === 'waking' ? 0 : blinkValue(now, dt));

    // Head: follows the gaze part of the way, breathes, nods with her voice.
    tilt.v = damp(tilt.v, tilt.target + L.tilt * LOOK_TILT, 3, dt);
    const sway = Math.sin(now * 0.7) * 0.025 + Math.sin(now * 0.31 + 1) * 0.02;
    const rate = L.thinking ? 2.5 : 3.5;
    headRot.y = damp(headRot.y, (gaze.x * L.headGain + L.wander.x * LOOK_X) * 0.9 + sway, rate, dt);
    headRot.x = damp(headRot.x, -(gaze.y * L.headGain + L.wander.y * LOOK_Y) * 0.7
                     + (mind.stage === 'listening' ? 0.06 : 0)
                     + talking * 0.05 * Math.sin(now * 9), L.thinking ? 2.5 : 4, dt);
    headRot.z = damp(headRot.z, tilt.v + Math.sin(now * 0.45) * 0.02, 3, dt);
    const head = bone('head'), neck = bone('neck');
    if (head) head.rotation.set(headRot.x * 0.6, headRot.y * 0.6, headRot.z * 0.6);
    if (neck) neck.rotation.set(headRot.x * 0.4, headRot.y * 0.4, headRot.z * 0.4);

    // Breathing: in quicker than out, each breath a little different, the
    // shoulders lifting with it so it reads on a skinned model.
    breathing.phase += Math.PI * 2 * (talking > 0.05 ? 0.3 : mind.stage === 'thinking' ? 0.28 : 0.22) * breathing.jitter * dt;
    if (breathing.phase > Math.PI * 2) { breathing.phase -= Math.PI * 2; breathing.jitter = 0.85 + Math.random() * 0.3; }
    const k = breathing.phase / (Math.PI * 2);
    const breath = k < 0.4 ? (1 - Math.cos(Math.PI * k / 0.4)) / 2 : (1 + Math.cos(Math.PI * (k - 0.4) / 0.6)) / 2;
    const chest = bone('upperChest') || bone('chest');
    if (chest) chest.rotation.x = -breath * 0.035;
    const ls = bone('leftShoulder'), rs = bone('rightShoulder');
    if (ls) ls.rotation.z = breath * 0.05;
    if (rs) rs.rotation.z = -breath * 0.05;

    // The body sways on its own and shifts its weight now and then, so the
    // hair (spring bones) has something to swing from besides the head.
    if (now > posture.next) { posture.z = (Math.random() - 0.5) * 0.08; posture.y = (Math.random() - 0.5) * 0.1; posture.next = now + 18 + Math.random() * 22; }
    posture.cz = damp(posture.cz, posture.z + Math.sin(now * 0.23) * 0.015, 1, dt);
    posture.cy = damp(posture.cy, posture.y + Math.sin(now * 0.11 + 2) * 0.02, 1, dt);
    const spine = bone('spine');
    if (spine) spine.rotation.set(mind.stage === 'listening' ? 0.04 : 0, posture.cy, posture.cz);

    // Arms down - but only on a model that ships in a T-pose.
    const la = bone('leftUpperArm'), ra = bone('rightUpperArm');
    if (armsDown === null) armsDown = inTPose();
    if (la) la.rotation.z = armsDown ? -1.2 : 0;
    if (ra) ra.rotation.z = armsDown ? 1.2 : 0;

    vrm.update(dt);
    updateEars(now, dt);   // after update: spring bones won't overwrite a twitch
  }

  renderer.render(scene, camera);
}

// ---------------------------------------------------------------------------
// Debug panel and demo
// ---------------------------------------------------------------------------
function fakeVoice(seconds = 2.4) {
  const fps = 30, env = [], zcr = [];
  for (let i = 0; i < seconds * fps; i++) {
    const syll = Math.abs(Math.sin(i / fps * Math.PI * 4.2));
    env.push(+(syll * rand(0.45, 0.9)).toFixed(2));
    zcr.push(+rand(0.03, 0.28).toFixed(2));
  }
  handle({ t: 'voice', env, zcr, fps });
}

function debugPanel() {
  const buttons = {
    blink: () => { blink.next = 0; },
    twitch: () => twitch(0, 1),
    'left ear': () => twitch(1, 1),
    talk: () => { handle({ t: 'stage', status: 'Speaking...' }); fakeVoice(); },
    listen: () => handle({ t: 'stage', status: 'Listening...' }),
    think: () => handle({ t: 'stage', status: 'Thinking...' }),
    idle: () => handle({ t: 'stage', status: 'Idle' }),
    happy: () => handle({ t: 'mood', energy: 0.6, warmth: 1 }),
    sad: () => handle({ t: 'mood', energy: -0.8, warmth: -0.1 }),
    cross: () => handle({ t: 'mood', energy: 0.2, warmth: -0.9 }),
    neutral: () => handle({ t: 'mood', energy: 0, warmth: 0 }),
    'you: left': () => handle({ t: 'gaze', x: -0.8, y: -0.1 }),
    'you: right': () => handle({ t: 'gaze', x: 0.8, y: -0.1 }),
    'you: ahead': () => handle({ t: 'gaze', none: true }),
  };
  const box = document.getElementById('dbuttons');
  for (const [label, fn] of Object.entries(buttons)) {
    const b = document.createElement('button');
    b.textContent = label;
    b.onclick = fn;
    box.appendChild(b);
  }
  document.getElementById('dears').textContent = ears.length
    ? ears.map(e => `${e.node.name} (${e.side > 0 ? 'left' : 'right'})`).join('\n')
    : 'none found - name them in config.json: "portrait": {"ear_bones": [...]}';
  document.getElementById('dexpr').textContent = [...has].join(', ') || 'none';
  const names = [];
  vrm.scene.traverse(o => { if (o.isBone || /ear|hair|j_sec/i.test(o.name)) names.push(o.name); });
  document.getElementById('dbones').textContent = names.filter(n => /ear|hair|sec/i.test(n)).join('\n') || '(none)';
  setInterval(() => { document.getElementById('dstate').textContent =
    `${mind.stage} · energy ${mind.energy.toFixed(2)} warmth ${mind.warmth.toFixed(2)}`; }, 300);
}

async function demo() {
  const step = (ms, ev) => new Promise(r => setTimeout(() => { if (ev) handle(ev); r(); }, ms));
  for (;;) {
    await step(2500, { t: 'stage', status: 'Listening...' });
    await step(2200, { t: 'turn', text: 'hey luna' });
    await step(300, { t: 'stage', status: 'Thinking...' });
    await step(2600, { t: 'stage', status: 'Speaking...' });
    fakeVoice(3.0);
    await step(3200, { t: 'mood', energy: 0.5, warmth: 0.9 });
    await step(400, { t: 'stage', status: 'Idle' });
    await step(5000, { t: 'mood', energy: 0, warmth: 0.2 });
  }
}

// ---------------------------------------------------------------------------
try {
  try {
    vrm = await load(cfg.model || 'models/placeholder.vrm');
  } catch (e) {
    if (!cfg.model || cfg.model.endsWith('placeholder.vrm')) throw e;
    console.warn(e);
    vrm = await load('models/placeholder.vrm');
    say(`couldn't load ${cfg.model} - showing the placeholder`, true);
    setTimeout(() => say(''), 6000);
  }
  frame();
  say('');
  window.portrait = { handle, twitch, fakeVoice, blink, mind, get vrm() { return vrm; } };
  if (params.get('debug')) debugPanel();
  if (params.get('demo')) demo(); else connect();
} catch (e) {
  console.error(e);
  say(`couldn't load the model: ${e.message}`, true);
}
animate();
