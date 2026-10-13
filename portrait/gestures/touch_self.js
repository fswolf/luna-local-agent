// touch_self: one hand on her breast, one between her legs, blushing and panting
import { fingers } from './_pose.js';

// Right hand on her breast
const BREAST = {
  rightUpperArm: [0.05, 0.85, 0.95],
  rightLowerArm: [0, 1.9, -0.2, -0.6],
  rightHand: [-0.4, 0.05, 0.08],
  rightShoulder: [0, 0, -0.08],
};

// Left hand between her legs
const LEGS = {
  leftUpperArm: [0.1, -0.4, -1.15],
  leftLowerArm: [0, -1.8, 0.3, 0.5],
  leftHand: [0.3, -0.1, -0.1],
  leftShoulder: [0, 0, 0.1],
};

export default {
  keywords: [
    "touches herself", "hand between her legs", "one hand on her breast",
    "touches her breast", "hand on her pussy", "fingers herself",
    "plays with herself", "touches down there",
  ],
  about: "lewd, one hand on her breast, one between her legs, blushing, panting",
  private: true,
  dur: 7.0, fade: [0.55, 0.7],
  keys: [
    [0.0, {
      ...BREAST,
      ...LEGS,
      ...fingers('right', 0.45),
      ...fingers('left', 0.35),
      '+spine': [0.04, 0, 0],
      '+chest': [0.03, 0, 0],
      '+head': [0.08, -0.04, -0.06],
    }],
    [1.2, {
      ...BREAST,
      ...LEGS,
      ...fingers('right', 0.55),
      ...fingers('left', 0.45),
      '+spine': [0.06, 0, 0.02],
      '+chest': [0.06, 0, 0],
      '+head': [0.1, -0.05, -0.08],
    }],
    [2.8, {
      '+chest': [0.08, 0, 0],
      '+head': [0.12, -0.03, -0.1],
    }],
    [4.2, {
      ...BREAST,
      ...LEGS,
      ...fingers('right', 0.5),
      ...fingers('left', 0.4),
      '+spine': [0.05, 0, 0.01],
      '+chest': [0.05, 0, 0],
      '+head': [0.09, -0.04, -0.07],
    }],
    [5.6, {
      '+chest': [0.07, 0, 0],
      '+head': [0.1, -0.04, -0.09],
    }],
    [7.0, {
      ...BREAST,
      ...LEGS,
      ...fingers('right', 0.48),
      ...fingers('left', 0.38),
      '+spine': [0.04, 0, 0],
      '+chest': [0.04, 0, 0],
      '+head': [0.07, -0.03, -0.05],
    }],
  ],
  expr: {
    blush: [[0, 0], [1.0, 0.85], [2.0, 1], [6.0, 0.95], [7.0, 0.6]],
    relaxed: [[0, 0.2], [1.2, 0.5], [6.2, 0.45], [7.0, 0.25]],
    // soft panting via subtle mouth
    ou: [[0, 0], [1.5, 0.3], [3.0, 0.4], [5.0, 0.35], [7.0, 0.15]],
  },
};
