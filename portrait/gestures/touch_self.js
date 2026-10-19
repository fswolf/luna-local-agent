import { fingers } from './_pose.js';

// Right hand cupping her breast
const BREAST = {
  rightUpperArm: [0.05, 0.85, 0.95],
  rightLowerArm: [0, 1.9, -0.2, -0.6],
  rightHand: [-0.4, 0.05, 0.08],
  rightShoulder: [0, 0, -0.08],
};

// Left hand between her legs. With the arm hanging down, x swings it forward
// (y barely moves it there) and z past -1.57 angles it in through her hip -
// so: down, a touch forward, the forearm angled in to her groin, fingers
// down. Checked in full-body framing from the front, the side and 3/4.
const LEGS = {
  leftUpperArm: [-0.38, 0, -1.6],
  leftLowerArm: [0, -0.05, -0.55],
  leftHand:     [0.85, 0, -0.3],
  leftShoulder: [0, 0, 0.1],
};
// the hand moving a little, slow
const RUB = a => ({ leftHand: [0.85 + a, 0, -0.3 - a * 0.5] });
// knees easing in, hips tipped a touch: only shows in full-body framing
const KNEES = { leftUpperLeg: [0, 0, 0.06], rightUpperLeg: [0, 0, -0.06], '+hips': [0.03, 0, 0] };
// head down, eyes stay on you (her gaze tracks the viewer, so they look up)
const LOOK = (d = 0) => ({ '+head': [0.22 + d, -0.04, -0.08], '+neck': [0.05, 0, -0.02] });

const DUR = 10;

// Panting loop
const PANT_KEYS = [];
const PANT_MOUTH = [[0, 0.25]];
let t = 0.3;
while (t < 9.2) {
  const rate = t < 5.0 ? 0.6 : 0.8;
  const deep = t < 5.0 ? 1 : 0.75;
  PANT_KEYS.push([t, {
    '+upperChest': [-0.055 * deep, 0, 0],
    '+rightShoulder': [0, 0, -0.06 * deep],
    '+leftShoulder': [0, 0, 0.06 * deep],
  }]);
  PANT_MOUTH.push([t, 0.5 * deep]);
  PANT_KEYS.push([t + rate * 0.45, {
    '+upperChest': [0.025, 0, 0],
    '+rightShoulder': [0, 0, 0.01],
    '+leftShoulder': [0, 0, -0.01],
  }]);
  PANT_MOUTH.push([t + rate * 0.45, 0.3 * deep]);
  t += rate;
}
PANT_MOUTH.push([9.2, 0.15], [DUR, 0.05]);

export default {
  keywords: [
    "touches herself", "hand between her legs", "one hand on her breast",
    "touches her breast", "hand on her pussy", "fingers herself",
    "plays with herself", "touches down there", "cups her breast",
  ],
  about: "lewd, one hand cupping her breast, one hand between her legs, blushing, panting",
  private: true,
  lewd: true,         // held back on a stream where lewd is off (twitch/youtube "lewd": false)
  sound: { name: 'touch-self', from: 'random' },   // portrait/sounds/touch-self.mp3, a random stretch of it
  dur: DUR, fade: [0.55, 0.7],
  keys: [
    [0.0, { ...BREAST, ...LEGS, ...KNEES, ...fingers('right', 0.45), ...fingers('left', 0.4),
            '+spine': [0.05, 0, 0], ...LOOK() }],
    [1.2, { ...BREAST, ...LEGS, ...KNEES, ...fingers('right', 0.55), ...fingers('left', 0.5),
            '+spine': [0.08, 0, 0.02], ...LOOK(0.03) }],
    // the hand moving, slow: a second each way
    [2.0, RUB(0.08)], [3.0, RUB(-0.04)], [4.0, RUB(0.08)], [5.0, RUB(-0.04)],
    [5.4, { ...BREAST, ...KNEES, ...fingers('right', 0.5), ...fingers('left', 0.45),
            '+spine': [0.07, 0, 0.01], ...LOOK(0.02) }],
    [6.0, RUB(0.08)], [7.0, RUB(-0.04)], [8.0, RUB(0.08)], [9.0, RUB(-0.02)],
    [DUR, { ...BREAST, ...LEGS, ...KNEES, ...fingers('right', 0.48), ...fingers('left', 0.42),
            '+spine': [0.05, 0, 0], ...LOOK(-0.04) }],
    ...PANT_KEYS,
  ],
  expr: {
    blush: [[0, 0], [1.0, 0.85], [2.0, 1], [9.0, 0.95], [DUR, 0.6]],
    relaxed: [[0, 0.2], [1.2, 0.5], [9.0, 0.45], [DUR, 0.25]],
    aa: PANT_MOUTH,
  },
};
