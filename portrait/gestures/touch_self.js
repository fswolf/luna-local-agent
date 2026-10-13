// touch_self: one hand on her breast, one between her legs, blushing and panting
import { fingers } from './_pose.js';

// Right hand on her breast
const BREAST = {
  rightUpperArm: [0.05, 0.85, 0.95],
  rightLowerArm: [0, 1.9, -0.2, -0.6],
  rightHand: [-0.4, 0.05, 0.08],
  rightShoulder: [0, 0, -0.08],
};

// Left hand forced down between the legs
const LEGS = {
  leftUpperArm: [0.2, -0.3, -1.45],
  leftLowerArm: [0, -2.3, 0.6, 0.4],
  leftHand: [0.4, -0.2, -0.2],
  leftShoulder: [0, 0, 0.15],
};

export default {
  keywords: [
    "touches herself", "hand between her legs", "one hand on her breast",
    "touches her breast", "hand on her pussy", "fingers herself",
    "plays with herself", "touches down there",
  ],
  about: "lewd, one hand on her breast, one between her legs, blushing, panting",
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
    [2.0, { '+upperChest': [-0.05, 0, 0] }],
    [2.5, { '+upperChest': [0.02, 0, 0] }],
    [3.2, { '+upperChest': [-0.06, 0, 0], '+head': [0.12, -0.03, -0.1] }],
    [3.8, { '+upperChest': [0.02, 0, 0] }],
    [4.6, {
      ...BREAST,
      ...LEGS,
      ...fingers('right', 0.5),
      ...fingers('left', 0.45),
      '+spine': [0.05, 0, 0.01],
      '+head': [0.09, -0.04, -0.07],
    }],
    [5.2, { '+upperChest': [-0.05, 0, 0] }],
    [5.8, { '+upperChest': [0.02, 0, 0] }],
    [6.5, { '+upperChest': [-0.04, 0, 0], '+head': [0.1, -0.04, -0.09] }],
    [7.5, {
      ...BREAST,
      ...LEGS,
      ...fingers('right', 0.48),
      ...fingers('left', 0.42),
      '+spine': [0.04, 0, 0],
      '+head': [0.07, -0.03, -0.05],
    }],
  ],
  expr: {
    blush: [[0, 0], [1.0, 0.85], [2.0, 1], [6.5, 0.95], [7.5, 0.6]],
    relaxed: [[0, 0.2], [1.2, 0.5], [6.5, 0.45], [7.5, 0.25]],
    aa: [[0, 0], [1.5, 0.25], [3.0, 0.35], [5.0, 0.3], [7.5, 0.1]],
  },
};
