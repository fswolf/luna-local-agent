// Luna's portrait: a VRM model that follows what she's doing.
//
// Everything it reacts to comes from the live monitor's event stream
// (/events, the same one /monitor reads): the stage she's at, her mood,
// tool calls, and - while she talks - the loudness envelope of each
// sentence as it starts playing, which is what moves her mouth. Nothing
// here talks back to the assistant.
//
//   ?bg=transparent   for an OBS browser source
//   ?frame=face       closer crop (default: bust); ?frame=full, all of her
//   ?debug=1          bone list and test buttons
//   ?demo=1           acts out a fake conversation, no assistant needed
//   ?holo=1 / ?holo=0 the hologram look on or off (overrides config.json)

import { THREE, GLTFLoader, VRMLoaderPlugin, VRMUtils,
         VRMAnimationLoaderPlugin, createVRMAnimationClip } from './vendor/luna-three.js';
import { createLook } from './look.js';
import { createHologram3D } from './hologram3d.js';
import { createGestures, IDLE } from './gestures.js';

const params = new URLSearchParams(location.search);
const note = document.getElementById('note');
const say = (text, keep) => {
  note.textContent = text;
  note.classList.toggle('hidden', !keep && !text);
};

if (params.get('bg') === 'transparent') document.body.classList.add('transparent');
if (params.get('debug')) document.body.classList.add('debug');

const cfg = await fetch('config.json' + location.search).then(r => r.json()).catch(() => ({}));

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

// The hologram look: config.json "hologram": {"enabled": true}, or ?holo=1.
// The URL sets how it starts; /holo and the tools pane switch it live.
const holoCfg = cfg.hologram || {};
const holoOn = params.has('holo') ? params.get('holo') !== '0' : !!holoCfg.enabled;
let holo = holoOn ? createHologram3D(THREE, renderer, holoCfg) : null;
function setHolo(on) {
  if (on) { if (holo) holo.on(); else holo = createHologram3D(THREE, renderer, holoCfg); }
  else holo?.off();
}

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
let moves = null;            // gestures.js: wave, hug, jump, idle things
let fx = 1;                  // -1 on a VRM 0.x model: it faces the other way in its own space
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
      : (/(^|[^a-z])ear([^a-z]|$)|ear_?[lr]\b|ears?$/.test(n) && !/(hear|year|pearl|gear|earring)/.test(n)
         || /catear_?1(_\d+)?$/.test(n)) && !o.isMesh;   // VRoid: J_Opt_L_CatEar1_01, the root of each ear
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
  const face = params.get('frame') === 'face', full = params.get('frame') === 'full';
  const height = full ? p.y + 0.45 : face ? 0.30 : 0.46;   // metres that should fit top to bottom
  const width = full ? 1.0 : face ? 0.24 : 0.40;           // ...and side to side
  const tan = Math.tan(THREE.MathUtils.degToRad(camera.fov / 2));
  const dist = Math.max((height / 2) / tan, (width / 2) / (tan * camera.aspect));
  const lookY = full ? (p.y + 0.3) / 2 : p.y + (face ? 0.065 : 0.02);
  camera.position.set(0, lookY + 0.01, p.z + dist);
  camera.lookAt(0, lookY, p.z);
  base.follow = full ? 0 : 0.7;   // close crops follow her up when she jumps
  base.lookY = lookY;
  base.headZ = p.z;
}

const base = { lookY: 1.45, headZ: 0, follow: 0.7 };

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
      if (next === 'listening' && mind.stage === 'speaking') holo?.glitch(0.5);   // talked over
      if (next === 'waking' && mind.stage !== 'waking') gesture('wave');
      if (next !== mind.stage) idle.next = clock.elapsedTime + rand(14, 30);
      mind.stage = next;
      look.setStage(next);
      holo?.bright(next === 'speaking' ? 1.12 : next === 'thinking' ? 0.9 : 1);
      break;
    }
    case 'holo': {      // /holo or the tools pane, while the page is open
      setHolo(!!ev.on);
      break;
    }
    case 'gaze':
      look.setTarget(ev);
      break;
    case 'turn':
      twitch(0, 0.6);
      said.text = ''; said.done.clear(); said.tagged = false; waveBack = false;
      // only you (voice, typed, Discord): chat has its own rules, and a
      // game's step prompt is full of "huge trolls" and "hello sailor"
      if (gmode.mode !== 'off' && /^(voice|typed|discord)?$/.test(ev.source || '')) fromYou(ev.text || '');
      break;
    case 'tok':         // her reply as it streams: act out *hugs*, *waves*... (the fallback)
      if (ev.p === 'a' && ev.s && gmode.mode !== 'off') { said.text = (said.text + ev.s).slice(-400); actOut(said.text); }
      break;
    case 'gesture':     // a [tag] she wrote, the meaning check, or /portrait wave
      if (ev.src === 'tag' || ev.src === 'meaning') {
        if (gmode.mode === 'off') break;
        if (ev.src === 'meaning' && said.done.size) break;   // keywords already caught it
        said.done.add(ev.name);
        if (ev.src === 'tag') said.tagged = true;
      }
      gesture(ev.name);
      break;
    case 'gesture_mode':   // switched in the tools pane or /portrait gestures
      gmode.mode = ev.mode; gmode.chat = ev.chat !== false;
      break;
    case 'chat':        // stream chat and Discord: !hug, hi, lol...
      if (gmode.chat) fromChat(ev);
      break;
    case 'mood': {
      const w = +ev.warmth || 0;
      if (w - mind.warmth > 0.2) moves?.wag(0.8), setTimeout(() => moves?.wag(0), 4000);
      if (w > 0.85 && mind.warmth <= 0.85 || w - mind.warmth > 0.3) blush.fluster = 1;   // that landed
      mind.energy = +ev.energy || 0;
      mind.warmth = w;
      break;
    }
    case 'tool':
      twitch(Math.random() < 0.5 ? 1 : -1, 0.8);
      look.glance(0.6);
      break;
    case 'flags': {
      const flags = ev.flags || [];
      if (flags.length) tilt.target = 0.12;   // a "hm" tilt when the review didn't like it
      if (flags.some(f => /^(tool failed|no answer|cut off)/.test(f))) { holo?.glitch(1); gesture('shrug'); }
      break;
    }
    case 'voice':
      if (ev.stop) { mind.voice.length = 0; break; }
      mind.voice.push({ env: ev.env || [], zcr: ev.zcr || [], fps: ev.fps || 30, start: performance.now() });
      if (mind.voice.length > 3) mind.voice.shift();
      break;
    case 'reload':      // /portrait use switched the model
      location.reload();
      break;
    case 'done':
      tilt.target = 0;
      break;
  }
}

// ---------------------------------------------------------------------------
// Gestures: what sets them off
// ---------------------------------------------------------------------------
function gesture(name, publicOnly = false) {
  if (!moves) return;
  if (moves.playing().some(n => n.replace('_left', '') === name)) return;   // already doing it
  if (name === 'wave' && !moves.hasClip('wave')) name = Math.random() < 0.7 ? 'wave' : 'wave_left';
  if (moves.play(name, publicOnly)) {
    idle.next = clock.elapsedTime + rand(20, 40);
    if (/wave|hug|jump|bounce/.test(name)) { moves.wag(name === 'hug' ? 0.5 : 1); setTimeout(() => moves.wag(0), 3500); }
  }
}

// You say hi, bye, or ask for a hug.
function fromYou(text) {
  const t = text.toLowerCase();
  if (/\b(hugs?|hugging|cuddles?)\b|🤗/.test(t)) setTimeout(() => gesture('hug'), 1200);
  else if (/^\W*(hi|hey|hello|hiya|heya|yo|morning|good (morning|evening|afternoon)|bye|goodbye|good ?night|see (you|ya)|night night)\b/.test(t)
           || /👋/.test(t)) waveBack = true;
}
let waveBack = false;

// Chat, answered or not. Viewers can ask with !wave, !hug, !jump,
// !bounce (or !dance), !shrug, !stretch; plain chat works too: a hug
// for her, someone new saying hi, bye, laughing, hype. Rate-limited so
// a busy chat doesn't keep her flailing.
const chatSeen = new Set();
const chatCool = { cmd: 0, auto: 0 };
const CHAT_CMDS = { wave: 'wave', hug: 'hug', jump: 'jump', bounce: 'bounce', dance: 'bounce',
                    shrug: 'shrug', stretch: 'stretch', hi: 'wave', hello: 'wave', hop: 'bounce' };
function fromChat(ev) {
  const t = String(ev.text || '').toLowerCase().trim(), who = String(ev.who || '').toLowerCase();
  const now = clock.elapsedTime, first = who && !chatSeen.has(who);
  if (who) chatSeen.add(who);
  const cmd = t.match(/^!(\w+)/);
  if (cmd) {
    if (CHAT_CMDS[cmd[1]] && now > chatCool.cmd) { chatCool.cmd = now + 5; chatCool.auto = now + 8; gesture(CHAT_CMDS[cmd[1]], true); }
    return;
  }
  if (now < chatCool.auto) return;
  let pick = null;
  if (/\*[^*]{0,30}\bhug|\bhugs?\b.{0,20}\bluna\b|\bluna\b.{0,20}\bhugs?\b|\bgroup hug\b|🤗|\(hug\)|<3 hug/.test(t)) pick = 'hug';
  else if (/^\W*(hi|hey|hello|hiya|heya|howdy|yo|o\/|o7|👋|good (morning|evening|afternoon))\b/.test(t) && first) pick = 'wave';
  else if (/^\W*(bye|goodbye|good ?night|gn|cya|see (you|ya)|later|night night)\b|👋/.test(t)) pick = 'wave';
  else if (/\b(pog|poggers|pogchamp|hype|lets go+|let'?s go+)\b|🎉|🔥/.test(t) && Math.random() < 0.4) pick = 'jump';
  else if (/\b(lol|lmao|lmfao|rofl|kekw|haha+)\b|😂|🤣/.test(t) && Math.random() < 0.3) pick = 'bounce';
  if (pick) { chatCool.auto = now + 12; gesture(pick, true); }
}

// She acts out what she writes: *hugs*, *waves*, *jumps*, 🤗, 👋 ...
const said = { text: '', done: new Set(), tagged: false };
// How her replies set gestures off (gestures.py): tags, meaning, keywords, off.
const gmode = { mode: cfg.gestures || 'tags', chat: cfg.chat_gestures !== false };
const ACTS = [
  ['hug', /\*[^*\n]{0,40}\b(hug|hugs|hugging|cuddle|cuddles|squeez)\w*[^*\n]{0,40}\*|🤗/i],
  ['wave', /\*[^*\n]{0,40}\b(wave|waves|waving)\b[^*\n]{0,40}\*|👋/i],
  ['jump', /\*[^*\n]{0,40}\b(jump|jumps|jumping|leaps?)\b[^*\n]{0,40}\*/i],
  ['bounce', /\*[^*\n]{0,40}\b(bounc\w*|hops?|hopping|wiggles?|happy dance)\b[^*\n]{0,40}\*/i],
  ['stretch', /\*[^*\n]{0,40}\b(stretch\w*|yawns?)\b[^*\n]{0,40}\*/i],
  ['shrug', /\*[^*\n]{0,40}\bshrug\w*[^*\n]{0,40}\*|🤷/i],
  ['tuck_hair', /\*[^*\n]{0,40}\b(tucks?|brush\w*) (her |a )?(hair|strand)[^*\n]{0,40}\*/i],
];
function actOut(text) {
  if (said.tagged) return;          // she picked one herself: that wins
  for (const [name, re] of ACTS) {
    if (said.done.has(name) || !re.test(text)) continue;
    said.done.add(name);
    gesture(name);
    return;
  }
  // said hi back without acting it out: wave anyway
  if (waveBack && /\b(hi|hey|hello|hiya|heya|morning|evening|bye|night|see you)\b/i.test(text)) {
    waveBack = false;
    if (!said.done.size) { said.done.add('wave'); gesture('wave'); }
  }
}

// On her own: every so often while idle, something small. While she
// talks, now and then a hand comes up.
const idle = { next: 25, last: '', talkNext: 0 };
function idleMoves(now, talking) {
  if (!moves || moves.busy()) return;
  if (mind.stage === 'idle' && now > idle.next) {
    let pick;
    const pool = IDLE.concat(moves.clipsWhere('idle'));   // clips marked "idle" join in
    do { pick = pool[Math.floor(Math.random() * pool.length)]; } while (pick === idle.last && pool.length > 1);
    idle.last = pick;
    moves.play(pick);
    idle.next = now + rand(25, 55);
  }
  if (talking && now > idle.talkNext) {
    const talk = moves.clipsWhere('talk');                  // clips marked "talk" too
    if (idle.talkNext && Math.random() < 0.55)
      moves.play(talk.length && Math.random() < 0.5 ? talk[Math.floor(Math.random() * talk.length)]
                 : Math.random() < 0.6 ? 'explain' : 'explain_left');
    idle.talkNext = now + rand(5, 11);
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
    // a quiet smile while she isn't talking: VRoid's "happy" opens the mouth
    setExpr(k, k === 'happy' && quietSmile() ? moodNow[k] * mouthShut.talk : moodNow[k]);
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
  const raw = clock.getDelta();
  const dt = Math.min(raw, 0.05);
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
    if (head) head.rotation.set(fx * headRot.x * 0.6, headRot.y * 0.6, fx * headRot.z * 0.6);
    if (neck) neck.rotation.set(fx * headRot.x * 0.4, headRot.y * 0.4, fx * headRot.z * 0.4);

    // Breathing: in quicker than out, each breath a little different, the
    // shoulders lifting with it so it reads on a skinned model.
    breathing.phase += Math.PI * 2 * (talking > 0.05 ? 0.3 : mind.stage === 'thinking' ? 0.28 : 0.22) * breathing.jitter * dt;
    if (breathing.phase > Math.PI * 2) { breathing.phase -= Math.PI * 2; breathing.jitter = 0.85 + Math.random() * 0.3; }
    const k = breathing.phase / (Math.PI * 2);
    const breath = k < 0.4 ? (1 - Math.cos(Math.PI * k / 0.4)) / 2 : (1 + Math.cos(Math.PI * (k - 0.4) / 0.6)) / 2;
    const chest = bone('upperChest') || bone('chest');
    if (chest) chest.rotation.set(-fx * breath * 0.035, 0, 0);
    const ls = bone('leftShoulder'), rs = bone('rightShoulder');
    if (ls) ls.rotation.set(0, 0, fx * breath * 0.05);
    if (rs) rs.rotation.set(0, 0, -fx * breath * 0.05);

    // The body sways on its own and shifts its weight now and then, so the
    // hair (spring bones) has something to swing from besides the head.
    if (now > posture.next) { posture.z = (Math.random() - 0.5) * 0.08; posture.y = (Math.random() - 0.5) * 0.1; posture.next = now + 18 + Math.random() * 22; }
    posture.cz = damp(posture.cz, posture.z + Math.sin(now * 0.23) * 0.015, 1, dt);
    posture.cy = damp(posture.cy, posture.y + Math.sin(now * 0.11 + 2) * 0.02, 1, dt);
    const spine = bone('spine');
    if (spine) spine.rotation.set(fx * (mind.stage === 'listening' ? 0.04 : 0), posture.cy, fx * posture.cz);

    // Arms down - but only on a model that ships in a T-pose - elbows
    // soft, fingers a little curled. Then whatever gesture is playing.
    if (armsDown === null) armsDown = inTPose();
    moves.rest(armsDown);
    idleMoves(now, talking > 0.05);
    moves.update(Math.min(raw, 0.2));   // real time, so a wave lasts as long on a slow machine
    const hy = moves.hipsY() * base.follow;
    camera.position.y = base.lookY + 0.01 + hy;
    camera.lookAt(0, base.lookY + hy, base.headZ);
    for (const [k, v] of Object.entries(moves.expr())) {
      if (k === 'blush') blush.gesture = v;
      else if (has.has(k)) vrm.expressionManager.setValue(k, Math.max(vrm.expressionManager.getValue(k) || 0, v));
    }
    if (!Object.hasOwn(moves.expr(), 'blush')) blush.gesture = 0;
    updateBlush(dt);

    vrm.update(dt);
    closeMouth(talking);
    updateEars(now, dt);   // after update: spring bones won't overwrite a twitch
  }

  if (holo && holo.isOn()) holo.render(scene, camera);
  else renderer.render(scene, camera);
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

// Many VRoid faces rest with the lips parted, and their happy and relaxed
// expressions open the mouth further. When she isn't talking, a "mouth
// closed" morph (VRoid: Fcl_MTH_Close) holds it shut; it lets go as her
// voice opens it. How firmly: "vrm": {"mouth_close": 0..1} in the model
// folder's luna.json, or the slider on the ?debug=1 page.
//
// Her mood's smile has the same problem: VRoid's "happy" is an open-mouthed
// grin. While she's quiet, a model with VRoid's separate eye and mouth
// shapes (Fcl_EYE_Joy, Fcl_MTH_Fun) smiles with them instead, mouth closed;
// the grin comes back as she talks. Gestures keep their open smiles.
const mouthShut = { amount: cfg.vrm?.mouth_close ?? 0.7, targets: null, smile: null, now: 0, talk: 0 };
function findMorphs() {
  mouthShut.targets = []; mouthShut.smile = [];
  vrm.scene.traverse(o => {
    const d = o.morphTargetDictionary;
    if (!d) return;
    const key = Object.keys(d).find(k => /(^|_)mth_close$|mouth_?close/i.test(k));
    if (key !== undefined) mouthShut.targets.push([o, d[key]]);
    if ('Fcl_EYE_Joy' in d && 'Fcl_MTH_Fun' in d) mouthShut.smile.push([o, d.Fcl_EYE_Joy, d.Fcl_MTH_Fun]);
  });
}
function quietSmile() {
  if (!mouthShut.smile) findMorphs();
  return mouthShut.smile.length > 0 && cfg.vrm?.quiet_smile !== false;
}
function closeMouth(talking) {
  if (!mouthShut.targets) findMorphs();
  mouthShut.talk += ((talking > 0.03 ? 1 : 0) - mouthShut.talk) * (talking > 0.03 ? 0.3 : 0.05);
  const em = vrm.expressionManager, v = k => em?.getValue(k) || 0;
  const open = Math.max(Math.min(1, talking * 5), v('surprised'), v('happy'),
                        v('aa'), v('ih'), v('ou'), v('ee'), v('oh'));   // a pucker or a yawn isn't held shut
  mouthShut.now += (mouthShut.amount * (1 - open) - mouthShut.now) * 0.25;
  for (const [o, i] of mouthShut.targets) o.morphTargetInfluences[i] = mouthShut.now;
  if (quietSmile()) {
    const s = moodNow.happy * (1 - mouthShut.talk);
    for (const [o, eye, mth] of mouthShut.smile) { o.morphTargetInfluences[eye] = s * 0.8; o.morphTargetInfluences[mth] = s; }
  }
}

// Blush. VRoid paints the cheeks into the face texture, so there's no
// expression to turn up; instead a second copy of the face skin, sharing
// its skeleton and shape keys, carries a pink glow painted in the face's
// own texture layout and fades in over the cheeks. It moves with every
// expression because it is the same face. A model with its own "blush"
// expression uses that instead.
//
// What raises it: a gesture that asks (hug, kiss, shy), a big jump in
// warmth (flustered, then fading), and a little while warmth stays high.
// luna.json, "vrm": {"blush": {"left": [u, v], "right": [u, v], "size": 0.075,
//                               "color": "#ff5f86", "strength": 0.65}}
// (u, v from the top-left of the face texture; the default is VRoid's.)
const blush = { now: 0, gesture: 0, fluster: 0, layer: null, tried: false, test: null };
function blushLayer() {
  if (blush.tried) return blush.layer;
  blush.tried = true;
  const o = cfg.vrm?.blush || {};
  let skin = null;
  vrm.scene.traverse(m => {
    if (!skin && m.isSkinnedMesh && [].concat(m.material).some(x => /face.*skin|skin.*face/i.test(x.name || ''))) skin = m;
  });
  if (!skin || o.enabled === false) return null;
  const S = 512, cv = document.createElement('canvas');
  cv.width = cv.height = S;
  const g = cv.getContext('2d');
  const col = new THREE.Color(o.color || '#ff5f86'), [r, gg, b] = [col.r, col.g, col.b].map(x => Math.round(x * 255));
  for (const [u, v] of [o.left || [0.33, 0.61], o.right || [0.67, 0.61]]) {
    const rad = (o.size || 0.075) * S;
    const grad = g.createRadialGradient(u * S, v * S, 0, u * S, v * S, rad);
    grad.addColorStop(0, `rgba(${r},${gg},${b},0.75)`);
    grad.addColorStop(0.45, `rgba(${r},${gg},${b},0.38)`);
    grad.addColorStop(1, `rgba(${r},${gg},${b},0)`);
    g.fillStyle = grad;
    g.beginPath(); g.ellipse(u * S, v * S, rad * 1.25, rad, 0, 0, Math.PI * 2); g.fill();
  }
  const tex = new THREE.CanvasTexture(cv);
  tex.flipY = false;                       // glTF texture layout
  tex.colorSpace = THREE.SRGBColorSpace;
  const mat = new THREE.MeshBasicMaterial({ map: tex, transparent: true, opacity: 0, depthWrite: false,
                                            polygonOffset: true, polygonOffsetFactor: -2, polygonOffsetUnits: -4 });
  const layer = new THREE.SkinnedMesh(skin.geometry, mat);
  layer.bind(skin.skeleton, skin.bindMatrix);
  layer.morphTargetInfluences = skin.morphTargetInfluences;      // same array: same expression, always
  layer.morphTargetDictionary = skin.morphTargetDictionary;
  layer.frustumCulled = false;
  layer.renderOrder = (skin.renderOrder || 0) + 1;
  skin.parent.add(layer);
  layer.position.copy(skin.position); layer.quaternion.copy(skin.quaternion); layer.scale.copy(skin.scale);
  blush.layer = { mesh: layer, mat, strength: o.strength ?? 0.65 };
  return blush.layer;
}
function updateBlush(dt) {
  blush.fluster = Math.max(0, blush.fluster - dt / 7);                 // flustered fades over ~7 s
  const warm = Math.max(0, (mind.warmth - 0.6) * 0.9);
  const target = blush.test ?? Math.min(1, Math.max(blush.gesture, blush.fluster, warm));
  blush.now = damp(blush.now, target, target > blush.now ? 2.5 : 0.8, dt);   // rises quicker than it fades
  if (has.has('blush')) { vrm.expressionManager.setValue('blush', blush.now); return; }
  const l = blushLayer();
  if (l) { l.mat.opacity = blush.now * l.strength; l.mesh.visible = blush.now > 0.01; }
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
    glitch: () => holo?.glitch(1),
    wave: () => gesture('wave'), hug: () => gesture('hug'), jump: () => gesture('jump'),
    shrug: () => gesture('shrug'), stretch: () => gesture('stretch'), 'look at hand': () => gesture('look_hand'),
    'tuck hair': () => gesture('tuck_hair'), bounce: () => gesture('bounce'), explain: () => gesture('explain'),
    'blow a kiss': () => gesture('kiss'), shy: () => gesture('shy'), fluster: () => { blush.fluster = 1; },
    'wag tail': () => { moves.wag(1); setTimeout(() => moves.wag(0), 3000); },
    'holo on/off': () => setHolo(!(holo && holo.isOn())),
  };
  const tune = document.getElementById('dtune');
  if (tune) {
    const row = document.createElement('label');
    row.textContent = 'mouth closed ';
    const r = document.createElement('input');
    Object.assign(r, { type: 'range', min: 0, max: 1, step: 0.05, value: mouthShut.amount });
    const out = document.createElement('span');
    out.textContent = ` ${mouthShut.amount}`;
    r.oninput = () => { mouthShut.amount = +r.value; out.textContent = ` ${r.value}  ("vrm": {"mouth_close": ${r.value}} in luna.json)`; };
    row.append(r, out);
    tune.appendChild(row);
    const row2 = document.createElement('label');
    row2.textContent = ' blush ';
    const r2 = document.createElement('input');
    Object.assign(r2, { type: 'range', min: -0.05, max: 1, step: 0.05, value: -0.05, title: 'left end: automatic' });
    const out2 = document.createElement('span');
    out2.textContent = ' auto';
    r2.oninput = () => { blush.test = +r2.value < 0 ? null : +r2.value; out2.textContent = blush.test == null ? ' auto' : ` ${r2.value}`; };
    row2.append(document.createElement('br'), r2, out2);
    row.after(row2);
  }
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
    await step(10, { t: 'tok', p: 'a', s: 'hey you! *waves*' });
    await step(300, { t: 'stage', status: 'Thinking...' });
    await step(2600, { t: 'stage', status: 'Speaking...' });
    fakeVoice(3.0);
    await step(3200, { t: 'mood', energy: 0.5, warmth: 0.9 });
    await step(400, { t: 'stage', status: 'Idle' });
    await step(5000, { t: 'mood', energy: 0, warmth: 0.2 });
  }
}

// ---------------------------------------------------------------------------
// Animation clips: the .vrma files in portrait/animations (livefeed lists
// them, with clips.json's settings). They load in the background; until
// one has, its gesture plays the built-in way.
async function loadClips() {
  const list = cfg.clips || [], loaded = [], failed = [];
  const loader = new GLTFLoader();
  loader.register(parser => new VRMAnimationLoaderPlugin(parser));
  await Promise.all(list.map(async c => {
    try {
      const gltf = await loader.loadAsync(encodeURI(c.file));
      const anim = gltf.userData.vrmAnimations?.[0];
      if (!anim) throw new Error('no VRM animation in it');
      moves.addClip(c.name, createVRMAnimationClip(anim, vrm), c);
      loaded.push(c);
    } catch (e) {
      console.warn('clip', c.file, e);
      failed.push(`${c.file}: ${e.message || e}`);
    }
  }));
  const box = document.getElementById('dclips');
  if (box && list.length) {
    box.textContent = '';
    for (const name of moves.clipNames()) {
      const b = document.createElement('button');
      const v = loaded.filter(c => c.name === name);
      b.textContent = name + (v.length > 1 ? ` (${v.length})` : '') + (v.some(c => c.private) ? ' 🔒' : '');
      b.title = v.map(c => c.file).join('\n');
      b.onclick = () => moves.play(name);
      box.appendChild(b);
    }
    if (failed.length) {
      const p = document.createElement('pre');
      p.textContent = failed.join('\n');
      box.appendChild(p);
    }
  }
}

// ---------------------------------------------------------------------------
try {
  vrm = await load(cfg.model);
  moves = createGestures(THREE, vrm);
  fx = vrm.meta?.metaVersion === '0' ? -1 : 1;
  frame();
  say('');
  window.portrait = { handle, twitch, fakeVoice, blink, mind, gesture, mouthShut, blush, get moves() { return moves; }, get vrm() { return vrm; }, get holo() { return holo; } };
  if (params.get('debug')) debugPanel();
  loadClips();
  if (params.get('demo')) demo(); else connect();
} catch (e) {
  console.error(e);
  say(`couldn't load the model: ${e.message}`, true);
}
animate();
