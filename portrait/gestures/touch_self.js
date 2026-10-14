import { fingers } from './_pose.js';

// Right hand cupping her breast
const BREAST = {
  rightUpperArm: [0.05, 0.85, 0.95],
  rightLowerArm: [0, 1.9, -0.2, -0.6],
  rightHand: [-0.4, 0.05, 0.08],
  rightShoulder: [0, 0, -0.08],
};

// Left hand between her legs — lower, still tucked inward
const LEGS = {
  leftUpperArm: [0.1, -0.5, -1.4],
  leftLowerArm: [0, -1.5, 0.15, 0.5],
  leftHand:     [0.35, -0.15, -0.18],
  leftShoulder: [0, 0, 0.08],
};

// Panting loop
const PANT_KEYS = [];
const PANT_MOUTH = [[0, 0.25]];
let t = 0.3;
while (t < 6.8) {
  const rate = t < 3.5 ? 0.55 : 0.75;
  const deep = t < 3.5 ? 1 : 0.75;
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
PANT_MOUTH.push([6.8, 0.15], [7.5, 0.05]);

export default {
  keywords: [
    "touches herself", "hand between her legs", "one hand on her breast",
    "touches her breast", "hand on her pussy", "fingers herself",
    "plays with herself", "touches down there", "cups her breast",
  ],
  about: "lewd, one hand cupping her breast, one hand between her legs, blushing, panting",
  private: true,
  dur: 7.5, fade: [0.55, 0.7],
  keys: [
    [0.0, {
      ...BREAST,
      ...LEGS,
      ...fingers('right', 0.45),
      ...fingers('left', 0.4),
      '+spine': [0.04, 0, 0],
      '+head': [0.08, -0.04, -0.06],
    }],
    [1.2, {
      ...BREAST,
      ...LEGS,
      ...fingers('right', 0.55),
      ...fingers('left', 0.5),
      '+spine': [0.06, 0, 0.02],
      '+head': [0.1, -0.05, -0.08],
    }],
    [2.8, { '+head': [0.12, -0.03, -0.1] }],
    [4.6, {
      ...BREAST,
      ...LEGS,
      ...fingers('right', 0.5),
      ...fingers('left', 0.45),
      '+spine': [0.05, 0, 0.01],
      '+head': [0.09, -0.04, -0.07],
    }],
    [7.5, {
      ...BREAST,
      ...LEGS,
      ...fingers('right', 0.48),
      ...fingers('left', 0.42),
      '+spine': [0.04, 0, 0],
      '+head': [0.07, -0.03, -0.05],
    }],
    ...PANT_KEYS,
  ],
  expr: {
    blush: [[0, 0], [1.0, 0.85], [2.0, 1], [6.5, 0.95], [7.5, 0.6]],
    relaxed: [[0, 0.2], [1.2, 0.5], [6.5, 0.45], [7.5, 0.25]],
    aa: PANT_MOUTH,
  },
};
