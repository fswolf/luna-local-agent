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
//   ?lights=1 / ?lights=0  her light strips on or off (overrides config.json)

import { THREE, GLTFLoader, VRMLoaderPlugin, VRMUtils,
         VRMAnimationLoaderPlugin, createVRMAnimationClip } from './vendor/luna-three.js';
import { createLook } from './look.js';
import { createHologram3D } from './hologram3d.js';
import { createEmotes } from './emotes.js';
import { createTouch } from './touch.js';
import { createFan } from './fan.js';
import { createProps } from './props.js';
import { createOutfits } from './outfits.js';
import { createLights } from './lights.js';
import { turnAsked } from './turns.js';
import { clothesAsked, clothesActed } from './clothes_talk.js';
import { createGestures, GESTURES, IDLE, NAMES as GESTURE_NAMES, FAILED as GESTURE_FAILED, KEYWORDS as GESTURE_KEYWORDS } from './gestures.js';
import { bindFaceLayers, blush, drool, tears, updateBlush, updateBrows, updateTears } from './face_layers.js';
import { bindDebugPanel, debugPanel } from './debug_panel.js';

bindDebugPanel({
  get blink() { return blink; },
  get camera() { return camera; },
  get cfg() { return cfg; },
  get clock() { return clock; },
  get ears() { return ears; },
  get emote() { return emote; },
  get emoteLast() { return emoteLast; }, set emoteLast(v) { emoteLast = v; },
  get fakeVoice() { return fakeVoice; },
  get fan() { return fan; },
  get fx() { return fx; },
  get gesture() { return gesture; },
  get handle() { return handle; },
  get has() { return has; },
  get holo() { return holo; },
  get idlePool() { return idlePool; },
  get lights() { return lights; },
  get lightsCfg() { return lightsCfg; },
  get mind() { return mind; },
  get moodBand() { return moodBand; },
  get mouthShut() { return mouthShut; },
  get moves() { return moves; },
  get orbit() { return orbit; },
  get params() { return params; },
  get props() { return props; },
  get outfits() { return outfits; },
  get renderer() { return renderer; },
  get setHolo() { return setHolo; },
  get setLights() { return setLights; },
  get spankSlider() { return spankSlider; },
  get studio() { return studio; }, set studio(v) { studio = v; },
  get throbAt() { return throbAt; }, set throbAt(v) { throbAt = v; },
  get twitch() { return twitch; },
  get vrm() { return vrm; },
});


bindFaceLayers({
  get camera() { return camera; },
  get cfg() { return cfg; },
  get damp() { return damp; },
  get fx() { return fx; },
  get has() { return has; },
  get mind() { return mind; },
  get moodNow() { return moodNow; },
  get vrm() { return vrm; },
});


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
// Light strips (lights.js): config.json portrait.lights, switched live by
// /lights, the tools pane and /settings. Built the first time they're on,
// so a model that never uses them pays nothing.
let lights = null, lightsTried = false;
function lightsCfg(s) {
  const out = { ...(s || {}) };
  if (params.has('lights')) out.enabled = params.get('lights') !== '0';
  return out;
}
function setLights(s) {
  cfg.lights = s;
  if (lights) { lights.set(lightsCfg(s)); return; }
  if (!lightsCfg(s).enabled || lightsTried || !vrm) return;
  lightsTried = true;
  createLights(THREE, vrm, cfg.model, lightsCfg(s))
    .then(l => { lights = l; if (!l) console.info('no light strips for this model (portrait/lights.py makes them)'); })
    .catch(e => console.warn('light strips:', e));
}

function setHolo(on) {
  if (on) { if (holo) holo.on(); else { holo = createHologram3D(THREE, renderer, holoCfg); holo.set('rim', base.rim); } }
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
  // the hologram's rim is drawn in pixels: thinner when she's smaller on screen, so full
  // body doesn't swallow her fingers and toes (1 at the bust, softened by the square root)
  const bust = Math.max(0.23 / tan, 0.20 / (tan * camera.aspect));
  base.rim = Math.min(1.3, Math.max(0.4, Math.sqrt(bust / dist)));
  holo?.set('rim', base.rim);
}

const base = { lookY: 1.45, headZ: 0, follow: 0.7, dist: 2, headY: 0, rim: 1 };

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
    case 'background':  // /settings: what's behind her, picked by you
      window.lunaBackground?.(ev.value);
      break;
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
    case 'lights':      // /lights, the tools pane, /settings
      setLights(ev.lights || {});
      break;
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
      said.text = ''; said.done.clear(); said.tagged = false; said.turned = false; waveBack = false;
      said.raw = ''; said.clothes.clear();
      // undressing is for you alone: not stream chat, not a guest at the keyboard
      said.private = /^(voice|typed|discord)?$/.test(ev.source || '') && !ev.guest;
      // only you (voice, typed, Discord): chat has its own rules, and a
      // game's step prompt is full of "huge trolls" and "hello sailor".
      // Not the last turn replayed to a page that just opened (or reloaded):
      // "take off your top" from ten minutes ago isn't a request now.
      if (/^(voice|typed|discord)?$/.test(ev.source || '') && !(ev.at && ev.at < OPENED - 1)) {
        said.turned = turnFromYou(ev.text || '');      // you asked her to turn: even with gestures off
        if (said.private && gmode.clothes !== 'off') clothes(clothesAsked(ev.text || ''), 'you');
        if (gmode.mode !== 'off') fromYou(ev.text || '');
      }
      break;
    case 'tok':         // her reply as it streams: act out *hugs*, *waves*... (the fallback)
      if (ev.p === 'a' && ev.s) {
        said.raw = (said.raw + ev.s).slice(-600);
        if (gmode.clothes !== 'off') clothesFromHer(said.raw);   // her *slips her top off* (portrait.clothes)
      }
      if (ev.p === 'a' && ev.s && gmode.mode !== 'off') { said.text = (said.text + ev.s).slice(-400); actOut(said.text); }
      break;
    case 'outfit':      // /outfit in her terminal, or a clothes [tag] she wrote (src: tag)
      if (ev.src === 'tag') { if (gmode.clothes !== 'off') clothes(ev, 'her'); }
      else clothes(ev, 'command');
      break;
    case 'gesture':     // a [tag] she wrote, a move she described, the meaning check, or /portrait wave
      if (ev.src === 'tag' || ev.src === 'meaning' || ev.src === 'aside') {
        if (gmode.mode === 'off') break;
        if (ev.src === 'meaning' && said.done.size) break;   // keywords already caught it
        if (ev.src === 'aside' && said.done.has(ev.name)) break;   // *waves*: the keyword fallback got there first
        if (said.turned && GESTURES[ev.name]?.view != null) break;   // you turned her already: "*turns around*" in her reply mustn't turn her back
        said.done.add(ev.name);
        if (ev.src === 'tag') said.tagged = true;
      }
      gesture(ev.name);
      break;
    case 'gesture_mode':   // switched in the settings pane or /portrait gestures
      gmode.mode = ev.mode; gmode.chat = ev.chat !== false;
      if (ev.clothes) gmode.clothes = ev.clothes;
      break;
    case 'chat':        // stream chat and Discord: !hug, hi, lol...
      if (gmode.chat) fromChat(ev);
      break;
    case 'mood': {
      const w = +ev.warmth || 0;
      if (w > 0.85 && mind.warmth <= 0.85 || w - mind.warmth > 0.3) blush.fluster = 1;   // that landed
      mind.energy = +ev.energy || 0;
      mind.energyStep = Number.isInteger(ev.energy_step) ? ev.energy_step : null;   // 0 tired .. 2 wired (mood/show.py)
      mind.warmth = w;
      mind.label = typeof ev.label === 'string' ? ev.label : '';
      mind.row = typeof ev.row === 'string' ? ev.row : '';
      mind.tame = !!ev.tame;      // live on a stream with lewd off: no lewd moves
      if (mind.tame) outfits?.wear?.('dressed');   // and nothing comes off while it's on
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
    case 'prop':       // her morning coffee (coffee.py): pick the mug up, put it down
      propEvent(ev);
      break;
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
      if (flags.some(f => /^(tool failed|no answer|cut off)/.test(f))) { holo?.glitch(1); lights?.failed(); gesture('shrug'); }
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

// Her hands are full (her mug, her book): only that prop's own moves
// (coffee_*, book_* - named like its pick-up gesture) and gestures that
// leave her arms alone play. A wave or a hug would swing the prop about.
const ARMS = /(UpperArm|LowerArm|Hand|Shoulder|Thumb|Index|Middle|Ring|Little)/;
function movesArms(name, depth = 0) {
  const g = GESTURES[name.replace(/_left$/, '')];
  if (!g) return moves?.hasClip(name) ?? false;            // a .vrma clip: assume it does
  if (Array.isArray(g.chain)) return depth < 4 && g.chain.some(n => movesArms(n, depth + 1));
  return (g.keys || []).some(([, p]) => Object.keys(p).some(k => ARMS.test(k)));
}
function busyHands(name) {
  const held = props?.names().find(n => props.held(n));
  if (!held) return false;
  const own = (props.PROPS[held]?.pickup || held + '_pickup').split('_')[0] + '_';
  return !name.startsWith(own) && movesArms(name);
}

function gesture(name, publicOnly = false) {
  if (!moves) return;
  if (GESTURES[name] && GESTURES[name].view != null) {
    const deg = +GESTURES[name].view || 0;
    turnTo(deg === 180 && facingAway() ? 0 : deg);      // "turn around" while turned round: back to you
    return;
  }
  if (moves.playing().some(n => n.replace('_left', '') === name)) return;   // already doing it
  if (busyHands(name)) return;
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

// What she has on is kept per model in this browser, so a reload doesn't
// dress her again, and told to Luna (life/clothes.py) after every change.
function wireOutfits(o) {
  const key = 'luna.outfit.' + (cfg.model || '');
  const keep = () => {
    try { localStorage.setItem(key, JSON.stringify(o.pieces().filter(p => !p.on).map(p => p.id))); } catch (e) {}
  };
  const tell = () => {
    const off = o.pieces().filter(p => !p.on);
    fetch('outfit', { method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ wearing: o.has ? o.state() : 'none', off: off.map(p => p.label),
                             pieces: o.pieces().map(p => p.label) }) }).catch(() => {});
  };
  if (o.has && !mind.tame) {
    try { for (const id of JSON.parse(localStorage.getItem(key) || '[]')) o.set(id, false); } catch (e) {}
  }
  let timer = 0;
  o.onChange(() => { keep(); clearTimeout(timer); timer = setTimeout(tell, 300); });   // kept at once, told a moment later
  tell();
}

// Her clothes (outfits.js, on a human model whose clothes come off):
//   from /outfit, from you in plain words ("take off your top", clothes_talk.js),
//   from her own *slips her top off*, or a [top_off] tag she wrote (clothes.py);
//   portrait.clothes picks which of the conversation ones count. Putting things on always works;
//   taking them off never in tame mode, never for stream chat or a guest,
//   and not on your word while she's cool with you, holding a grudge or has
//   walked off - then it's up to her (her own action still counts).
function clothes(a, who) {
  if (!a || !outfits?.has) return false;
  const off = a.wear === 'underwear' || (Array.isArray(a.off) && a.off.length);
  if (off) {
    if (mind.tame || (who !== 'command' && !said.private)) return false;
    if (who === 'you' && (mind.row === 'grudge' || warmthBand() === 'cool' || mind.hold)) return false;
  }
  let did = false;
  if (a.wear === 'dressed' || a.wear === 'underwear') did = outfits.wear(a.wear);
  for (const p of [].concat(a.off || [])) did = outfits.set(String(p), false) || did;
  for (const p of [].concat(a.on || [])) did = outfits.set(String(p), true) || did;
  return did;
}
// Each finished action in her reply so far (*...* or (...)), once a turn
function clothesFromHer(text) {
  if (!outfits?.has) return;
  for (const m of text.matchAll(/\*([^*\n]{3,160})\*|\(([^()\n]{3,160})\)/g)) {
    const act = (m[1] || m[2]).trim();
    if (said.clothes.has(act)) continue;
    said.clothes.add(act);
    clothes(clothesActed(act), 'her');
  }
}

// You asked her to turn: "turn around", "show me your ass", "turn left",
// "turn 90", "face me" (turns.js). True if it was a turn.
function turnFromYou(text) {
  const a = turnAsked(text);
  if (!a) return false;
  if (a.around) gesture('turn_around');                // round, or back to you if she's turned
  else if (a.to != null) turnTo(a.to);
  else {
    const now = (view.target ?? orbit.yaw) * 180 / Math.PI;
    let deg = (((now + a.by) % 360) + 540) % 360 - 180; // into -180..180
    if (Math.abs(deg) < 1) deg = 0;                     // all the way round: facing you, no drift timer
    turnTo(deg);
  }
  return true;
}

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
const said = { text: '', done: new Set(), tagged: false, turned: false, raw: '', clothes: new Set(), private: true };
const OPENED = Date.now() / 1000;      // when this page opened: older events are a replay of how things stood
// How her replies set gestures off (gestures.py): tags, meaning, keywords, off;
// and how the conversation changes her clothes (clothes.py): tags, keywords, off.
const gmode = { mode: cfg.gestures || 'keywords', chat: cfg.chat_gestures !== false, clothes: cfg.clothes || 'keywords' };
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
    if (!(said.turned && GESTURES[best[0]]?.view != null)) gesture(best[0]);   // see 'gesture' above
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
// A prop in her hand (props.js): the pick-up gesture plays (its PROPS entry's
// pickup, else <name>_pickup, so a prop placed in the studio needs no code),
// the prop appears
// part way through it (the gesture's prop_at), and the pose she ends in is
// held (its hold) until she puts it down again, so between sips her arm
// stays round the mug.
// hold: true keeps the pose of its last key (the '+' torso bones are left
// to her breathing; '+neck' and '+head' stay, so she keeps looking into her
// book); an object is a pose of its own
function heldPose(g) {
  if (g.hold && typeof g.hold === 'object') return g.hold;
  if (g.hold !== true || !g.keys?.length) return null;
  const last = g.keys[g.keys.length - 1][1];
  return Object.fromEntries(Object.entries(last).filter(([b]) => !b.startsWith('+') || b === '+neck' || b === '+head'));
}
function propEvent(ev) {
  const p = props?.PROPS[ev.name];
  if (!p || !moves) return;
  if (ev.on) {
    if (props.held(ev.name)) return;
    // one thing in her hands at a time: whatever she's holding goes down first
    const other = props.names().find(n => n !== ev.name && props.held(n));
    if (other) {
      const putName = props.PROPS[other].putdown || other + '_putdown', put = GESTURES[putName];
      if (!moves.playing().includes(putName)) propEvent({ name: other, on: false });   // (already going down: just wait)
      setTimeout(() => propEvent(ev), ((put ? lengthOf(put) : 0) + 0.2) * 1000);
      return;
    }
    const g = GESTURES[p.pickup || ev.name + '_pickup'];
    if (!g) { props.show(ev.name); return; }
    gesture(p.pickup || ev.name + '_pickup');
    setTimeout(() => props.show(ev.name), (+g.prop_at || 0) * 1000);
    setTimeout(() => moves.hold(heldPose(g)), Math.max(0, g.dur - (g.fade?.[1] ?? 0.4)) * 1000);
  } else {
    if (!props.held(ev.name)) return;
    const g = GESTURES[p.putdown || ev.name + '_putdown'];
    if (!g) { props.hide(ev.name); moves.hold(null); return; }
    gesture(p.putdown || ev.name + '_putdown');
    setTimeout(() => moves.hold(null), (g.fade?.[0] ?? 0.3) * 1000 + 50);   // once the gesture has her arm
    setTimeout(() => props.hide(ev.name), (+g.prop_at || 0) * 1000);
  }
}

// What she can drift into right now: her mood's own idles, and the everyday
// ones (gestures with idle: true, or idle: ['warm', 'lewd', ...] for only
// those mood bands; clips marked "idle" join in). Legs-only moves wait for
// full body (or a fan).
function idleFits(v) { return v === true || (Array.isArray(v) && v.includes(moodBand())); }
function idlePool() {
  if (!moves) return { mood: [], everyday: [] };
  const seen = n => !(GESTURES[n]?.full && framing !== 'full' && !fan?.status().connected);
  const mood = mind.idle.filter(n => moves.names.includes(n) || moves.hasClip(n)).filter(seen);
  const everyday = IDLE.filter(n => idleFits(GESTURES[n].idle)).concat(moves.clipsWhere('idle')).filter(seen);
  return { mood, everyday };
}

function idleMoves(now, talking) {
  // Holding a pose: nothing else on her own, and back into it as soon as
  // anything that interrupted it has finished.
  if (moves && mind.hold && (moves.names.includes(mind.hold) || moves.hasClip(mind.hold))) {
    if (!moves.busy()) moves.play(mind.hold);
    return;
  }
  if (!moves || moves.busy()) return;
  if (moves.holding()) return;     // her hands are full (the mug): she sips instead
  if (mind.stage === 'idle' && now > idle.next) {
    let pick;
    // half the time, something that suits her mood (agent/moods.json "idle"),
    // else one of the everyday idles that fits her mood band
    const { mood: fits, everyday } = idlePool();
    const pool = fits.length && (Math.random() < 0.5 || !everyday.length) ? fits : everyday;
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
    props.update(Math.min(raw, 0.2));
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
    lights?.update(dt, { stage: mind.stage, energy: mind.energy, warmth: mind.warmth, row: mind.row,
                         tame: mind.tame, talking, glow: Math.max(moves?.glow?.() || 0, throbTest(now)) });
  }

  if (holo && holo.isOn()) {
    holo.set('rim', Math.min(1.3, Math.max(0.4, base.rim / Math.sqrt(orbit.zoom))));   // the viewer's zoom too
    holo.render(scene, camera);
  }
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

// the debug panel's "throb": a 10 s build and release, as a lewd gesture would drive them
let throbAt = -99;
function throbTest(now) {
  const t = now - throbAt;
  return t < 0 || t > 10 ? 0 : t < 7 ? 0.2 + t / 7 * 1.2 : 1.4 * (1 - (t - 7) / 3);
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
const touched = { last: -99, recent: [], build: {} };

// Touches that add up (touch.json "build" and "soft" on a reaction): while
// she's tired it takes a few touches on a part of her before the full
// reaction plays; until then she gets the soft one - its gesture on the first
// touch only, then just the face, so not every touch is a big move. A zone
// she hasn't been touched on for build_seconds starts over, and so does one
// that's just had its full reaction. build and soft can be one value or
// { tired, even, wired } (her energy, the same edges as moods.json).
// her mood's place in its row (teasing / frisky / heated) when the server says,
// else the dial with moods.json's default edges
function energyBand() {
  if (mind.energyStep != null) return ['tired', 'even', 'wired'][Math.max(0, Math.min(2, mind.energyStep))];
  const e = mind.energy; return e < -0.2 ? 'tired' : e < 0.35 ? 'even' : 'wired';
}
function byEnergy(v) {
  return v && typeof v === 'object' && !Array.isArray(v) && ['tired', 'even', 'wired'].some(k => k in v) ? v[energyBand()] : v;
}
function buildNeed(r) { return Math.max(1, Math.round(+byEnergy(r?.build) || 1)); }
function buildOf(zone, now) {
  const b = touched.build[zone];
  return b && now - b.at < (+touchCfg.build_seconds || 15) ? b : { n: 0, at: now };
}

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
function taggedFor(zone, only) {
  const keys = only ? [only] : moodKeys();
  return Object.keys(GESTURES).filter(n => {
    const g = GESTURES[n];
    if (n.endsWith('_left') || n.startsWith('__') || !Array.isArray(g.touch) || !g.touch.includes(zone)) return false;
    return !Array.isArray(g.moods) || keys.some(k => g.moods.includes(k));
  });
}
// The one mood a touch answers from: the table's own (most specific first), else
// the most specific one a tagged gesture has. Tagged gestures only join for that
// mood: heated answers the chest from "lewd", so a gesture tagged "loving" stays
// out, though heated is loving-warm too.
function touchKey(zone) {
  return reactionKey(touchCfg.zones?.[zone]) || moodKeys().find(k => taggedFor(zone, k).length) || '';
}
function react(r, zone, side) {
  const tagged = zone ? taggedFor(zone, touchKey(zone)) : [];
  const gs = [...new Set([...(Array.isArray(r.gestures) ? r.gestures : []), ...tagged])];
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
// Spanks. From warm up (warm, very warm, lewd) a click on her bum is a
// spank: she flinches (spank_flinch), and her bum reddens - a glow painted
// over her cheeks that steps up every SPANK_STEP spanks and fades as they're
// forgotten (one every SPANK_FORGET seconds). Not while a tame stream is live.
// Each one also goes to Luna as 'spank' (touches.py -> mood.note_spank): every
// 60 knocks her mood down a notch.
const SPANK_STEP = 10, SPANK_FORGET = 10;
const spank = { n: 0, flash: 0, layers: [], built: false };
function spankMode() { return !mind.tame && (mind.row === 'lewd' || ['warm', 'loving'].includes(warmthBand())); }
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
      if (d < 1) { w[i] = Math.pow(1 - d, 0.6); any++; }          // full in the middle, soft at the edge
    }
    if (any < 12) return;
    const src = o.geometry.index ? o.geometry.index.array : [...Array(n).keys()];
    const tri = [];
    for (let i = 0; i < src.length; i += 3)
      if (w[src[i]] > 0 || w[src[i + 1]] > 0 || w[src[i + 2]] > 0) tri.push(src[i], src[i + 1], src[i + 2]);
    const g = new THREE.BufferGeometry();
    for (const k of ['position', 'normal', 'skinIndex', 'skinWeight']) if (o.geometry.attributes[k]) g.setAttribute(k, o.geometry.attributes[k]);
    const col = new Float32Array(n * 4);
    for (let i = 0; i < n; i++) col.set([1, 0.02, 0.03, w[i]], i * 4);   // a deep red (linear: three.js lightens it)
    g.setAttribute('color', new THREE.BufferAttribute(col, 4));
    g.setIndex(tri);
    // multiplied into her skin, not painted over it: her own shading and
    // highlights stay, the skin just goes red (white where there's no blush)
    const mat = new THREE.MeshBasicMaterial({ vertexColors: true, transparent: true, opacity: 0, depthWrite: false,
                                              blending: THREE.CustomBlending, blendEquation: THREE.AddEquation,
                                              blendSrc: THREE.ZeroFactor, blendDst: THREE.SrcColorFactor,
                                              polygonOffset: true, polygonOffsetFactor: -2, polygonOffsetUnits: -2 });
    mat.onBeforeCompile = sh => {
      sh.fragmentShader = sh.fragmentShader.replace('#include <dithering_fragment>',
        '#include <dithering_fragment>\n  gl_FragColor = vec4(mix(vec3(1.0), gl_FragColor.rgb, clamp(gl_FragColor.a, 0.0, 1.0)), 1.0);');
    };
    const layer = new THREE.SkinnedMesh(g, mat);
    layer.userData.bumBlush = true;
    layer.frustumCulled = false;
    layer.renderOrder = 5;
    layer.position.copy(o.position); layer.quaternion.copy(o.quaternion); layer.scale.copy(o.scale);
    o.parent.add(layer);
    layer.bind(o.skeleton, o.bindMatrix);
    mat.userData.on = layer; mat.userData.from = o;     // a sibling, not a child: follows the piece it's made from by hand (updateSpank)
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
function spankLevel() { return Math.min(0.92, Math.floor(spank.n / SPANK_STEP) * 0.18 + Math.min(1, spank.n / SPANK_STEP) * 0.14); }
function updateSpank(dt) {
  if (!spank.layers.length) return;
  if (!spank.hold) spank.n = Math.max(0, spank.n - dt / SPANK_FORGET);
  spank.flash = Math.max(0, spank.flash - dt * 2.5);
  const a = mind.tame ? 0 : Math.min(0.97, spankLevel() + spank.flash * 0.25);
  // a layer made from a piece of clothing (her shorts) goes with it: taken off
  // (outfits.js), the glow mustn't float where it was
  for (const m of spank.layers) {
    m.opacity = a;
    m.visible = a > 0.003;
    if (m.userData.on) m.userData.on.visible = m.userData.from ? m.userData.from.visible : true;
  }
}

function touch(zone, side) {
  lights?.touched(zone);
  if (zone === 'butt' && moves && spankMode()) { spankHit(); return 'spank'; }   // every click, no cooldown
  const now = clock.elapsedTime;
  // every click counts toward "too much", even ones too quick to answer
  const lim = touchCfg.too_much || {};
  touched.recent = touched.recent.filter(t => now - t < (+lim.seconds || 8)).concat(now);
  if (now - touched.last < (+touchCfg.cooldown || 1.5)) return;
  touched.last = now;
  const tooMuch = touched.recent.length >= (+lim.touches || 5);
  const r = pickReaction(tooMuch ? touchCfg.too_much_reaction : touchCfg.zones?.[zone])
            || (!tooMuch && taggedFor(zone, touchKey(zone)).length ? {} : null);
  if (tooMuch) touched.recent = [];
  if (!r) return;
  const need = tooMuch ? 1 : buildNeed(r);
  if (need > 1) {
    const b = buildOf(zone, now);
    b.n += 1; b.at = now; touched.build[zone] = b;
    if (b.n < need) {
      const s = byEnergy(r.soft);
      // its gesture on the first touch only, and never over one still playing
      // (the full reaction she's just had): then it's the face alone
      if (s && typeof s === 'object') react({ ...s, gestures: b.n === 1 && !moves?.busy() ? s.gestures : [] }, '', side);
      return;
    }
    delete touched.build[zone];                // the full one: the next touches build up again
  }
  react(r, tooMuch ? '' : zone, side);
}

// ...and Luna hears about it (livefeed -> touches.py): with touch talk on
// she answers out loud, a moment later, in one short line. Every click
// goes, so "on the head, 3 times" is right; the cooldown is hers.
let studio = null;      // the pose studio (studio.js), debug viewer only
let props = null;       // things in her hands (props.js): the morning mug
let outfits = null;     // her clothes, piece by piece (outfits.js); null for a model without separate clothes

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
      const key = reactionKey(table), tagged = hit ? taggedFor(hit.zone, touchKey(hit.zone)).length : 0;
      if (!params.get('debug')) el.style.cursor = key || tagged ? 'pointer' : '';
      if (tip) {
        const need = hit ? buildNeed(pickReaction(touchCfg.zones?.[hit.zone])) : 1;
        const built = need > 1 ? ` · ${buildOf(hit.zone, clock.elapsedTime).n}/${need} (${energyBand()})` : '';
        tip.textContent = !hit ? '' : `${hit.zone} · ${key || (tagged ? `gestures (${moodBand()})` : `nothing set (${mind.label || moodBand()})`)}${built}`;
        tip.style.left = x + 14 + 'px';
        tip.style.top = y + 10 + 'px';
      }
    }, 120);
  });
  el.addEventListener('pointerleave', () => { clearTimeout(hoverTimer); if (tip) tip.textContent = ''; });
}

try {
  vrm = await load(cfg.model);
  moves = createGestures(THREE, vrm, () => view.target ?? orbit.yaw);      // where the camera is, or is heading
  props = createProps({ THREE, GLTFLoader, vrm, fx: vrm.meta?.metaVersion === '0' ? -1 : 1 });
  // not awaited: looking for <model>.outfits.json mustn't hold up her first frame
  createOutfits({ THREE, vrm, url: cfg.model }).then(o => { outfits = o; wireOutfits(o); }).catch(e => { console.error(e); outfits = null; });
  earRange = cfg.vrm?.ear_range ?? (ears.some(e => /catear/i.test(e.node.name)) ? 0.3 : 1);
  fx = vrm.meta?.metaVersion === '0' ? -1 : 1;
  frame();
  say('');
  setLights(cfg.lights);
  // the debug page's frame picker: bust / face / full without reloading (the studio keeps going)
  const setFrame = f => { if (['bust', 'face', 'full'].includes(f)) { framing = f; frame(); } };
  window.portrait = { setFrame, get fan() { return fan?.status(); }, handle, twitch, fakeVoice, blink, mind, gesture, emote, emotes, mouthShut, blush, tears, drool, orbit, get moves() { return moves; }, get vrm() { return vrm; }, get holo() { return holo; },
                      touchAt: (x, y) => toucher.at(vrm, x, y), touch, spank, get props() { return props; }, get outfits() { return outfits; },
                      get lights() { return lights; }, setLights };
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
