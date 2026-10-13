// Gestures for the 3D (VRM) portrait: wave, hug, jump, shrug, and the
// little things she does on her own when nothing's happening.
//
// Every VRM has the same humanoid skeleton, so these work on any model
// (written for the T-pose rest VRM 1.0 and VRoid use). A gesture is a few
// keyframes of bone rotations, eased between, blended in and out over
// whatever the portrait is already doing (breathing, looking, talking),
// so starting or ending one never snaps.
//
//   bones      absolute rotations [x, y, z], radians, normalized bones;
//              a 4th number twists the bone about its own length first
//              (turning a forearm so the palm faces the right way)
//   '+bone'    added on top of what the portrait does (head, spine)
//   hips       an offset to the hips position, metres (jumping)
//   expr       expressions held while it plays ({happy: 0.8})
//   osc        a wobble on top: [bone, axis, amplitude, hz]
//
// Animation clips (.vrma, portrait/animations/) can stand in for any of
// these or add new ones: addClip() below. A clip plays through the same
// blend, so it eases in and out over her breathing like the rest.
//
// Poses are written for the right side; mirror() makes the left one.
// Her left is +X, she faces +Z (towards the camera).

const R = (o) => o;   // readability: a pose
const L_OF = { right: 'left', left: 'right' };

function mirrorName(n) {
  const add = n.startsWith('+') ? '+' : '';
  const b = add ? n.slice(1) : n;
  const m = b.replace(/^(right|left)/, s => L_OF[s]);
  return add + m;
}
function mirrorPose(p) {
  const out = {};
  for (const [k, v] of Object.entries(p)) {
    if (k === 'hips' || k === 'expr') { out[k] = v; continue; }
    out[mirrorName(k)] = v.length > 3 ? [v[0], -v[1], -v[2], v[3]] : [v[0], -v[1], -v[2]];
  }
  return out;
}
// both arms: the right one given, the left mirrored
function both(p) { return Object.assign({}, p, mirrorPose(p)); }

// The arms hanging naturally: down, elbows soft, fingers a little curled.
export const REST = both({
  rightUpperArm: [0, 0.05, 1.22], rightLowerArm: [0, 0.22, 0], rightHand: [0, 0, 0.08],
});
const FINGERS = ['Index', 'Middle', 'Ring', 'Little'];
for (const side of ['right', 'left']) {
  const s = side === 'right' ? 1 : -1;
  FINGERS.forEach((f, i) => {
    const c = 0.18 + i * 0.07;
    REST[`${side}${f}Proximal`] = [0, 0, s * c];
    REST[`${side}${f}Intermediate`] = [0, 0, s * (c + 0.1)];
    REST[`${side}${f}Distal`] = [0, 0, s * c];
  });
}
for (const b of ['UpperLeg', 'LowerLeg', 'Foot']) { REST['right' + b] = [0, 0, 0]; REST['left' + b] = [0, 0, 0]; }

// fist-ish / open hand helpers
function fingers(side, curl) {
  const s = side === 'right' ? 1 : -1, out = {};
  FINGERS.forEach((f, i) => {
    out[`${side}${f}Proximal`] = [0, 0, s * curl * (1 + i * 0.1)];
    out[`${side}${f}Intermediate`] = [0, 0, s * curl * 1.2];
    out[`${side}${f}Distal`] = [0, 0, s * curl];
  });
  return out;
}
const open = side => fingers(side, 0.05);

// ---------------------------------------------------------------------------
// The gestures
// ---------------------------------------------------------------------------
// rightHand x: the wrist turned so the palm faces whoever she's waving at
const WAVE_UP = R({ rightUpperArm: [0, 0.5, 0.75], rightLowerArm: [0, -0.2, -2.45], rightHand: [-1.2, 0, -0.1],
                    ...open('right'), '+head': [0, -0.08, -0.08], '+spine': [0, 0, -0.03] });
const HUG_OPEN = both({ rightUpperArm: [0, 0.85, 0.1], rightLowerArm: [0, 0.35, 0], rightHand: [0, 0, 0] });
const HUG_HOLD = both({ rightUpperArm: [0, 1.1, 0.05], rightLowerArm: [0, 1.15, -0.1], rightHand: [0, 0.3, 0] });

export const GESTURES = {
  wave: {
    dur: 2.6, fade: [0.35, 0.45],
    keys: [[0, WAVE_UP], [2.6, WAVE_UP]],
    osc: [['rightLowerArm', 2, 0.22, 2.3], ['rightHand', 1, 0.3, 2.3]],   // forearm sways, hand rocks in its own plane
    expr: { happy: 0.6 },
  },
  hug: {
    dur: 3.6, fade: [0.4, 0.6],
    keys: [
      [0.0, { ...HUG_OPEN, '+spine': [0.06, 0, 0], '+head': [0.05, 0, 0] }],
      [0.6, { ...HUG_OPEN, '+spine': [0.12, 0, 0], '+head': [0.08, 0, 0] }],
      [1.1, { ...HUG_HOLD, '+spine': [0.16, 0, 0], '+head': [0.12, 0, 0.16] }],
      [2.8, { ...HUG_HOLD, '+spine': [0.15, 0.04, 0], '+head': [0.12, 0.05, 0.2] }],
      [3.6, { ...HUG_OPEN, '+spine': [0.06, 0, 0], '+head': [0.04, 0, 0.05] }],
    ],
    expr: { happy: 0.85, blink: [[0, 0], [0.9, 0], [1.2, 0.85], [2.8, 0.85], [3.1, 0]] },
  },
  jump: {
    dur: 1.35, fade: [0.12, 0.3],
    keys: [
      [0.00, { ...REST }],
      [0.22, { ...both({ rightUpperArm: [0, -0.35, 1.3], rightLowerArm: [0, 0.3, 0] }),
               ...both({ rightUpperLeg: [-0.55, 0, 0], rightLowerLeg: [1.05, 0, 0], rightFoot: [-0.5, 0, 0] }),
               '+spine': [0.12, 0, 0], hips: [0, -0.09, 0] }],
      [0.42, { ...both({ rightUpperArm: [0, 0.2, -0.7], rightLowerArm: [0, 0.2, -0.2], ...open('right') }),
               ...both({ rightUpperLeg: [0.05, 0, 0], rightLowerLeg: [0.1, 0, 0], rightFoot: [0.3, 0, 0] }),
               '+spine': [-0.06, 0, 0], '+head': [-0.1, 0, 0], hips: [0, 0.16, 0] }],
      [0.62, { ...both({ rightUpperArm: [0, 0.2, -0.4], rightLowerArm: [0, 0.2, -0.3] }),
               ...both({ rightUpperLeg: [-0.25, 0, 0], rightLowerLeg: [0.4, 0, 0], rightFoot: [0, 0, 0] }),
               hips: [0, 0.11, 0] }],
      [0.80, { ...both({ rightUpperArm: [0, 0, 0.9], rightLowerArm: [0, 0.4, 0] }),
               ...both({ rightUpperLeg: [-0.5, 0, 0], rightLowerLeg: [0.9, 0, 0], rightFoot: [-0.4, 0, 0] }),
               '+spine': [0.1, 0, 0], hips: [0, -0.07, 0] }],
      [1.35, { ...REST, hips: [0, 0, 0] }],
    ],
    expr: { happy: 0.9, surprised: [[0, 0], [0.35, 0.5], [0.8, 0]] },
  },
  shrug: {
    dur: 2.2, fade: [0.3, 0.45],
    keys: [[0, both({ rightUpperArm: [0, 0.3, 1.0], rightLowerArm: [0, 1.65, -0.75], rightHand: [-0.8, 0, 0], ...open('right'),
                      rightShoulder: [0, 0, -0.2] })],
           [2.2, both({ rightUpperArm: [0, 0.3, 1.0], rightLowerArm: [0, 1.65, -0.75], rightHand: [-0.8, 0, 0], ...open('right'),
                        rightShoulder: [0, 0, -0.2] })]],
    add: { '+head': [0.02, 0, 0.14] },
    expr: { relaxed: 0.3 },
  },
  // ---- on her own, when idle ----
  stretch: {
    dur: 4.2, fade: [0.8, 0.9],
    keys: [
      [0.0, { ...both({ rightUpperArm: [0, 0.1, -1.35], rightLowerArm: [0, 0.6, 0], rightHand: [0, 0.3, 0] }),
              '+spine': [-0.07, 0, 0], '+head': [-0.18, 0, 0] }],
      [1.6, { ...both({ rightUpperArm: [0, 0.05, -1.45], rightLowerArm: [0, 0.3, 0], rightHand: [0, 0.3, 0] }),
              '+spine': [-0.1, 0, 0.06], '+head': [-0.2, 0, 0.08] }],
      [3.0, { ...both({ rightUpperArm: [0, 0.05, -1.45], rightLowerArm: [0, 0.3, 0], rightHand: [0, 0.3, 0] }),
              '+spine': [-0.1, 0, -0.06], '+head': [-0.2, 0, -0.08] }],
      [4.2, { ...both({ rightUpperArm: [0, 0.1, -1.3], rightLowerArm: [0, 0.6, 0], rightHand: [0, 0.3, 0] }),
              '+spine': [-0.05, 0, 0], '+head': [-0.1, 0, 0] }],
    ],
    expr: { relaxed: 0.6, blink: [[0, 0], [0.5, 1], [3.4, 1], [3.9, 0]], aa: [[0, 0], [0.8, 0.55], [2.0, 0.6], [2.6, 0]] },
  },
  look_hand: {
    dur: 3.6, fade: [0.6, 0.7],
    keys: [
      [0.0, { leftUpperArm: [0, -0.85, -0.75], leftLowerArm: [0, -1.9, 0.35], leftHand: [0.6, 0, 0.2], ...fingers('left', 0.1),
              '+head': [0.22, 0.18, 0.06] }],
      [1.8, { leftUpperArm: [0, -0.9, -0.7], leftLowerArm: [0, -1.95, 0.4], leftHand: [1.1, 0, 0.2], ...fingers('left', 0.5),
              '+head': [0.24, 0.2, 0.1] }],
      [3.6, { leftUpperArm: [0, -0.85, -0.75], leftLowerArm: [0, -1.9, 0.35], leftHand: [0.5, 0, 0.2], ...fingers('left', 0.2),
              '+head': [0.2, 0.16, 0.06] }],
    ],
    expr: { relaxed: 0.35 },
  },
  tuck_hair: {
    dur: 2.6, fade: [0.55, 0.6],
    keys: [
      [0.0, { rightUpperArm: [0, 0.7, 0.5], rightLowerArm: [0, 0, -2.55, -1.0], rightHand: [-1.1, 0.3, 0], ...fingers('right', 0.15),
              '+head': [0, -0.1, -0.14] }],
      [1.4, { rightUpperArm: [0, 0.7, 0.45], rightLowerArm: [0, 0, -2.65, -1.0], rightHand: [-1.2, 0.45, 0], ...fingers('right', 0.15),
              '+head': [0, -0.12, -0.18] }],
      [2.6, { rightUpperArm: [0, 0.68, 0.55], rightLowerArm: [0, 0, -2.45, -1.0], rightHand: [-1.1, 0.3, 0], ...fingers('right', 0.15),
              '+head': [0, -0.08, -0.1] }],
    ],
    expr: { relaxed: 0.4 },
  },
  bounce: {      // a happy little double bob
    dur: 1.3, fade: [0.15, 0.3],
    keys: [
      [0.00, { hips: [0, 0, 0], ...both({ rightUpperLeg: [0, 0, 0], rightLowerLeg: [0, 0, 0] }) }],
      [0.18, { hips: [0, -0.035, 0], ...both({ rightUpperLeg: [-0.25, 0, 0], rightLowerLeg: [0.45, 0, 0], rightFoot: [-0.2, 0, 0] }) }],
      [0.38, { hips: [0, 0.03, 0], ...both({ rightUpperLeg: [0, 0, 0], rightLowerLeg: [0, 0, 0], rightFoot: [0, 0, 0] }) }],
      [0.58, { hips: [0, -0.035, 0], ...both({ rightUpperLeg: [-0.25, 0, 0], rightLowerLeg: [0.45, 0, 0], rightFoot: [-0.2, 0, 0] }) }],
      [0.80, { hips: [0, 0.025, 0], ...both({ rightUpperLeg: [0, 0, 0], rightLowerLeg: [0, 0, 0], rightFoot: [0, 0, 0] }) }],
      [1.30, { hips: [0, 0, 0] }],
    ],
    add: { '+head': [0, 0, 0.08] },
    expr: { happy: 0.75 },
  },
  explain: {     // a hand that comes up while she talks
    dur: 2.4, fade: [0.5, 0.6],
    keys: [[0, { rightUpperArm: [0, 0.3, 1.05], rightLowerArm: [0, 1.2, 0], rightHand: [-0.9, 0, 0.15], ...fingers('right', 0.1) }],
           [1.2, { rightUpperArm: [0, 0.35, 1.0], rightLowerArm: [0, 1.3, 0], rightHand: [-1.1, 0, 0.1], ...fingers('right', 0.1) }],
           [2.4, { rightUpperArm: [0, 0.3, 1.05], rightLowerArm: [0, 1.2, 0], rightHand: [-0.9, 0, 0.15], ...fingers('right', 0.15) }]],
  },
};
// left-handed versions, so it isn't always the same hand
GESTURES.wave_left = mirrorGesture(GESTURES.wave);
GESTURES.explain_left = mirrorGesture(GESTURES.explain);
GESTURES.tuck_hair_left = mirrorGesture(GESTURES.tuck_hair);

function mirrorGesture(g) {
  return Object.assign({}, g, {
    keys: g.keys.map(([t, p]) => [t, mirrorPose(p)]),
    add: g.add && mirrorPose(g.add),
    osc: g.osc && g.osc.map(([b, ax, a, hz]) => [mirrorName(b), ax, ax === 0 ? a : -a, hz]),
  });
}

export const IDLE = ['stretch', 'look_hand', 'tuck_hair', 'tuck_hair_left', 'bounce'];
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
  return prev[1].map((v, i) => v + (next[1][i] - v) * k);
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
  const active = [];          // {g, name, t, out}
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
            if (b.kind === 'quaternion') b.target.quaternion.slerp(b.g.quaternion, w);
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
        for (const [name, v] of Object.entries(g.add || {})) {
          const b = bone(name.slice(1));
          if (!b) continue;
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
