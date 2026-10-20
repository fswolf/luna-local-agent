// Luna's portrait: a VRM model that follows what she's doing.
//
// Everything it reacts to comes from the live monitor's event stream
// (/events, the same one /monitor reads): the stage she's at, her mood,
// tool calls, and - while she talks - the loudness envelope of each
// sentence as it starts playing, which is what moves her mouth. Nothing
// here talks back to the assistant.
//
//   ?bg=transparent   for an OBS browser source
//   ?frame=face       closer crop (default: bust); ?frame=full, all of her.
//                     Without it, config.json portrait.frame, switched live from the tools pane
//   ?debug=1          bone list and test buttons
//   ?demo=1           acts out a fake conversation, no assistant needed
//   ?holo=1 / ?holo=0 the hologram look on or off (overrides config.json)
//   ?fan=1            for an HDMI hologram fan: black, all of her, centred, nothing else
//   ?nocast           never cast to a WiFi hologram fan from this page (fan.js)

import { THREE, GLTFLoader, VRMLoaderPlugin, VRMUtils,
         VRMAnimationLoaderPlugin, createVRMAnimationClip } from './vendor/luna-three.js';
import { createLook } from './look.js';
import { createHologram3D } from './hologram3d.js';
import { createEmotes } from './emotes.js';
import { createTouch } from './touch.js';
import { createFan } from './fan.js';
import { createGestures, GESTURES, IDLE, NAMES as GESTURE_NAMES, FAILED as GESTURE_FAILED, KEYWORDS as GESTURE_KEYWORDS } from './gestures.js';

const params = new URLSearchParams(location.search);
const note = document.getElementById('note');
const say = (text, keep) => {
  note.textContent = text;
  note.classList.toggle('hidden', !keep && !text);
};

if (params.get('bg') === 'transparent') document.body.classList.add('transparent');
if (params.get('debug')) document.body.classList.add('debug');

const cfg = await fetch('config.json' + location.search).then(r => r.json()).catch(() => ({}));
// ?fan=1: the page an HDMI hologram fan shows. Black is invisible on a fan.
const fanView = params.get('fan') === '1';
if (fanView) document.body.classList.add('fan');
let framing = params.get('frame') || (fanView ? cfg.fan?.framing || 'full' : cfg.frame) || 'bust';   // bust, face or full

// ---------------------------------------------------------------------------
// Scene
// ---------------------------------------------------------------------------
const renderer = new THREE.WebGLRenderer({ antialias: true, alpha: true, preserveDrawingBuffer: true });
renderer.setPixelRatio(Math.min(devicePixelRatio, 2));
renderer.setSize(innerWidth, innerHeight);
renderer.outputColorSpace = THREE.SRGBColorSpace;
renderer.setClearColor(0x000000, fanView ? 1 : 0);
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
const emotes = createEmotes(THREE, scene);   // hearts, sweat drop... beside her head

// The hologram look: config.json "hologram": {"enabled": true}, or ?holo=1.
// The URL sets how it starts; /holo and the tools pane switch it live.
const holoCfg = cfg.hologram || {};
const holoOn = params.has('holo') ? params.get('holo') !== '0' : !!holoCfg.enabled && !fanView;   // a fan is the hologram
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
let fan = null;              // fan.js: casting to a WiFi hologram fan
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
  const face = framing === 'face', full = framing === 'full';
  const height = full ? p.y + 0.45 : face ? 0.30 : 0.46;   // metres that should fit top to bottom
  const width = full ? 1.0 : face ? 0.24 : 0.40;           // ...and side to side
  const tan = Math.tan(THREE.MathUtils.degToRad(camera.fov / 2));
  const dist = Math.max((height / 2) / tan, (width / 2) / (tan * camera.aspect));
  const lookY = full ? (p.y + 0.3) / 2 : p.y + (face ? 0.065 : 0.02);
  camera.position.set(0, lookY + 0.01, p.z + dist);
  camera.lookAt(0, lookY, p.z);
  base.follow = full ? 0 : 0.7;   // close crops follow her up when she jumps
  base.dist = dist;
  base.lookY = lookY;
  base.headZ = p.z;
  base.headY ||= p.y;   // her standing height, measured once (the fan's framing keeps to it)
}

const base = { lookY: 1.45, headZ: 0, follow: 0.7, dist: 2, headY: 0 };

// The viewer (?debug=1): left-drag to turn around her, wheel to zoom, double-click
// to put the camera back. Off on the live portrait, so a stray click in OBS
// or on the desktop never moves her.
const orbit = { yaw: 0, pitch: 0, zoom: 1 };
if (params.get('debug')) {
  const el = renderer.domElement;
  let drag = null;
  el.style.cursor = 'grab';
  // Left button only turns her; no right-click menu in the viewer.
  document.addEventListener('contextmenu', e => e.preventDefault());
  el.addEventListener('pointerdown', e => {
    if (e.button !== 0) return;
    drag = { x: e.clientX, y: e.clientY }; el.setPointerCapture(e.pointerId); el.style.cursor = 'grabbing';
    view.target = null; view.back = 0;     // you've taken over: no easing, no drifting back
  });
  el.addEventListener('pointermove', e => {
    if (!drag) return;
    orbit.yaw -= (e.clientX - drag.x) * 0.008;
    orbit.pitch = Math.max(-1.2, Math.min(1.2, orbit.pitch + (e.clientY - drag.y) * 0.006));
    drag = { x: e.clientX, y: e.clientY };
  });
  const stop = () => { drag = null; el.style.cursor = 'grab'; };
  el.addEventListener('pointerup', stop);
  el.addEventListener('pointercancel', stop);
  el.addEventListener('wheel', e => { e.preventDefault(); orbit.zoom = Math.max(0.25, Math.min(4, orbit.zoom * Math.exp(e.deltaY * 0.001))); }, { passive: false });
  el.addEventListener('dblclick', () => { orbit.yaw = 0; orbit.pitch = 0; orbit.zoom = 1; view.target = null; view.back = 0; });
}

// ---------------------------------------------------------------------------
// What she's doing - from the event stream
// ---------------------------------------------------------------------------
const mind = {
  stage: 'idle',              // idle listening thinking speaking waking
  label: '',                  // the mood's name (loving, mad...)
  row: '',                    // 'lewd' or 'grudge' when she's past the grid's edges
  energy: 0, warmth: 0,       // mood dials, about -1..1
  face: null,                 // the mood's face from agent/moods.json (null: work it out from the dials)
  idle: [],                   // gestures this mood drifts into
  hold: '',                   // a pose held for as long as the mood says (walked away: 'sulk')
  emote: '',                  // an emote this mood shows now and then (loving: 'hearts')
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
    case 'frame':       // the tools pane: bust or full, while the page is open (a ?frame= page keeps its own)
      if (!params.get('frame') && !fanView && ['bust', 'face', 'full'].includes(ev.frame)) { framing = ev.frame; frame(); }
      break;
    case 'holo': {      // /holo or the tools pane, while the page is open
      setHolo(!!ev.on && !fanView);   // a fan is the hologram already
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
      if (w > 0.85 && mind.warmth <= 0.85 || w - mind.warmth > 0.3) blush.fluster = 1;   // that landed
      mind.energy = +ev.energy || 0;
      mind.warmth = w;
      mind.label = typeof ev.label === 'string' ? ev.label : '';
      mind.row = typeof ev.row === 'string' ? ev.row : '';
      mind.tame = !!ev.tame;      // live on a stream with lewd off: no lewd moves
      mind.face = ev.face && typeof ev.face === 'object' ? ev.face : null;
      mind.idle = Array.isArray(ev.idle) ? ev.idle : [];
      // A held pose (walked away: "sulk"). Let go of it when the mood
      // stops asking - she turns back.
      const hold = typeof ev.hold === 'string' ? ev.hold : '';
      if (mind.hold && hold !== mind.hold && moves?.playing().includes(mind.hold)) moves.stop();
      mind.hold = hold;
      // a mood that shows an emote now and then (loving, flirty: hearts)
      const em = typeof ev.emote === 'string' ? ev.emote : '';
      if (em !== mind.emote) emoteNext = clock.elapsedTime + rand(10, 40);
      mind.emote = em;
      break;
    }
    case 'emote':      // a compliment landed (moods.json "compliment")
      emote(ev.name);
      break;
    case 'feeling':    // a quick one from reading the exchange: laughing, embarrassed...
      feel.face = ev.face || {};
      feel.start = clock.elapsedTime;
      feel.seconds = +ev.seconds || 6;
      if (ev.gesture && moves && !moves.busy()) gesture(ev.gesture);
      if (ev.emote) emote(ev.emote);
      break;
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
// Emotes: one burst at a time, 30 s apart at least, and rare enough in a
// mood that they still mean something
// ---------------------------------------------------------------------------
let emoteNext = 0, emoteLast = -99;
function emote(name) {
  if (!name || emotes.busy() || clock.elapsedTime - emoteLast < 30) return;
  emoteLast = clock.elapsedTime;
  emotes.show(name);
}
function moodEmote(now) {
  if (!mind.emote || now < emoteNext || mind.stage === 'listening') return;
  emoteNext = now + rand(180, 360);
  emote(mind.emote);
}

// ---------------------------------------------------------------------------
// Gestures: what sets them off
// ---------------------------------------------------------------------------
// Turning: a gesture file with view: (degrees) swings the camera round her
// instead of moving her - Luna's "turn around". Eased; back to the front on
// its own after VIEW_HOLD seconds.
const VIEW_HOLD = 120;
const view = { target: null, back: 0 };
function turnTo(deg) {
  const tau = Math.PI * 2;
  orbit.yaw = ((orbit.yaw % tau) + tau + Math.PI) % tau - Math.PI;      // into -π..π, so she turns the short way
  let t = deg * Math.PI / 180;
  if (t - orbit.yaw > Math.PI) t -= tau;
  if (orbit.yaw - t > Math.PI) t += tau;
  view.target = t;
  view.back = deg ? clock.elapsedTime + VIEW_HOLD : 0;
}

// Sounds: portrait/sounds/ (yours, not in git). A gesture file can name one:
//   sound: 'touch-self'                 the file touch-self.mp3 (or .ogg/.wav), or a
//                                       folder of that name - a random clip from it
//   sound: { name, from, len }          from: seconds in, or 'random'; len: how long
//                                       (default: the gesture's length)
// It fades out at the end, or when another gesture starts. No file, no
// sound, nothing else changes; portrait.sounds: false turns them all off.
let SOUNDS = {};
fetch('sounds/index.json').then(r => (r.ok ? r.json() : {})).then(j => { SOUNDS = j || {}; }).catch(() => {});
const sound = { el: null, timer: 0, blobs: {} };
// Loaded whole, once: the portrait's little server can't send part of a
// file, and without that the browser can't jump into the middle of a clip.
function clipUrl(file) {
  return sound.blobs[file] ??= fetch(file).then(r => (r.ok ? r.blob() : null)).then(b => (b ? URL.createObjectURL(b) : null)).catch(() => null);
}
function stopSound(fade = 0.5) {
  sound.ticket = (sound.ticket || 0) + 1;          // a clip still loading won't start
  const el = sound.el;
  if (!el) return;
  sound.el = null;
  clearTimeout(sound.timer);
  const v0 = el.volume, t0 = performance.now();
  const step = setInterval(() => {                 // a timer, not a frame: OBS may not be drawing
    const k = 1 - (performance.now() - t0) / (fade * 1000);
    if (k <= 0) { clearInterval(step); el.pause(); } else el.volume = v0 * k;
  }, 30);
}
function playSound(spec, dur) {
  if (cfg.sounds === false || !spec) return;
  const s = typeof spec === 'string' ? { name: spec } : spec;
  const files = SOUNDS[String(s.name || '').toLowerCase()];
  if (!files || !files.length) return;
  stopSound(0.2);
  const ticket = sound.ticket = (sound.ticket || 0) + 1;
  clipUrl(files[Math.floor(Math.random() * files.length)]).then(url => {
    if (!url || ticket !== sound.ticket) return;     // gone, or another gesture took over meanwhile
    const el = new Audio(url);
    el.volume = Math.max(0, Math.min(1, cfg.sound_volume ?? 0.8));
    const len = +s.len || dur || 0;
    el.addEventListener('loadedmetadata', () => {
      const room = Math.max(0, (el.duration || 0) - len);
      el.currentTime = s.from === 'random' ? Math.random() * room : Math.min(+s.from || 0, room);
      el.play().catch(() => {});      // a browser that wants a click first: just no sound
    }, { once: true });
    sound.el = el;
    if (len) sound.timer = setTimeout(() => { if (sound.el === el) stopSound(0.9); }, Math.max(0.1, len - 0.9) * 1000);
  });
}
// How long a gesture (or a whole chain) runs, for its sound
function lengthOf(g) {
  return Array.isArray(g.chain) ? g.chain.reduce((t, n) => t + (+GESTURES[n]?.dur || 0), 0) : +g.dur || 0;
}

// Is the view (or where it's heading) round the back of her?
function facingAway() { return Math.cos(view.target ?? orbit.yaw) < -0.5; }

function gesture(name, publicOnly = false) {
  if (!moves) return;
  if (GESTURES[name] && GESTURES[name].view != null) {
    const deg = +GESTURES[name].view || 0;
    turnTo(deg === 180 && facingAway() ? 0 : deg);      // "turn around" while turned round: back to you
    return;
  }
  if (moves.playing().some(n => n.replace('_left', '') === name)) return;   // already doing it
  if (mind.tame && GESTURES[name]?.lewd) return;
  if (name === 'wave' && !moves.hasClip('wave')) name = Math.random() < 0.7 ? 'wave' : 'wave_left';
  if (moves.play(name, publicOnly)) {
    idle.next = clock.elapsedTime + rand(20, 40);
    const g = GESTURES[name.replace(/_left$/, '')];
    if (g && g.sound) playSound(g.sound, lengthOf(g)); else stopSound();
    // a gesture can show emotes (emote: 'sweat', { name, at: seconds in }, or a
    // list of those, one after another) and swish her tail while it plays (wag: 0-1)
    if (g && g.emote) {
      for (const one of [].concat(g.emote)) {
        const e = typeof one === 'string' ? { name: one } : one;
        setTimeout(() => { if (moves.playing().includes(name)) { emoteLast = -99; emote(e.name); } }, (+e.at || 0) * 1000);
      }
    }
    if (g && (g.wag || g.tail_up)) {
      if (g.tail_up) moves.wag(+g.tail_up, 0); else moves.wag(+g.wag);
      setTimeout(() => { if (!moves.playing().includes(name)) moves.wag(0); }, lengthOf(g) * 1000 + 300);
    }
    if (/wave|hug|jump|bounce/.test(name)) { moves.wag(name === 'hug' ? 0.5 : 1); setTimeout(() => moves.wag(0), 3500); }
    if (name === 'look_back') { moves.wag(0.6); setTimeout(() => moves.wag(0), 6000); }   // a slow swish while she's bent over
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
// !bounce, !dance, !jog (or !run), !shrug, !stretch, !turn (round and back),
// !side, !front, !kiss, !bashful; plain chat works too: a hug
// for her, someone new saying hi, bye, laughing, hype. Rate-limited so
// a busy chat doesn't keep her flailing.
const chatSeen = new Set();
const chatCool = { cmd: 0, auto: 0 };
const CHAT_CMDS = { wave: 'wave', hug: 'hug', jump: 'jump', bounce: 'bounce',
                    shrug: 'shrug', stretch: 'stretch', hi: 'wave', hello: 'wave', hop: 'bounce', dance: 'dance',
                    jog: 'jog', run: 'jog', side: 'turn_side', front: 'face_me',
                    kiss: 'blow_kiss', blowkiss: 'blow_kiss', bashful: 'bashful', blush: 'bashful',
                    turn: 'turn_around' };      // !turn: round, and again to come back (see gesture())
function fromChat(ev) {
  const t = String(ev.text || '').toLowerCase().trim(), who = String(ev.who || '').toLowerCase();
  const now = clock.elapsedTime, first = who && !chatSeen.has(who);
  if (who) chatSeen.add(who);
  const cmd = t.match(/^!(\w+)/);
  if (cmd) {
    const c = Object.hasOwn(CHAT_CMDS, cmd[1]) && CHAT_CMDS[cmd[1]];
    if (c && now > chatCool.cmd) { chatCool.cmd = now + 5; chatCool.auto = now + 8; gesture(c, true); }
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
// Built from each gesture file's "keywords" (and clips.json's): a word
// inside an action she writes (*beckons you closer*) or an emoji anywhere.
// A keyword matches as the start of a word, so "hug" also catches hugs,
// hugging. Built once the gestures and clips have loaded.
let ACTS = [];
function buildActs() {
  const esc = s => s.replace(/[.*+?^${}()|[\]\\]/g, '\\$&').replace(/\s+/g, '\\s+');
  const lists = Object.entries(GESTURE_KEYWORDS).concat((cfg.clips || []).filter(c => c.keywords).map(c => [c.name, c.keywords]));
  ACTS = [];
  for (const [name, kws] of lists) {
    const words = kws.filter(k => /\w/.test(k)), marks = kws.filter(k => !/\w/.test(k));
    const parts = [];
    if (words.length) parts.push(`\\*[^*\\n]{0,60}\\b(?:${words.map(esc).join('|')})\\w*[^*\\n]{0,60}\\*`);
    if (marks.length) parts.push(marks.map(esc).join('|'));
    if (parts.length) ACTS.push([name, new RegExp(parts.join('|'), 'iu')]);
  }
}
function actOut(text) {
  if (said.tagged) return;          // she picked one herself: that wins
  // the earliest match in what she's written so far
  let best = null;
  for (const [name, re] of ACTS) {
    if (said.done.has(name)) continue;
    const m = re.exec(text);
    if (m && (!best || m.index < best[1])) best = [name, m.index];
  }
  if (best) {
    said.done.add(best[0]);
    gesture(best[0]);
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
  // Holding a pose: nothing else on her own, and back into it as soon as
  // anything that interrupted it has finished.
  if (moves && mind.hold && (moves.names.includes(mind.hold) || moves.hasClip(mind.hold))) {
    if (!moves.busy()) moves.play(mind.hold);
    return;
  }
  if (!moves || moves.busy()) return;
  if (mind.stage === 'idle' && now > idle.next) {
    let pick;
    // half the time, something that suits her mood (agent/moods.json "idle")
    const fits = mind.idle.filter(n => moves.names.includes(n) || moves.hasClip(n));
    const seen = n => !(GESTURES[n]?.full && framing !== 'full' && !fan?.status().connected);   // legs-only moves wait for full body (or a fan)
    const pool = (fits.length && Math.random() < 0.5 ? fits : IDLE.concat(moves.clipsWhere('idle'))).filter(seen);   // clips marked "idle" join in
    if (pool.length) {
      do { pick = pool[Math.floor(Math.random() * pool.length)]; } while (pick === idle.last && pool.length > 1);
      idle.last = pick;
      moves.play(pick);
    }
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
  const len = 0.16 * (1 + moodNow.sad * 0.8);   // heavier lids when she's low
  const k = blink.t / len;
  let v = k < 0.45 ? k / 0.45 : Math.max(0, 1 - (k - 0.45) / 0.55);
  if (blink.t >= len) {
    blink.t = -1;
    blink.next = now + (blink.double ? 0.09 : rand(2.2, 6.5) * (1 + moodNow.sad * 0.6));
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
// How far the ears may move. VRoid's cat ears are separate pieces that float
// off the head if they turn far, so they get a small range; "vrm":
// {"ear_range": 0..1} in the model's luna.json sets it (1 = full).
let earRange = 1;
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
    eul.set(e.x * earRange, 0, e.z * e.side * earRange);
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

// set by the portrait every frame; a gesture can only add to these
const PORTRAIT_SETS = new Set(['blink', 'happy', 'sad', 'angry', 'relaxed', 'surprised', 'aa', 'ih', 'ou', 'ee', 'oh']);
const gestureOwned = new Set();

// Moods: gentle, never a full grin from the dials alone.
const moodNow = { happy: 0, sad: 0, angry: 0, relaxed: 0, surprised: 0 };
// Heavy lids. A feeling's lids (playful) hold for its few seconds. A
// mood's (flirty) come as moments - held all the time they read as sleepy,
// not sultry - so her eyes stay mostly open and every so often she gives
// a half-lidded glance for a few seconds. Blinks go from wherever they are.
const lids = { now: 0, mood: 0, feel: 0, glance: 0, next: 0 };
const LIDS_AT_REST = 0.25;      // of the mood's lids, between glances
function lidsTarget(now) {
  if (!lids.mood) { lids.glance = 0; lids.next = now + rand(3, 8); }
  else if (now >= lids.next) { lids.glance = now; lids.next = now + rand(8, 20); }
  const t = now - lids.glance;                        // a glance: ease in, hold, ease out over ~3 s
  const g = lids.glance && t < 3.2 ? Math.min(1, t / 0.6, (3.2 - t) / 0.8) : 0;
  return Math.max(lids.feel, lids.mood * (LIDS_AT_REST + (1 - LIDS_AT_REST) * g));
}

// A quick feeling: in fast, held, out over the last second and a half.
const feel = { face: {}, start: -99, seconds: 6 };
function feelWeight(now) {
  const t = now - feel.start;
  if (t < 0 || t > feel.seconds) return 0;
  return Math.min(1, t / 0.4, (feel.seconds - t) / 1.5);
}

function updateMood(dt, talking) {
  const w = mind.warmth, e = mind.energy;
  const fw = feelWeight(clock.elapsedTime);
  // A quick feeling, or a gesture's sad/cross face (a sulk): on a model
  // with separate brow/eye/mouth shapes those two only show through here,
  // since the whole-face presets are kept at 0 for them.
  const gx = moves?.expr() || {};
  const fromGesture = k => (k === 'sad' || k === 'angry') && moodParts() ? (gx[k] || 0) : 0;
  const over = k => Math.min(1, Math.max((feel.face[k] || 0) * fw, fromGesture(k)));
  if (mind.face) {
    // the mood's own face, from agent/moods.json; a model without separate
    // brow/eye/mouth shapes shows sad and cross at half, or the presets take over
    const f = mind.face, half = moodParts() ? 1 : 0.5;
    const target = {
      happy: Math.max(f.happy || 0, over('happy')) + (talking ? 0.08 : 0),
      relaxed: Math.max(f.relaxed || 0, over('relaxed')),
      sad: Math.max(f.sad || 0, over('sad')) * half,
      angry: Math.max(f.angry || 0, over('angry')) * half,
      surprised: Math.max(mind.stage === 'waking' ? 0.35 : 0, f.surprised || 0, over('surprised')),
    };
    blush.mood = Math.max(f.blush || 0, over('blush'));
    lids.mood = f.lids || 0;
    lids.feel = over('lids');
    return applyMood(target, dt);
  }
  blush.mood = over('blush');
  lids.mood = 0;
  lids.feel = over('lids');
  const target = {
    happy: Math.max(0, Math.min(0.55, w * 0.45 + e * 0.15 + (talking ? 0.08 : 0))),
    relaxed: Math.max(0, Math.min(0.4, w * 0.3 - e * 0.2)),
    // with separate brow/eye/mouth shapes she can show more without the
    // whole-face presets taking over
    sad: moodParts() ? Math.max(0, Math.min(0.9, -e * 0.7 - w * 0.15)) : Math.max(0, Math.min(0.45, -e * 0.35 - w * 0.1)),
    angry: moodParts() ? Math.max(0, Math.min(0.85, -w * 0.8 - 0.1)) : Math.max(0, Math.min(0.4, -w * 0.4 - 0.1)),
    surprised: mind.stage === 'waking' ? 0.35 : 0,
  };
  for (const k in target) target[k] = Math.max(target[k], over(k));
  applyMood(target, dt);
}
function applyMood(target, dt) {
  for (const k in target) {
    moodNow[k] = damp(moodNow[k], target[k], 2.5, dt);
    // a quiet smile while she isn't talking: VRoid's "happy" opens the mouth
    setExpr(k, k === 'happy' && quietSmile() ? moodNow[k] * mouthShut.talk
               : (k === 'sad' || k === 'angry') && moodParts() ? 0 : moodNow[k]);
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
    lids.now = damp(lids.now, mind.stage === 'waking' ? 0 : Math.min(0.7, lidsTarget(now)), 2.5, dt);
    setExpr('blink', mind.stage === 'waking' ? 0 : Math.max(lids.now, blinkValue(now, dt)));

    // Head: follows the gaze part of the way, breathes, nods with her voice.
    tilt.v = damp(tilt.v, tilt.target + L.tilt * LOOK_TILT, 3, dt);
    const sway = Math.sin(now * 0.7) * 0.025 + Math.sin(now * 0.31 + 1) * 0.02;
    const rate = L.thinking ? 2.5 : 3.5;
    headRot.y = damp(headRot.y, (gaze.x * L.headGain + L.wander.x * LOOK_X) * 0.9 + sway, rate, dt);
    headRot.x = damp(headRot.x, -(gaze.y * L.headGain + L.wander.y * LOOK_Y) * 0.7
                     + (mind.stage === 'listening' ? 0.06 : 0)
                     + moodNow.sad * 0.12 + moodNow.angry * 0.05
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
    if (view.back && now > view.back) turnTo(0);                       // drift back to the front
    if (view.target != null) {
      orbit.yaw = damp(orbit.yaw, view.target, 3.5, Math.min(raw, 0.2));
      if (Math.abs(orbit.yaw - view.target) < 0.002) { orbit.yaw = view.target; view.target = null; }
    }
    const d = base.dist * orbit.zoom, ty = base.lookY + hy;
    camera.position.set(Math.sin(orbit.yaw) * Math.cos(orbit.pitch) * d, ty + 0.01 + Math.sin(orbit.pitch) * d,
                        base.headZ + Math.cos(orbit.yaw) * Math.cos(orbit.pitch) * d);
    camera.lookAt(0, ty, base.headZ);
    // Expressions the portrait sets itself every frame (blink, moods, mouth)
    // are only ever raised by a gesture. Any other one a gesture touches
    // (a wink's blinkRight) belongs to the gesture alone: set outright, and
    // put back to 0 when the gesture lets go - or the eye stays shut.
    const gx = moves.expr();
    for (const k of gestureOwned) if (!Object.hasOwn(gx, k)) { vrm.expressionManager.setValue(k, 0); gestureOwned.delete(k); }
    for (const [k, v] of Object.entries(gx)) {
      if (k === 'blush') blush.gesture = v;
      else if (k === 'tears') tears.gesture = v;
      else if (k === 'drool') drool.gesture = v;
      else if (!has.has(k)) continue;
      else if ((k === 'sad' || k === 'angry') && moodParts()) continue;   // through updateMood's parts
      else if (PORTRAIT_SETS.has(k)) vrm.expressionManager.setValue(k, Math.max(vrm.expressionManager.getValue(k) || 0, v));
      else { vrm.expressionManager.setValue(k, v); gestureOwned.add(k); }
    }
    if (!Object.hasOwn(moves.expr(), 'blush')) blush.gesture = 0;
    if (!Object.hasOwn(moves.expr(), 'tears')) tears.gesture = 0;
    if (!Object.hasOwn(moves.expr(), 'drool')) drool.gesture = 0;
    updateBlush(dt);
    updateSpank(dt);
    updateBrows();
    updateTears(dt, now);
    moodEmote(now);
    emotes.update(dt, bone('head'), camera);

    vrm.update(dt);
    closeMouth(talking);
    updateEars(now, dt);   // after update: spring bones won't overwrite a twitch
  }

  if (holo && holo.isOn()) holo.render(scene, camera);
  else renderer.render(scene, camera);
  if (fan && vrm) fan.update(performance.now());
}

// ---------------------------------------------------------------------------
// Hologram fan (fan.js, holofan.py): a WiFi fan gets her live, from a camera
// of its own - centred, square, all of her (or bust), turning when she turns.
// ---------------------------------------------------------------------------
function placeFan(cam, how) {
  // framed on her standing height, not where her head is this moment: a bow
  // or a crouch moves her in the circle, the camera stays put (bust follows a jump)
  const headY = base.headY || 1.4, bust = how === 'bust';
  const height = bust ? 0.62 : headY + 0.3;                             // what fits the circle
  const lookY = bust ? headY - 0.12 + moves.hipsY() * 0.7 : (headY + 0.15) / 2;
  const dist = (height / 2) / Math.tan(THREE.MathUtils.degToRad(cam.fov / 2));
  cam.position.set(Math.sin(orbit.yaw) * dist, lookY, base.headZ + Math.cos(orbit.yaw) * dist);
  cam.lookAt(0, lookY, base.headZ);
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
  mouthShut.targets = []; mouthShut.smile = []; mouthShut.parts = [];
  vrm.scene.traverse(o => {
    const d = o.morphTargetDictionary;
    if (!d) return;
    const key = Object.keys(d).find(k => /(^|_)mth_close$|mouth_?close/i.test(k));
    if (key !== undefined) mouthShut.targets.push([o, d[key]]);
    if ('Fcl_EYE_Joy' in d && 'Fcl_MTH_Fun' in d) mouthShut.smile.push([o, d.Fcl_EYE_Joy, d.Fcl_MTH_Fun]);
    const parts = [];
    for (const [mood, list] of Object.entries(MOOD_PARTS))
      for (const [name, wgt, isMouth, onTop] of list) if (name in d) parts.push([mood, d[name], wgt, !!isMouth, !!onTop]);
    if (parts.length) mouthShut.parts.push([o, parts]);
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
  // sad and cross, part by part: brows lead, eyes follow, the mouth eases off
  // while she talks so the words still read
  if (moodParts()) {
    for (const [o, parts] of mouthShut.parts) for (const [mood, idx, wgt, isMouth, onTop] of parts) {
      const val = moodNow[mood] * wgt * (isMouth ? 1 - 0.7 * mouthShut.talk : 1);
      // a shape a VRM expression also drives (the blink): never pull it below that
      o.morphTargetInfluences[idx] = onTop ? Math.max(o.morphTargetInfluences[idx], val) : val;
    }
  }
}

// VRoid faces carry brows, eyes and mouth as separate shapes; sad and cross
// are built from those instead of the whole-face presets.
const MOOD_PARTS = {
  // (brows are often under the bangs, so the eyes and mouth do the work)
  sad: [['Fcl_BRW_Sorrow', 1], ['Fcl_EYE_Sorrow', 1.1], ['Fcl_MTH_Sorrow', 1.2, true]],
  angry: [['Fcl_BRW_Angry', 1.9], ['Fcl_EYE_Angry', 1.8], ['Fcl_MTH_Angry', 1.3, true], ['Fcl_EYE_Close', 0.45, false, true]],
};
function moodParts() {
  if (!mouthShut.smile) findMorphs();
  return mouthShut.parts.length > 0 && cfg.vrm?.mood_parts !== false;
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
const blush = { now: 0, gesture: 0, fluster: 0, mood: 0, layer: null, tried: false, test: null };
function blushLayer() {
  if (blush.tried) return blush.layer;
  blush.tried = true;
  const o = cfg.vrm?.blush || {};
  let skin = null;
  vrm.scene.traverse(m => {
    if (!skin && m.isSkinnedMesh && !m.userData.overlay && [].concat(m.material).some(x => /face.*skin|skin.*face/i.test(x.name || ''))) skin = m;
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
  layer.userData.overlay = true;
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
  const target = blush.test ?? Math.min(1, Math.max(blush.gesture, blush.fluster, blush.mood, warm));
  blush.now = damp(blush.now, target, target > blush.now ? 2.5 : 0.8, dt);   // rises quicker than it fades
  if (has.has('blush')) { vrm.expressionManager.setValue('blush', blush.now); return; }
  const l = blushLayer();
  if (l) { l.mat.opacity = blush.now * l.strength; l.mesh.visible = blush.now > 0.01; }
}

// Tears. The same trick as the blush: a copy of the face skin that moves
// with every expression, carrying a texture painted in the face's own
// layout - here redrawn as she cries: a wet shine on the lower lids, then
// streaks that grow down her cheeks with drops running along them.
// What brings them: the cry gesture, or staying deeply sad for a while.
// luna.json, "vrm": {"tears": {"left": [u, v], "right": [u, v], "length": 0.3}}
// (where each tear starts, below the eye; the default is VRoid's layout).
// The same layer carries drool: a gesture's "drool" channel (0..1) draws a
// glossy strand from the corner of her mouth, "vrm": {"drool": {"start":
// [u, v], "length": 0.07}} (default: VRoid's left mouth corner).
const tears = { now: 0, gesture: 0, sadFor: 0, layer: null, tried: false, test: null, drops: [] };
const drool = { now: 0, gesture: 0, test: null };
function tearLayer() {
  if (tears.tried) return tears.layer;
  tears.tried = true;
  let skin = null;
  vrm.scene.traverse(m => {
    if (!skin && m.isSkinnedMesh && m.renderOrder !== 1000 && !m.userData.overlay
        && [].concat(m.material).some(x => /face.*skin|skin.*face/i.test(x.name || ''))) skin = m;
  });
  if (!skin) return null;
  const cv = document.createElement('canvas');
  cv.width = cv.height = 512;
  const tex = new THREE.CanvasTexture(cv);
  tex.flipY = false;
  tex.colorSpace = THREE.SRGBColorSpace;
  const mat = new THREE.MeshBasicMaterial({ map: tex, transparent: true, opacity: 1, depthWrite: false,
                                            polygonOffset: true, polygonOffsetFactor: -3, polygonOffsetUnits: -6 });
  const layer = new THREE.SkinnedMesh(skin.geometry, mat);
  layer.userData.overlay = true;
  layer.bind(skin.skeleton, skin.bindMatrix);
  layer.morphTargetInfluences = skin.morphTargetInfluences;
  layer.morphTargetDictionary = skin.morphTargetDictionary;
  layer.frustumCulled = false;
  layer.renderOrder = (skin.renderOrder || 0) + 2;
  skin.parent.add(layer);
  layer.position.copy(skin.position); layer.quaternion.copy(skin.quaternion); layer.scale.copy(skin.scale);
  const o = cfg.vrm?.tears || {};
  tears.layer = { mesh: layer, tex, g: cv.getContext('2d'),
                  starts: [o.left || [0.335, 0.565], o.right || [0.665, 0.565]], length: o.length || 0.3 };
  return tears.layer;
}
function updateTears(dt, now) {
  // deeply sad for ~6 s brings tears on its own
  tears.sadFor = moodNow.sad > 0.55 ? tears.sadFor + dt : Math.max(0, tears.sadFor - dt * 2);
  const target = tears.test ?? Math.min(1, Math.max(tears.gesture, tears.sadFor > 6 ? Math.min(1, (tears.sadFor - 6) / 4) : 0));
  tears.now = damp(tears.now, target, target > tears.now ? 0.9 : 0.35, dt);    // well up slowly, dry slower
  const dTarget = drool.test ?? drool.gesture;
  drool.now = damp(drool.now, dTarget, dTarget > drool.now ? 4 : 1.5, dt);
  const exprTears = has.has('tears');
  if (exprTears) vrm.expressionManager.setValue('tears', tears.now);
  const showTears = !exprTears && cfg.vrm?.tears?.enabled !== false && tears.now > 0.01;
  const showDrool = cfg.vrm?.drool?.enabled !== false && drool.now > 0.01;
  if (!showTears) tears.drops.length = 0;
  const l = showTears || showDrool ? tearLayer() : tears.layer;
  if (!l) return;
  l.mesh.visible = showTears || showDrool;
  if (!l.mesh.visible) return;
  const g = l.g, S = 512, k = tears.now;
  g.clearRect(0, 0, S, S);
  if (showDrool) drawDrool(g, S, drool.now);
  if (!showTears) { l.tex.needsUpdate = true; return; }
  // drops: born at the lid every so often, sliding down and slowing
  if (k > 0.35 && Math.random() < dt * 1.4 * k) {
    const side = Math.random() < 0.5 ? 0 : 1;
    tears.drops.push({ side, y: 0, v: 0.05 + Math.random() * 0.04, wob: Math.random() * 6 });
  }
  for (const [i, [u, v]] of l.starts.entries()) {
    const x = u * S, y0 = v * S, len = l.length * S * Math.min(1, k * 1.3), dir = i === 0 ? 1 : -1;
    // wet lower lid: a soft, bright line
    const lid = g.createRadialGradient(x, y0, 0, x, y0, 30);
    lid.addColorStop(0, `rgba(150,200,255,${0.6 * k})`);
    lid.addColorStop(1, 'rgba(225,240,255,0)');
    g.fillStyle = lid;
    g.beginPath(); g.ellipse(x, y0, 30, 7, 0, 0, Math.PI * 2); g.fill();
    // the streak: thin, glossy, curving slightly outward as it runs down
    if (k > 0.25) {
      const path = t => [x + dir * -Math.sin(t * 1.4) * 6, y0 + t * len];
      const grad = g.createLinearGradient(x, y0, x, y0 + len);
      grad.addColorStop(0, `rgba(120,175,250,${0.85 * k})`);
      grad.addColorStop(0.85, `rgba(120,175,250,${0.6 * k})`);
      grad.addColorStop(1, 'rgba(120,175,250,0)');
      g.strokeStyle = grad; g.lineWidth = 7; g.lineCap = 'round';
      g.beginPath();
      for (let t = 0; t <= 1.001; t += 0.05) { const [px, py] = path(t); t ? g.lineTo(px, py) : g.moveTo(px, py); }
      g.stroke();
      g.strokeStyle = `rgba(255,255,255,${0.6 * k})`; g.lineWidth = 2;    // highlight down its middle
      g.beginPath();
      for (let t = 0; t <= 0.9; t += 0.05) { const [px, py] = path(t); t ? g.lineTo(px - dir, py) : g.moveTo(px - dir, py); }
      g.stroke();
      for (const d of tears.drops) {
        if (d.side !== i) continue;
        const [px, py] = path(Math.min(1.15, d.y));
        g.fillStyle = `rgba(110,170,250,${0.9 * k * Math.max(0, 1 - Math.max(0, d.y - 0.9) * 4)})`;
        g.beginPath(); g.ellipse(px, py, 5.5, 8, 0, 0, Math.PI * 2); g.fill();
        g.fillStyle = `rgba(255,255,255,${0.9 * k})`;
        g.beginPath(); g.arc(px - 1.3, py - 2, 1.4, 0, Math.PI * 2); g.fill();
      }
    }
  }
  for (const d of tears.drops) { d.y += d.v * dt * 6 * (1 - Math.min(0.6, d.y * 0.5)); }
  tears.drops = tears.drops.filter(d => d.y < 1.3);
  l.tex.needsUpdate = true;
}

// A strand from the corner of her mouth: grows down as the channel rises,
// thin and glossy, with a bead gathering at its end.
function drawDrool(g, S, k) {
  const o = cfg.vrm?.drool || {}, [u, v] = o.start || [0.552, 0.762];
  const x = u * S, y0 = v * S, len = (o.length || 0.07) * S * Math.min(1, k * 1.2);
  const path = t => [x + Math.sin(t * 2.2) * 2.5 + t * 3, y0 + t * len];
  const line = (w, style, to = 1.001, dx = 0) => {
    g.strokeStyle = style; g.lineWidth = w; g.lineCap = 'round'; g.beginPath();
    for (let t = 0; t <= to; t += 0.05) { const [px, py] = path(t); t ? g.lineTo(px + dx, py) : g.moveTo(px + dx, py); }
    g.stroke();
  };
  line(6, `rgba(150,165,215,${0.35 * k})`);                               // a faint edge, so it reads on pale skin
  const strand = g.createLinearGradient(x, y0, x, y0 + len);
  strand.addColorStop(0, `rgba(235,242,255,${0.9 * k})`);
  strand.addColorStop(1, `rgba(220,232,255,${0.75 * k})`);
  line(4, strand);
  line(1.4, `rgba(255,255,255,${0.95 * k})`, 0.85, -0.9);                  // the shine down it
  const [bx, by] = path(1), r = 3 + 3 * k;                                 // the bead
  g.fillStyle = `rgba(150,165,215,${0.35 * k})`;
  g.beginPath(); g.ellipse(bx, by + r * 0.4, r * 0.85 + 1.2, r + 1.2, 0, 0, Math.PI * 2); g.fill();
  g.fillStyle = `rgba(225,236,255,${0.9 * k})`;
  g.beginPath(); g.ellipse(bx, by + r * 0.4, r * 0.85, r, 0, 0, Math.PI * 2); g.fill();
  g.fillStyle = `rgba(255,255,255,${0.95 * k})`;
  g.beginPath(); g.arc(bx - r * 0.3, by, r * 0.3, 0, Math.PI * 2); g.fill();
}

// Brows through the bangs, the anime way: a copy of the brows drawn over
// the hair, sharing the face's skeleton and shape keys. Faint normally,
// stronger when she's cross or sad, so her brows can actually say it.
// "vrm": {"brows_over_hair": 0..1} in luna.json sets the resting strength (0 = off).
const brows = { layer: null, tried: false };
function browLayer() {
  if (brows.tried) return brows.layer;
  brows.tried = true;
  let src = null;
  vrm.scene.traverse(m => { if (!src && m.isSkinnedMesh && /facebrow/i.test([].concat(m.material)[0]?.name || '')) src = m; });
  if (!src || (cfg.vrm?.brows_over_hair ?? 0.35) <= 0 && cfg.vrm?.brows_over_hair !== undefined) return null;
  const from = [].concat(src.material)[0];
  const mat = new THREE.MeshBasicMaterial({ map: from.map, color: 0x6e3550, transparent: true, opacity: 0,
                                            depthTest: false, depthWrite: false, alphaTest: 0.05 });
  const layer = new THREE.SkinnedMesh(src.geometry, mat);
  layer.bind(src.skeleton, src.bindMatrix);
  layer.morphTargetInfluences = src.morphTargetInfluences;
  layer.morphTargetDictionary = src.morphTargetDictionary;
  layer.frustumCulled = false;
  layer.renderOrder = 1000;          // after the hair (VRM sets its own orders in the teens)
  src.parent.add(layer);
  layer.position.copy(src.position); layer.quaternion.copy(src.quaternion); layer.scale.copy(src.scale);
  brows.layer = { mesh: layer, mat };
  return brows.layer;
}
const _hf = new THREE.Vector3(), _hc = new THREE.Vector3(), _hp = new THREE.Vector3();
function updateBrows() {
  const l = browLayer();
  if (!l) return;
  const rest = cfg.vrm?.brows_over_hair ?? 0.35;
  // only from the front: from behind they'd show through her head
  const head = vrm.humanoid.getNormalizedBoneNode('head');
  head.getWorldPosition(_hp);
  _hf.set(0, 0, fx).applyQuaternion(head.getWorldQuaternion(new THREE.Quaternion()));
  _hc.copy(camera.position).sub(_hp).normalize();
  const facing = Math.max(0, Math.min(1, (_hf.dot(_hc) - 0.2) * 2.5));
  l.mat.opacity = Math.min(1, rest + moodNow.angry * 0.9 + moodNow.sad * 0.6) * facing;
  l.mesh.visible = l.mat.opacity > 0.01;
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
    // as agent/moods.json has them: the flirty mood, and the playful feeling
    flirty: () => { handle({ t: 'mood', energy: 0.5, warmth: 1, face: { happy: 0.3, blush: 0.4, lids: 0.45 }, emote: 'hearts' });
                    emoteLast = -99; emote('hearts'); },
    playful: () => handle({ t: 'feeling', face: { happy: 0.4, blush: 0.4, lids: 0.5 }, gesture: 'wink', seconds: 6 }),
    // the two rows past the grid, so touches answer from their lewd / grudge entries
    lewd: () => { handle({ t: 'mood', energy: 0.3, warmth: 0.9, label: 'frisky', row: 'lewd',
                           face: { happy: 0.4, blush: 0.55, lids: 0.5 }, emote: 'hearts' });
                  emoteLast = -99; emote('hearts'); },
    grudge: () => handle({ t: 'mood', energy: 0.8, warmth: -0.5, label: 'furious', row: 'grudge',
                           face: { angry: 0.9 }, emote: 'anger' }),
    'you: left': () => handle({ t: 'gaze', x: -0.8, y: -0.1 }),
    'you: right': () => handle({ t: 'gaze', x: 0.8, y: -0.1 }),
    'you: ahead': () => handle({ t: 'gaze', none: true }),
    glitch: () => holo?.glitch(1),
    fluster: () => { blush.fluster = 1; },
    'tears on/off': () => { tears.test = tears.test ? null : 1; },
    'wag tail': () => { moves.wag(1); setTimeout(() => moves.wag(0), 3000); },
    'holo on/off': () => setHolo(!(holo && holo.isOn())),
    hearts: () => { emoteLast = -99; emote('hearts'); },
    'sweat drop': () => { emoteLast = -99; emote('sweat'); },
    anger: () => { emoteLast = -99; emote('anger'); },
    question: () => { emoteLast = -99; emote('question'); },
  };
  const tune = document.getElementById('dtune');
  if (tune) {
    const row = document.createElement('label');
    row.style.display = 'block';
    row.textContent = 'mouth closed ';
    const r = document.createElement('input');
    Object.assign(r, { type: 'range', min: 0, max: 1, step: 0.05, value: mouthShut.amount });
    const out = document.createElement('span');
    out.textContent = ` ${mouthShut.amount}`;
    r.oninput = () => { mouthShut.amount = +r.value; out.textContent = ` ${r.value}  ("vrm": {"mouth_close": ${r.value}} in luna.json)`; };
    row.append(r, out);
    tune.appendChild(row);
    const row2 = document.createElement('label');
    row2.style.display = 'block';
    row2.textContent = 'blush ';
    const r2 = document.createElement('input');
    Object.assign(r2, { type: 'range', min: -0.05, max: 1, step: 0.05, value: -0.05, title: 'left end: automatic' });
    const out2 = document.createElement('span');
    out2.textContent = ' auto';
    r2.oninput = () => { blush.test = +r2.value < 0 ? null : +r2.value; out2.textContent = blush.test == null ? ' auto' : ` ${r2.value}`; };
    row2.append(r2, out2);
    row.after(row2);
  }
  // a button for every gesture file, labelled by its file name (blow_kiss.js -> "blow kiss"),
  // with a hover line saying what it is: about, touch zones, moods, and
  // 🔥 lewd, 🔒 private (never from stream chat), 🧍 full body only, ⛓ a chain of others
  const tips = {};
  for (const n of GESTURE_NAMES) {
    if (n.endsWith('_left')) continue;
    const label = n.replace(/_/g, ' '), g = GESTURES[n] || {};
    buttons[label] = () => gesture(n);
    tips[label] = [`${n}.js` + (g.lewd ? ' 🔥' : '') + (g.private ? ' 🔒' : '') + (g.full ? ' 🧍' : '') + (g.chain ? ` ⛓ ${g.chain.join(' → ')}` : ''),
                   g.about, g.touch && `touch: ${g.touch.join(', ')}`, g.moods && `moods: ${g.moods.join(', ')}`].filter(Boolean).join('\n');
  }
  // grouped, each group alphabetical; anything not listed is a gesture
  const GROUPS = [
    ['her state', ['idle', 'listen', 'talk', 'think']],
    ['face and mood', ['blink', 'cross', 'flirty', 'fluster', 'grudge', 'happy', 'lewd', 'neutral', 'playful', 'sad', 'tears on/off']],
    ['looking', ['you: ahead', 'you: left', 'you: right']],
    ['body', ['left ear', 'twitch', 'wag tail']],
    ['effects', ['glitch', 'holo on/off']],
    ['emotes', ['anger', 'hearts', 'question', 'sweat drop']],
  ];
  const grouped = new Set(GROUPS.flatMap(([, l]) => l));
  GROUPS.splice(1, 0, ['gestures', Object.keys(buttons).filter(l => !grouped.has(l))]);
  const box = document.getElementById('dbuttons');
  for (const [title, labels] of GROUPS) {
    const list = labels.filter(l => buttons[l]).sort((a, b) => a.localeCompare(b));
    if (!list.length) continue;
    const h = document.createElement('div');
    h.className = 'dim';
    h.style.margin = '6px 0 1px';
    h.textContent = title;
    box.appendChild(h);
    if (title === 'gestures') {
      // one menu, by file name: pick to play, ▶ to play it again
      const sel = document.createElement('select'), again = document.createElement('button');
      sel.style.maxWidth = '100%';
      sel.add(new Option(`pick a gesture (${list.length})`, ''));
      for (const label of list) {
        const n = label.replace(/ /g, '_'), g = GESTURES[n] || {};
        const o = new Option(n + (g.lewd ? ' 🔥' : '') + (g.private ? ' 🔒' : '') + (g.full ? ' 🧍' : '') + (g.chain ? ' ⛓' : ''), label);
        o.title = tips[label] || '';
        sel.add(o);
      }
      const play = () => { if (sel.value) buttons[sel.value](); sel.title = tips[sel.value] || ''; };
      sel.onchange = play;
      again.textContent = '▶'; again.title = 'play it again'; again.onclick = play;
      const key = document.createElement('div');
      key.className = 'dim';
      key.textContent = '🔥 lewd · 🔒 never from stream chat · 🧍 full body only · ⛓ a chain';
      box.append(sel, again, key);
      continue;
    }
    for (const label of list) {
      const b = document.createElement('button');
      b.textContent = label;
      if (tips[label]) b.title = tips[label];
      b.onclick = buttons[label];
      box.appendChild(b);
    }
    if (title === 'effects') box.appendChild(spankSlider());
  }
  if (fan) {            // the WiFi hologram fan, while casting is on
    const h = Object.assign(document.createElement('div'), { className: 'dim', textContent: 'hologram fan' });
    const line = Object.assign(document.createElement('div'), { className: 'dim' });
    h.style.margin = '6px 0 1px';
    const show = () => {
      const f = fan.status();
      line.textContent = !f.enabled ? 'cast is off (portrait.fan.cast)'
        : !f.connected ? `waiting for a fan (on its WiFi, or your router)${f.error ? ' · ' + f.error : ''}`
        : !f.type ? `a fan at ${f.ip}: asking which model it is...`
        : !f.geometry ? `a fan at ${f.ip} (type ${f.type}): a model we can't draw for`
        : `${f.model} (type ${f.type}) at ${f.ip} · ${f.casting ? `live ${f.fps}/s` : 'idle'} · jpeg q${f.quality}`
          + (f.geometry.support === 'legacy' ? ' · older format: may not show live' : '')
          + (f.error ? ' · ' + f.error : '');
    };
    show(); setInterval(show, 2000);
    box.append(h, line);
  }
  // the pose studio: its own window (studio.js); this button brings it back
  const open = document.createElement('button');
  open.textContent = '🎬 pose studio';
  open.onclick = () => studio?.show();
  box.appendChild(open);
  import('./studio.js').then(m => { studio = m.createStudio({ vrm, moves, GESTURES, gesture, THREE, orbit, camera, canvas: renderer.domElement, fx }); })
    .catch(e => console.warn('pose studio:', e));
  // a gesture file with a mistake in it: say which and why, instead of a missing button
  if (Object.keys(GESTURE_FAILED).length) {
    const p = document.createElement('pre');
    p.style.color = '#ff8aa8';
    p.textContent = Object.entries(GESTURE_FAILED).map(([n, why]) => n.startsWith('(') ? why : `gestures/${n}.js didn't load: ${why}`).join('\n');
    box.appendChild(p);
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
// ---------------------------------------------------------------------------
// Touching her: click a part of her and she reacts (3D models). touch.js
// works out where (a ray from the cursor, the nearest bone); what she does
// is portrait/touch.json, by zone and by how warm her mood is.
// ---------------------------------------------------------------------------
const touchCfg = await fetch('touch.json').then(r => r.ok ? r.json() : {}).catch(() => ({}));
const toucher = createTouch(THREE, camera, renderer.domElement);
const touched = { last: -99, recent: [] };

function warmthBand() {        // the same edges as moods.json's warmth
  const w = mind.warmth;
  return w < -0.2 ? 'cool' : w < 0.35 ? 'neutral' : w < 0.66 ? 'warm' : 'loving';
}
function moodBand() { return mind.row || warmthBand(); }
// What can answer now, most specific first: her mood by name (heated),
// its row (lewd, grudge), then the warmth band - so a table without a
// lewd entry falls back to loving, and without a grudge one to cool.
function moodKeys() { return [mind.label, mind.row, warmthBand()].filter(Boolean); }
function reactionKey(table) {
  if (!table) return '';
  return moodKeys().find(k => table[k]) || '';
}
function pickReaction(table) {
  const key = reactionKey(table);
  return key ? table[key] : null;
}
// Gesture files can say which touches they answer: touch: ['legs'],
// moods: ['warm', 'loving'], or a row ('lewd', 'grudge') or a mood name
// (no moods: any). Drop one in and it joins.
function taggedFor(zone) {
  const keys = moodKeys();
  return Object.keys(GESTURES).filter(n => {
    const g = GESTURES[n];
    if (n.endsWith('_left') || n.startsWith('__') || !Array.isArray(g.touch) || !g.touch.includes(zone)) return false;
    return !Array.isArray(g.moods) || keys.some(k => g.moods.includes(k));
  });
}
function react(r, zone, side) {
  const gs = [...new Set([...(Array.isArray(r.gestures) ? r.gestures : []), ...taggedFor(zone)])];
  if (gs.length) {
    let g = gs[Math.floor(Math.random() * gs.length)];
    if (side === 'left' && GESTURES[g + '_left']) g += '_left';   // a one-sided gesture: the side you touched
    gesture(g);
  }
  if (r.face && typeof r.face === 'object') {
    feel.face = r.face; feel.start = clock.elapsedTime; feel.seconds = +r.seconds || 3.5;
  }
  if (r.emote) emote(r.emote);
  if (r.ears) twitch(0, 1);
}
// Spanks. In her top two rows (very warm, lewd) a click on her bum is a
// spank: she flinches (spank_flinch), and her bum reddens - a glow painted
// over her cheeks that steps up every SPANK_STEP spanks and fades as they're
// forgotten (one every SPANK_FORGET seconds). Not while a tame stream is live.
// Each one also goes to Luna as 'spank' (touches.py -> mood.note_spank): every
// 60 knocks her mood down a notch.
const SPANK_STEP = 10, SPANK_FORGET = 10;
const spank = { n: 0, flash: 0, layers: [], built: false };
function spankMode() { return !mind.tame && (mind.row === 'lewd' || warmthBand() === 'loving'); }
function buildBumBlush() {
  spank.built = true;
  // which vertices are her cheeks: in the hips bone's own frame at rest (from
  // the skin's bind matrices, so it doesn't matter how she's posed right now),
  // behind her and either side of the middle, fading out toward the edges
  const rawHips = vrm.humanoid.getRawBoneNode('hips');
  const p = new THREE.Vector3(), m = new THREE.Matrix4();
  vrm.scene.traverse(o => {
    if (!o.isSkinnedMesh || !o.skeleton || o.userData.bumBlush) return;
    const bi = o.skeleton.bones.indexOf(rawHips);
    if (bi < 0) return;
    m.multiplyMatrices(o.skeleton.boneInverses[bi], o.bindMatrix);
    const pos = o.geometry.attributes.position, n = pos.count;
    const si = o.geometry.attributes.skinIndex, sw = o.geometry.attributes.skinWeight;
    const tail = new Set(o.skeleton.bones.map((b, k) => (/tail/i.test(b.name) ? k : -1)).filter(k => k >= 0));
    const w = new Float32Array(n);
    let any = 0;
    for (let i = 0; i < n; i++) {
      if (tail.size && si && sw) {                                 // not her tail, however close it sits
        let t = 0;
        for (let c = 0; c < 4; c++) if (tail.has(si.getComponent(i, c))) t += sw.getComponent(i, c);
        if (t > 0.3) continue;
      }
      p.fromBufferAttribute(pos, i).applyMatrix4(m);
      if (fx < 0) { p.x = -p.x; p.z = -p.z; }
      if (p.z > -0.02) continue;                                   // her front half
      const dx = (Math.abs(p.x) - 0.065) / 0.075, dy = (p.y + 0.07) / 0.085;
      const d = Math.sqrt(dx * dx + dy * dy);
      if (d < 1) { w[i] = Math.pow(1 - d, 1.4); any++; }
    }
    if (any < 12) return;
    const src = o.geometry.index ? o.geometry.index.array : [...Array(n).keys()];
    const tri = [];
    for (let i = 0; i < src.length; i += 3)
      if (w[src[i]] > 0 || w[src[i + 1]] > 0 || w[src[i + 2]] > 0) tri.push(src[i], src[i + 1], src[i + 2]);
    const g = new THREE.BufferGeometry();
    for (const k of ['position', 'normal', 'skinIndex', 'skinWeight']) if (o.geometry.attributes[k]) g.setAttribute(k, o.geometry.attributes[k]);
    const col = new Float32Array(n * 4);
    for (let i = 0; i < n; i++) col.set([1, 0.16, 0.26, w[i]], i * 4);
    g.setAttribute('color', new THREE.BufferAttribute(col, 4));
    g.setIndex(tri);
    const mat = new THREE.MeshBasicMaterial({ vertexColors: true, transparent: true, opacity: 0, depthWrite: false,
                                              polygonOffset: true, polygonOffsetFactor: -2, polygonOffsetUnits: -2 });
    const layer = new THREE.SkinnedMesh(g, mat);
    layer.userData.bumBlush = true;
    layer.frustumCulled = false;
    layer.renderOrder = 5;
    layer.position.copy(o.position); layer.quaternion.copy(o.quaternion); layer.scale.copy(o.scale);
    o.parent.add(layer);
    layer.bind(o.skeleton, o.bindMatrix);
    spank.layers.push(mat);
  });
}
function spankHit() {
  if (!spank.built) { try { buildBumBlush(); } catch (e) { console.warn('bum blush:', e); } }
  const before = Math.floor(spank.n / SPANK_STEP);
  spank.n += 1;
  spank.flash = 1;
  if (moves.playing().includes('spank_flinch')) moves.stop();
  gesture('spank_flinch');
  twitch(0, 1);
  if (Math.floor(spank.n / SPANK_STEP) > before) { emoteLast = -99; emote(mind.row === 'lewd' ? 'hearts' : 'sweat'); }
}
// The debug panel's preview: drag to any number of spanks and the glow holds
// there (no fading) until you let go of it with 'fade'. Any mood, no flinch.
function spankSlider() {
  const row = document.createElement('div'), r = document.createElement('input'), out = document.createElement('span');
  const hit = document.createElement('button'), fade = document.createElement('button');
  row.className = 'row';
  Object.assign(r, { type: 'range', min: 0, max: 80, step: 1, value: 0, title: 'bum redness: how many spanks' });
  r.style.width = '120px';
  hit.textContent = 'spank'; hit.title = 'one spank, flinch and all (any mood)';
  fade.textContent = 'fade'; fade.title = 'let it fade like it does live';
  const show = () => { out.textContent = `${Math.round(spank.n)} · ${Math.round(spankLevel() * 100)}%`; r.value = Math.round(spank.n); };
  r.oninput = () => {
    if (!spank.built) { try { buildBumBlush(); } catch (e) { console.warn('bum blush:', e); } }
    spank.n = +r.value; spank.hold = true; fade.style.borderColor = 'var(--accent)'; show();
  };
  hit.onclick = () => { spankHit(); show(); };
  fade.onclick = () => { spank.hold = false; fade.style.borderColor = ''; };
  setInterval(show, 500);
  const label = document.createElement('span');
  label.className = 'dim'; label.textContent = 'red bum ';
  row.append(label, r, out, hit, fade);
  return row;
}
function spankLevel() { return Math.min(0.75, Math.floor(spank.n / SPANK_STEP) * 0.13 + Math.min(1, spank.n / SPANK_STEP) * 0.06); }
function updateSpank(dt) {
  if (!spank.layers.length) return;
  if (!spank.hold) spank.n = Math.max(0, spank.n - dt / SPANK_FORGET);
  spank.flash = Math.max(0, spank.flash - dt * 2.5);
  const a = mind.tame ? 0 : Math.min(0.85, spankLevel() + spank.flash * 0.18);
  for (const m of spank.layers) { m.opacity = a; m.visible = a > 0.003; }
}

function touch(zone, side) {
  if (zone === 'butt' && moves && spankMode()) { spankHit(); return 'spank'; }   // every click, no cooldown
  const now = clock.elapsedTime;
  // every click counts toward "too much", even ones too quick to answer
  const lim = touchCfg.too_much || {};
  touched.recent = touched.recent.filter(t => now - t < (+lim.seconds || 8)).concat(now);
  if (now - touched.last < (+touchCfg.cooldown || 1.5)) return;
  touched.last = now;
  const tooMuch = touched.recent.length >= (+lim.touches || 5);
  const r = pickReaction(tooMuch ? touchCfg.too_much_reaction : touchCfg.zones?.[zone])
            || (!tooMuch && taggedFor(zone).length ? {} : null);
  if (tooMuch) touched.recent = [];
  if (r) react(r, tooMuch ? '' : zone, side);
}

// ...and Luna hears about it (livefeed -> touches.py): with touch talk on
// she answers out loud, a moment later, in one short line. Every click
// goes, so "on the head, 3 times" is right; the cooldown is hers.
let studio = null;      // the pose studio (studio.js), debug viewer only

function tell(zone) {
  if (params.get('demo')) return;
  fetch('touch', { method: 'POST', headers: { 'Content-Type': 'application/json' },
                   body: JSON.stringify({ zone }) }).catch(() => {});
}

if (touchCfg.enabled !== false) {
  const el = renderer.domElement;
  const tip = params.get('debug') ? Object.assign(document.body.appendChild(document.createElement('div')), { id: 'touchtip' }) : null;
  let down = null, hoverTimer = 0;
  el.addEventListener('pointerdown', e => { down = e.button === 0 ? { x: e.clientX, y: e.clientY, t: performance.now() } : null; });
  el.addEventListener('pointerup', e => {
    // a click, not the end of a drag (the debug page turns her by dragging)
    if (!down || Math.hypot(e.clientX - down.x, e.clientY - down.y) > 6 || performance.now() - down.t > 600) return;
    down = null;
    const hit = toucher.at(vrm, e.clientX, e.clientY, true);
    if (!hit) return;
    if (studio?.active) { studio.pick(hit.bone); return; }     // posing: a click picks the bone
    tell(touch(hit.zone, hit.side) || hit.zone);
  });
  // over a part of her: a pointing hand, and on the debug page the zone's
  // name. Looked up once the cursor rests (a ray through a skinned model
  // isn't free), not on every move.
  el.addEventListener('pointermove', e => {
    const x = e.clientX, y = e.clientY;
    clearTimeout(hoverTimer);
    hoverTimer = setTimeout(() => {
      const hit = toucher.at(vrm, x, y);
      const table = hit && touchCfg.zones?.[hit.zone];
      const key = reactionKey(table), tagged = hit ? taggedFor(hit.zone).length : 0;
      if (!params.get('debug')) el.style.cursor = key || tagged ? 'pointer' : '';
      if (tip) {
        tip.textContent = !hit ? '' : `${hit.zone} · ${key || (tagged ? `gestures (${moodBand()})` : `nothing set (${mind.label || moodBand()})`)}`;
        tip.style.left = x + 14 + 'px';
        tip.style.top = y + 10 + 'px';
      }
    }, 120);
  });
  el.addEventListener('pointerleave', () => { clearTimeout(hoverTimer); if (tip) tip.textContent = ''; });
}

try {
  vrm = await load(cfg.model);
  moves = createGestures(THREE, vrm);
  earRange = cfg.vrm?.ear_range ?? (ears.some(e => /catear/i.test(e.node.name)) ? 0.3 : 1);
  fx = vrm.meta?.metaVersion === '0' ? -1 : 1;
  frame();
  say('');
  // the debug page's frame picker: bust / face / full without reloading (the studio keeps going)
  const setFrame = f => { if (['bust', 'face', 'full'].includes(f)) { framing = f; frame(); } };
  window.portrait = { setFrame, get fan() { return fan?.status(); }, handle, twitch, fakeVoice, blink, mind, gesture, emote, emotes, mouthShut, blush, tears, drool, orbit, get moves() { return moves; }, get vrm() { return vrm; }, get holo() { return holo; },
                      touchAt: (x, y) => toucher.at(vrm, x, y), touch, spank };
  if (cfg.fan?.cast && !params.has('nocast'))
    fan = createFan({ THREE, renderer, scene, cfg: { ...cfg.fan, ...(params.get('fanframe') ? { framing: params.get('fanframe') } : {}) }, place: placeFan });
  if (params.get('debug')) debugPanel();
  buildActs();
  loadClips().then(buildActs);
  if (params.get('demo')) demo(); else connect();
} catch (e) {
  console.error(e);
  say(`couldn't load the model: ${e.message}`, true);
}
animate();
