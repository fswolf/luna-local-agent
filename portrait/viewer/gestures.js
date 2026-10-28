// Gestures for the 3D (VRM) portrait: the player, and the list of what
// she can do. Each gesture is its own file in portrait/gestures/ (wave.js, hug.js,
// ...); add a file and it's picked up, no list to edit anywhere.
//
// Every VRM has the same humanoid skeleton, so these work on any model.
// A gesture is a few keyframes of bone rotations, eased between, blended
// in and out over whatever the portrait is already doing (breathing,
// looking, talking), so starting or ending one never snaps.
//
// In a gesture file (export default { ... }):
//   dur, fade  seconds; fade = [in, out]
//   keys       [[time, pose], ...]; a pose is { bone: [x, y, z] }, radians,
//              normalized bones; a 4th number twists the bone about its
//              own length first (turning a forearm so the palm faces right)
//   '+bone'    added on top of what the portrait does (head, spine)
//   hips       an offset to the hips position, metres (jumping)
//   expr       expressions while it plays: { happy: 0.8 } or a timeline
//              [[t, v], ...]; also blush and tears
//   osc        a wobble on top: [bone, axis, amplitude, hz]
//   add        poses added on top for the whole gesture
//   sob        shoulders hitch (crying)
//   then       another gesture to flow into as this one ends ('pant')
//   sound      a clip from portrait/sounds/ to play with it: 'name' or { name, from, len }
//   emote      'sweat', { name, at: seconds in }, or a list of them - emotes while it plays
//   wag        0-1: her tail swishes while it plays
//   tail_up    0-1: her tail lifts and holds up, still, while it plays
//   lewd       true: never plays while a stream with lewd off is live
//              (twitch/youtube "lewd": false) - she shows the row below instead
//   face       'away' or 'me': she turns (at the hips) so her back, or her front,
//              is square to the camera, from wherever you're looking. Worked out
//              once as it starts, so you can still walk the camera round her
//              after. Her '+hips' turn in the keys comes on top (0 = square).
//   view       instead of keys: degrees to swing the camera round her (turn_around
//              180, turn_side 90, face_me 0); back to the front after 120 s
//   chain      instead of keys: other gestures to play in turn, each flowing into
//              the next (['sultry_beckon', 'blow_kiss']); its own touch/moods/private/full
//              apply, the steps' own don't
//   about      when to use it: offered to her as a [tag] in tags mode, and
//              what the meaning mode compares the conversation with
//   keywords   ["beckon", "come hither", "🤫"]: plays it when she writes one
//              inside an *action*, or the emoji anywhere (keyword fallback)
//   idle       one of the things she does on her own
//   private    never from stream chat; only offered in your own turns
//   left       also make a left-handed copy, <name>_left
//   full       only reads with all of her on screen (her legs): offered to
//              her and played on her own only in full-body framing
//   touch      zones it answers when you click her: ['legs'] (touch.js)
//   moods      ...in these mood bands or moods: ['warm', 'loving']; none: any
//
// Animation clips (.vrma, portrait/animations/) can stand in for any of
// these or add new ones: addClip() below.

import { REST, mirrorGesture } from './gestures/_pose.js';
export { REST };

// The list comes from the server (every gesture/*.js not starting with _);
// without one (a static copy of the page), the built-ins.
const BUILT_IN = ['dance', 'jog', 'pant', 'sultry_beckon', 'wink', 'shh', 'wave', 'hug', 'jump', 'shrug', 'blow_kiss', 'shy', 'cry', 'stretch', 'look_hand',
                  'tuck_hair', 'bounce', 'explain', 'sulk', 'bashful'];
export const FAILED = {};      // name -> why it didn't load (shown on the debug page)
const list = await fetch('gestures/index.json').then(r => r.ok ? r.json() : null).catch(() => null);
if (!list || !list.length) FAILED['(the list)'] = "the server didn't list any gesture files, so only the built-ins loaded - "
  + 'restart Luna or ./viewer.sh (an older copy is still running)';

export const GESTURES = {};
export const ABOUT = {};
export const KEYWORDS = {};    // name -> ["hug", "cuddle", "🤗"]: the keyword fallback
for (const name of (list && list.length ? list : BUILT_IN)) {
  try {
    const g = (await import(`./gestures/${name}.js`)).default;
    GESTURES[name] = g;
    if (g.about) ABOUT[name] = g.about;
    if (Array.isArray(g.keywords) && g.keywords.length) KEYWORDS[name] = g.keywords;
    if (g.left) GESTURES[`${name}_left`] = Object.assign(mirrorGesture(g), { about: undefined, left: false });
  } catch (e) {
    console.warn(`gesture ${name}:`, e);
    FAILED[name] = String(e.message || e);
  }
}

export const IDLE = Object.keys(GESTURES).filter(n => GESTURES[n].idle);
export const PRIVATE = Object.keys(GESTURES).filter(n => GESTURES[n].private);
export const NAMES = Object.keys(GESTURES);

// ---------------------------------------------------------------------------
// Playing them
// ---------------------------------------------------------------------------
const ease = t => t * t * (3 - 2 * t);

// a key's value for one channel at time t (fill forward, fill back)
export function sample(keys, name, t) {
  let prev = null, next = null;
  for (const [kt, p] of keys) {
    if (!(name in p)) continue;
    if (kt <= t) prev = [kt, p[name]];
    else { next = [kt, p[name]]; break; }
  }
  if (!prev) return next ? next[1] : null;
  if (!next) return prev[1];
  const k = ease((t - prev[0]) / (next[0] - prev[0]));
  // a key with a twist (4th number) next to one without: the missing one is 0,
  // never undefined - NaN in a rotation makes the limb vanish
  const n = Math.max(prev[1].length, next[1].length);
  return Array.from({ length: n }, (_, i) => (prev[1][i] ?? 0) + ((next[1][i] ?? 0) - (prev[1][i] ?? 0)) * k);
}
export function sampleScalar(v, t) {
  if (!Array.isArray(v)) return v;
  let prev = v[0], next = null;
  for (const kv of v) { if (kv[0] <= t) prev = kv; else { next = kv; break; } }
  if (!next) return prev[1];
  return prev[1] + (next[1] - prev[1]) * ease((t - prev[0]) / (next[0] - prev[0]));
}

// How far to turn her (radians about her hips) so her back ('away') or front ('me')
// is to a camera at yaw (0 = in front of her). She turns to her right (clockwise
// from above) unless her left is a lot shorter: the turn is kept in -225°..135°,
// so a camera nudged a little off the front doesn't flip a half turn to her left.
export function faceTurn(face, yaw) {
  const tau = Math.PI * 2, low = -1.25 * Math.PI, want = (yaw || 0) + (face === 'away' ? Math.PI : 0);
  return ((want - low) % tau + tau) % tau + low;
}

// view(): the camera's yaw round her now, for gestures with face: (portrait.js orbit)
export function createGestures(THREE, vrm, view = () => 0) {
  const hips = vrm.humanoid.getNormalizedBoneNode('hips');
  const hipsRest = hips ? hips.position.clone() : null;
  const bone = n => vrm.humanoid.getNormalizedBoneNode(n);
  const active = [];
  // bones the portrait sets itself every frame, before the gestures
  const MANAGED = new Set(['head', 'neck', 'spine', 'leftShoulder', 'rightShoulder',
                           bone('upperChest') ? 'upperChest' : 'chest']);
  const turnFor = g => (g && (g.face === 'away' || g.face === 'me') ? faceTurn(g.face, view()) : 0);
  const touched = new Set();      // every bone a gesture has written to
  const touchedObj = new Set();   // ...and every node a .vrma clip has          // {g, name, t, out}
  const qa = new THREE.Quaternion(), e = new THREE.Euler();
  // VRM 0.x faces the other way in its own space: same pose, x and z flipped.
  const fx = vrm.meta?.metaVersion === '0' ? -1 : 1;
  const euler = (x, y, z) => e.set(fx * x, y, fx * z);
  const qt = new THREE.Quaternion(), X = new THREE.Vector3(1, 0, 0);
  let exprNow = {};
  let held = null;      // a pose she keeps between gestures (holding her mug): hold()

  // the tail: spring bones, so it can't be posed; it wags by swinging
  // the gravity its joints feel from side to side
  const tail = [];
  for (const j of vrm.springBoneManager?.joints || []) {
    if (/tail/i.test(j.bone?.name || '')) tail.push({ j, dir: j.settings.gravityDir.clone(), power: j.settings.gravityPower });
  }
  const wag = { amount: 0, target: 0, phase: 0, sweep: 1 };
  const wagUp = new THREE.Vector3();
  // how a wag carries the tail: lift (pull), sweep (side to side), back (behind her)
  const TAIL = { lift: 3.0, sweep: 1.8, back: 0.5 };

  // .vrma clips: name -> [{clip, opts}], several = variants picked at random
  const clips = {};

  // A clip plays on stand-in objects, never on her directly, so it can be
  // blended over her own pose by weight (an AnimationMixer only blends
  // against where a bone was when the clip was bound, not this frame).
  function clipRunner(clip, opts) {
    const root = new THREE.Object3D(), ghosts = {}, binds = [];
    const exprByObj = {};
    for (const x of vrm.expressionManager?.expressions || []) exprByObj[x.name] = x.expressionName;
    const skip = opts.look ? /head|neck|eye/i : null;
    for (const track of clip.tracks) {
      const { nodeName, propertyName } = THREE.PropertyBinding.parseTrackName(track.name);
      if (!ghosts[nodeName]) {
        const g = new THREE.Object3D();
        g.name = nodeName; g.weight = 0;
        root.add(g); ghosts[nodeName] = g;
      }
      if (exprByObj[nodeName]) { binds.push({ kind: 'expr', g: ghosts[nodeName], expr: exprByObj[nodeName] }); continue; }
      // her eyes stay hers: look.js aims them, a clip's look-at track would fight it
      if (/lookat/i.test(nodeName)) continue;
      const target = vrm.scene.getObjectByName(nodeName);
      if (!target || (skip && skip.test(nodeName))) continue;
      binds.push({ kind: propertyName, g: ghosts[nodeName], target });
    }
    const mixer = new THREE.AnimationMixer(root);
    const action = mixer.clipAction(clip);
    action.play();
    return { binds, mixer, action, length: clip.duration };
  }

  function startClip(name, v) {
    const o = v.opts, speed = +o.speed || 1;
    const repeat = o.loop ? Math.max(1, +o.repeat || 3) : 1;
    const run = clipRunner(v.clip, o);
    return { name, t: 0, out: 0, kind: 'clip', run, speed, loop: !!o.loop,
             g: { dur: run.length / speed * repeat, fade: o.fade || [0.45, 0.55], expr: o.expr } };
  }

  function channels(g) {
    const names = new Set();
    for (const [, p] of g.keys) for (const k of Object.keys(p)) if (k !== 'expr') names.add(k);
    return [...names];
  }

  return {
    names: NAMES,
    addClip(name, clip, opts = {}) { (clips[name] = clips[name] || []).push({ clip, opts }); },
    hasClip(name) { return !!clips[name]; },
    clipNames() { return Object.keys(clips); },
    clipsWhere(key) { return Object.keys(clips).filter(n => clips[n].some(v => v.opts[key])); },
    busy() { return active.some(a => !a.out); },
    playing() { return active.filter(a => !a.out).map(a => a.name); },
    state() { return active.map(a => ({ name: a.name, t: +a.t.toFixed(2), out: a.out })); },
    // publicOnly: from chat, so a clip marked private never plays
    play(name, publicOnly = false) {
      if (publicOnly && PRIVATE.includes(name)) return false;
      const vs = (clips[name] || []).filter(v => !publicOnly || !v.opts.private);
      let g = GESTURES[name], next = [];
      // a chain gesture ({ chain: ['sultry_beckon', 'blow_kiss'] }) plays its steps in turn
      if (g && Array.isArray(g.chain)) { next = g.chain.filter(n => GESTURES[n] && !GESTURES[n].chain && GESTURES[n].view == null); g = GESTURES[next.shift()]; }
      if (g && g.view != null) return false;      // a turn: the portrait moves the camera (portrait.js turnTo)
      if (!vs.length && !g) return false;
      for (const a of active) if (!a.out) a.out = a.t;          // let the old one go
      if (vs.length) active.push(startClip(name, vs[Math.floor(Math.random() * vs.length)]));
      else active.push({ g, name, t: 0, ct: 0, out: 0, ch: channels(g), next, turn: turnFor(g) });
      return true;
    },
    stop() { for (const a of active) if (!a.out) a.out = a.t; },
    // How hard her light strips throb for what's playing: a gesture's
    // lights: [[seconds, level], ...] (a chain's over the whole chain), 0 when none.
    glow() {
      let v = 0;
      for (const a of active) {
        const c = GESTURES[a.name]?.lights;
        if (a.gone || !Array.isArray(c) || !c.length) continue;
        const t = (a.ct || 0) + a.t;
        let x = c[c.length - 1][1];
        for (let i = 0; i < c.length; i++) {
          if (t < c[i][0]) { x = i ? c[i - 1][1] + (c[i][1] - c[i - 1][1]) * (t - c[i - 1][0]) / ((c[i][0] - c[i - 1][0]) || 1) : c[0][1]; break; }
        }
        const fo = (a.g.fade || [0.3, 0.4])[1];
        if (a.out) x *= Math.max(0, 1 - (a.t - a.out) / fo);
        v = Math.max(v, x);
      }
      return v;
    },
    // The pose studio (studio.js): a gesture that never ends, edited in place.
    // pose is {bone: [x, y, z, twist?]} like any key; expr {blush: 0.6, ...}.
    studio(pose, expr, face) {
      for (const a of active) if (!a.out) a.out = a.t;
      const g = { dur: 1e9, fade: [0.25, 0.4], keys: [[0, pose]], expr, face };
      const a = { g, name: '(studio)', t: 0, out: 0, ch: channels(g), turn: turnFor(g) };
      active.push(a);
      return { refresh() { a.ch = channels(g); }, stop() { if (!a.out) a.out = a.t; } };
    },
    // A gesture's pose at t seconds: what the studio starts from
    poseAt(name, t) {
      const g = GESTURES[name], out = {};
      if (!g || !Array.isArray(g.keys)) return out;
      for (const n of channels(g)) { const v = sample(g.keys, n, t); if (v) out[n] = v.map(x => +x.toFixed(3)); }
      return out;
    },
    // level 0-1; sweep 0 lifts the tail and holds it up without swishing
    wag(level, sweep = 1) { wag.target = level; wag.sweep = sweep; },
    // A pose that replaces the rest pose for the bones it names, until
    // hold(null): her arm stays round the mug between sips. Gestures still
    // play over it and come back to it.
    hold(pose) { held = pose || null; },
    holding() { return held; },

    // The natural rest pose; called every frame before update(), so a
    // gesture that ends always has somewhere to go back to.
    rest(armsDown) {
      for (const [n, v] of Object.entries(REST)) {
        if (!armsDown && /Arm|Hand/.test(n)) continue;
        const b = bone(n);
        if (b) b.rotation.set(fx * v[0], v[1], fx * v[2]);
      }
      if (hips && hipsRest) hips.position.copy(hipsRest);
      // Any other bone a gesture has moved (chest, hips, toes...) starts each
      // frame from straight again. Without this, '+chest' added a little more
      // every frame and she spun round at the waist.
      for (const n of touched) {
        if (MANAGED.has(n) || n in REST) continue;
        const b = bone(n);
        if (b) b.quaternion.identity();
      }
      for (const o of touchedObj) {
        const n = Object.keys(vrm.humanoid.humanBones).find(k => bone(k) === o);
        if (n && (MANAGED.has(n) || n in REST)) continue;
        o.quaternion.identity();
      }
      // last, so nothing above undoes it
      if (held) {
        for (const [n, v] of Object.entries(held)) {
          const b = n === 'hips' || n.startsWith('+') ? null : bone(n);
          if (!b) continue;
          euler(v[0], v[1], v[2]);
          b.quaternion.setFromEuler(e);
          if (v.length > 3) b.quaternion.multiply(qt.setFromAxisAngle(X, fx * v[3]));
        }
      }
    },

    // After the portrait has set its own pose for the frame.
    update(dt) {
      exprNow = {};
      const over = {};      // how much a playing gesture already drives each '+' bone (the held pose gives way)
      // oldest first, so the newest one lands on top while the old fades
      for (let i = 0; i < active.length; i++) {
        const a = active[i], g = a.g;
        a.t += dt;
        const [fi, fo] = g.fade || [0.3, 0.4];
        const end = a.out ? a.out + fo : g.dur;
        if (a.t >= end) { a.gone = true; continue; }
        // flow into the next one: it fades in while this one fades out
        // (a chain's next step, else the gesture's own then:)
        const nx = a.next?.length ? a.next[0] : g.then;
        if (nx && !a.out && !a.chained && a.t >= g.dur - fo && GESTURES[nx]) {
          a.chained = true;
          const n = GESTURES[nx], inChain = !!a.next?.length;
          active.push({ g: n, name: inChain ? a.name : nx, t: 0, ct: inChain ? (a.ct || 0) + a.t : 0, out: 0, ch: channels(n), next: inChain ? a.next.slice(1) : [],
                        turn: n.face === a.g.face ? a.turn : turnFor(n) });     // the same way: keep the turn it had
        }
        const wIn = Math.min(1, a.t / fi);
        const wOut = a.out ? 1 - (a.t - a.out) / fo : Math.min(1, (g.dur - a.t) / fo);
        const w = ease(Math.max(0, Math.min(wIn, wOut)));
        const t = Math.min(a.t, g.dur);

        if (a.kind === 'clip') {
          const r = a.run, ct = t * a.speed;
          r.action.time = a.loop ? ct % r.length : Math.min(ct, r.length);
          r.mixer.update(0);
          for (const b of r.binds) {
            if (b.kind === 'quaternion') { b.target.quaternion.slerp(b.g.quaternion, w); touchedObj.add(b.target); }
            else if (b.kind === 'position') b.target.position.lerp(b.g.position, w);
            else if (b.kind === 'expr') exprNow[b.expr] = Math.max(exprNow[b.expr] || 0, b.g.weight * w);
          }
          for (const [k, v] of Object.entries(g.expr || {})) exprNow[k] = Math.max(exprNow[k] || 0, sampleScalar(v, t) * w);
          continue;
        }

        // face: turned square to (or away from) the camera first, so her pose is from there
        if (a.turn && hips) { euler(0, a.turn * w, 0); hips.quaternion.multiply(qa.setFromEuler(e)); touched.add('hips'); }
        for (const name of a.ch) {
          const v = sample(g.keys, name, t);
          if (!v) continue;
          if (name === 'hips') {
            if (hips && hipsRest) hips.position.set(hipsRest.x + fx * v[0] * w, hipsRest.y + v[1] * w, hipsRest.z + fx * v[2] * w);
            continue;
          }
          const additive = name.startsWith('+');
          const b = bone(additive ? name.slice(1) : name);
          if (!b) continue;
          touched.add(additive ? name.slice(1) : name);
          if (additive) over[name] = Math.max(over[name] || 0, w);
          if (additive) {
            euler(v[0] * w, v[1] * w, v[2] * w);
            b.quaternion.multiply(qa.setFromEuler(e));
          } else {
            const o = (g.osc || []).filter(x => x[0] === name);
            const vv = v.slice();
            for (const [, ax, amp, hz] of o) vv[ax] += amp * Math.sin(t * hz * Math.PI * 2);
            euler(vv[0], vv[1], vv[2]);
            qa.setFromEuler(e);
            if (vv.length > 3) qa.multiply(qt.setFromAxisAngle(X, fx * vv[3]));
            b.quaternion.slerp(qa, w);
          }
        }
        if (g.sob) {
          const hitch = Math.max(0, Math.sin(t * 7.5)) ** 3 * (0.5 + 0.5 * Math.sin(t * 1.3)) * w;
          for (const [n, z] of [['leftShoulder', 1], ['rightShoulder', -1]]) {
            const b = bone(n); if (b) { euler(0, 0, z * 0.09 * hitch); b.quaternion.multiply(qa.setFromEuler(e)); }
          }
          const sp = bone('upperChest') || bone('chest');
          if (sp) { euler(-0.04 * hitch, 0, 0); sp.quaternion.multiply(qa.setFromEuler(e)); }
        }
        for (const [name, v] of Object.entries(g.add || {})) {
          const b = bone(name.slice(1));
          if (!b) continue;
          touched.add(name.slice(1));
          euler(v[0] * w, v[1] * w, v[2] * w);
          b.quaternion.multiply(qa.setFromEuler(e));
        }
        for (const [k, v] of Object.entries(g.expr || {})) {
          exprNow[k] = Math.max(exprNow[k] || 0, sampleScalar(v, t) * w);
        }
      }

      // a held pose's head and neck ('+head', '+neck': looking down into her
      // book), added on top like a gesture's, fading out under one that moves them
      if (held) for (const [name, v] of Object.entries(held)) {
        if (!name.startsWith('+')) continue;
        const b = bone(name.slice(1)), k = 1 - (over[name] || 0);
        if (!b || k <= 0) continue;
        touched.add(name.slice(1));
        euler(v[0] * k, v[1] * k, v[2] * k);
        b.quaternion.multiply(qa.setFromEuler(e));
      }

      for (let i = active.length - 1; i >= 0; i--) if (active[i].gone) active.splice(i, 1);

      // tail
      // The tail hangs down at rest, so swinging it sideways from there sends it
      // between her legs - out of view. A wag lifts it first: the joints are
      // pulled up and back behind her (gravity reversed, strong enough to beat
      // the tail's stiffness), then swept side to side, so it rises into view
      // beside her waist and swishes there.
      wag.amount += (wag.target - wag.amount) * (1 - Math.exp(-(wag.target > wag.amount ? 2.5 : 1.2) * dt));
      if (tail.length) {
        wag.phase += dt * Math.PI * 2 * 1.3;
        const a = wag.amount, s = Math.sin(wag.phase);
        for (const { j, dir, power } of tail) {
          if (a < 0.01) { j.settings.gravityDir.copy(dir); j.settings.gravityPower = power; continue; }
          const up = wagUp.set(s * TAIL.sweep * wag.sweep, 1, -TAIL.back).normalize();
          j.settings.gravityDir.copy(dir).lerp(up, Math.min(1, a * 1.5)).normalize();
          j.settings.gravityPower = power + a * TAIL.lift;
        }
      }
    },
    expr() { return exprNow; },
    hipsY() { return hips && hipsRest ? hips.position.y - hipsRest.y : 0; },
  };
}
