// Gestures for the 3D (VRM) portrait: the player, and the list of what
// she can do. Each gesture is its own file in gestures/ (wave.js, hug.js,
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
//   about      when to use it: offered to her as a [tag] in tags mode
//   idle       one of the things she does on her own
//   private    never from stream chat; only offered in your own turns
//   left       also make a left-handed copy, <name>_left
//
// Animation clips (.vrma, portrait/animations/) can stand in for any of
// these or add new ones: addClip() below.

import { REST, mirrorGesture } from './gestures/_pose.js';
export { REST };

// The list comes from the server (every gesture/*.js not starting with _);
// without one (a static copy of the page), the built-ins.
const BUILT_IN = ['wink', 'shh', 'wave', 'hug', 'jump', 'shrug', 'kiss', 'shy', 'cry', 'stretch', 'look_hand',
                  'tuck_hair', 'bounce', 'explain'];
export const FAILED = {};      // name -> why it didn't load (shown on the debug page)
const list = await fetch('gestures/index.json').then(r => r.ok ? r.json() : null).catch(() => null);
if (!list) FAILED['(the list)'] = "the server didn't send gestures/index.json, so only the built-ins loaded - "
  + 'restart Luna or ./viewer.sh (an older copy is still running)';

export const GESTURES = {};
export const ABOUT = {};
for (const name of list || BUILT_IN) {
  try {
    const g = (await import(`./gestures/${name}.js`)).default;
    GESTURES[name] = g;
    if (g.about) ABOUT[name] = g.about;
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
function sample(keys, name, t) {
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
function sampleScalar(v, t) {
  if (!Array.isArray(v)) return v;
  let prev = v[0], next = null;
  for (const kv of v) { if (kv[0] <= t) prev = kv; else { next = kv; break; } }
  if (!next) return prev[1];
  return prev[1] + (next[1] - prev[1]) * ease((t - prev[0]) / (next[0] - prev[0]));
}

export function createGestures(THREE, vrm) {
  const hips = vrm.humanoid.getNormalizedBoneNode('hips');
  const hipsRest = hips ? hips.position.clone() : null;
  const bone = n => vrm.humanoid.getNormalizedBoneNode(n);
  const active = [];
  // bones the portrait sets itself every frame, before the gestures
  const MANAGED = new Set(['head', 'neck', 'spine', 'leftShoulder', 'rightShoulder',
                           bone('upperChest') ? 'upperChest' : 'chest']);
  const touched = new Set();      // every bone a gesture has written to
  const touchedObj = new Set();   // ...and every node a .vrma clip has          // {g, name, t, out}
  const qa = new THREE.Quaternion(), e = new THREE.Euler();
  // VRM 0.x faces the other way in its own space: same pose, x and z flipped.
  const fx = vrm.meta?.metaVersion === '0' ? -1 : 1;
  const euler = (x, y, z) => e.set(fx * x, y, fx * z);
  const qt = new THREE.Quaternion(), X = new THREE.Vector3(1, 0, 0);
  let exprNow = {};

  // the tail: spring bones, so it can't be posed; it wags by swinging
  // the gravity its joints feel from side to side
  const tail = [];
  for (const j of vrm.springBoneManager?.joints || []) {
    if (/tail/i.test(j.bone?.name || '')) tail.push({ j, dir: j.settings.gravityDir.clone(), power: j.settings.gravityPower });
  }
  const wag = { amount: 0, target: 0, phase: 0 };

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
      const g = GESTURES[name];
      if (!vs.length && !g) return false;
      for (const a of active) if (!a.out) a.out = a.t;          // let the old one go
      if (vs.length) active.push(startClip(name, vs[Math.floor(Math.random() * vs.length)]));
      else active.push({ g, name, t: 0, out: 0, ch: channels(g) });
      return true;
    },
    stop() { for (const a of active) if (!a.out) a.out = a.t; },
    wag(level) { wag.target = level; },

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
    },

    // After the portrait has set its own pose for the frame.
    update(dt) {
      exprNow = {};
      // oldest first, so the newest one lands on top while the old fades
      for (let i = 0; i < active.length; i++) {
        const a = active[i], g = a.g;
        a.t += dt;
        const [fi, fo] = g.fade || [0.3, 0.4];
        const end = a.out ? a.out + fo : g.dur;
        if (a.t >= end) { a.gone = true; continue; }
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

      for (let i = active.length - 1; i >= 0; i--) if (active[i].gone) active.splice(i, 1);

      // tail
      wag.amount += (wag.target - wag.amount) * (1 - Math.exp(-3 * dt));
      if (tail.length) {
        wag.phase += dt * Math.PI * 2 * 1.6;
        const s = Math.sin(wag.phase) * wag.amount;
        for (const { j, dir, power } of tail) {
          j.settings.gravityDir.set(dir.x + s * 1.6, dir.y, dir.z).normalize();
          j.settings.gravityPower = power + Math.abs(wag.amount) * 0.6;
        }
      }
    },
    expr() { return exprNow; },
    hipsY() { return hips && hipsRest ? hips.position.y - hipsRest.y : 0; },
  };
}
