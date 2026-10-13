// Shared by every gesture file: the rest pose, mirroring, finger helpers.
//
// Bones are the standard VRM humanoid names, rotations [x, y, z] in radians
// (normalized bones, T-pose rest). Poses are written for the right side;
// both() / mirrorPose() make the left. Her left is +X, she faces +Z.
export const R = (o) => o;   // readability: a pose
const L_OF = { right: 'left', left: 'right' };

export function mirrorName(n) {
  const add = n.startsWith('+') ? '+' : '';
  const b = add ? n.slice(1) : n;
  const m = b.replace(/^(right|left)/, s => L_OF[s]);
  return add + m;
}
export function mirrorPose(p) {
  const out = {};
  for (const [k, v] of Object.entries(p)) {
    if (k === 'hips' || k === 'expr') { out[k] = v; continue; }
    out[mirrorName(k)] = v.length > 3 ? [v[0], -v[1], -v[2], v[3]] : [v[0], -v[1], -v[2]];
  }
  return out;
}
// both arms: the right one given, the left mirrored
export function both(p) { return Object.assign({}, p, mirrorPose(p)); }

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
export function fingers(side, curl) {
  const s = side === 'right' ? 1 : -1, out = {};
  FINGERS.forEach((f, i) => {
    out[`${side}${f}Proximal`] = [0, 0, s * curl * (1 + i * 0.1)];
    out[`${side}${f}Intermediate`] = [0, 0, s * curl * 1.2];
    out[`${side}${f}Distal`] = [0, 0, s * curl];
  });
  return out;
}
export const open = side => fingers(side, 0.05);

// the same gesture with the other hand
export function mirrorGesture(g) {
  return Object.assign({}, g, {
    keys: g.keys.map(([t, p]) => [t, mirrorPose(p)]),
    add: g.add && mirrorPose(g.add),
    osc: g.osc && g.osc.map(([b, ax, a, hz]) => [mirrorName(b), ax, ax === 0 ? a : -a, hz]),
  });
}
