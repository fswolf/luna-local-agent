// glowstick_dance: raving with a glow stick in each fist (the rave set,
// props.js), on a 128 bpm beat. Fist pumps one arm at a time, both sticks
// held up swaying side to side, arms crossing in front of her and flung wide,
// then both fists pumping overhead. Fists the whole way, so the sticks stay in
// her hands, and the moves are big ones so their light trails draw on the beat.
import { both, fingers } from './_pose.js';

const BEAT = 60 / 128;                    // seconds per beat (128 bpm)

const FISTS = { ...fingers('right', 0.95), ...fingers('left', 0.95) };
// right side; both() mirrors. The hand turned up (rightHand y) stands the stick
// up out of her fist like a torch, rather than lying across it.
const UP = (y = 1.0) => ({ rightUpperArm: [0, 0.4, -1.0], rightLowerArm: [0, 0.3, -0.3], rightHand: [0, y, 0] });
const HEAD = { rightUpperArm: [0, 0.5, -0.4], rightLowerArm: [0, 1.6, -0.2], rightHand: [1.2, 0, 0] };   // fist by her head, stick up beside it
const CHEST = { rightUpperArm: [0, 0.8, 1.05], rightLowerArm: [0, 2.0, -0.35], rightHand: [0, 0, 0] };
const WIDE = { rightUpperArm: [0, 0.3, 0.1], rightLowerArm: [0, 0.4, 0], rightHand: [0, 0.8, 0] };    // flung out to the side
const CROSS = { rightUpperArm: [0, 1.35, 0.35], rightLowerArm: [0, 1.0, -0.3], rightHand: [0, 0, 0] }; // wrists crossed at her chest

const left = p => both(p);                       // (both(): the left from the right)
const R = (p, q) => ({ ...both(q), ...p });      // right arm p, left arm the mirror of q
const KNEES = (k) => both({ rightUpperLeg: [-0.2 * k, 0, 0], rightLowerLeg: [0.4 * k, 0, 0], rightFoot: [-0.2 * k, 0, 0] });

const keys = [];
const at = (t, arms, k, side, lean = 0) => keys.push([t, {
  ...arms, ...FISTS, ...KNEES(k),
  hips: [0.03 * side, -0.04 * k, 0],
  '+spine': [0.03 * k, 0, -0.06 * side - lean],
  '+head': [0.09 * k - 0.02, 0.04 * side, 0.06 * side],     // a nod down on every beat
}]);

for (let i = 0; i < 16; i++) {
  const t = i * BEAT, side = i % 2 ? -1 : 1, mid = t + BEAT / 2;
  if (i < 4) {
    // fist pumps, one arm then the other, the other fist at her chest
    at(t, side > 0 ? R(UP(), CHEST) : R(CHEST, UP()), 1, side);
    at(mid, R(HEAD, HEAD), 0.2, 0);
  } else if (i < 8) {
    // both sticks up, swaying over her head, wrists flicking them on the beat
    at(t, left(UP(1.0)), 1, side, 0.1 * side);
    at(mid, left(UP(0.3)), 0.2, side * 0.5, 0.05 * side);
  } else if (i < 12) {
    // flung wide on the beat, crossed in front of her between
    at(t, left(WIDE), 1, side);
    at(mid, left(CROSS), 0.3, 0);
  } else {
    // both fists pumping overhead together
    at(t, left(UP()), 1, side);
    at(mid, left(HEAD), 0.2, 0);
  }
}
keys.push([16 * BEAT, { ...left(CHEST), ...FISTS, ...KNEES(0), hips: [0, 0, 0], '+spine': [0, 0, 0], '+head': [0, 0, 0] }]);

export default {
  bpm: 128,                     // its beat, so music can play it at the song's tempo (portrait.js musicDance)
  about: "raving, hyped, music: dancing with glow sticks, pumping them overhead to the beat",
  keywords: ["rave", "raving", "glow stick", "glowstick"],
  dur: 16 * BEAT, fade: [0.4, 0.6],
  keys,
  expr: { happy: 0.6 },
};
