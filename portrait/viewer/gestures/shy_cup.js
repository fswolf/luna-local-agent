// cup_breasts: both hands cup her chest, holds the pose, looks at you with blush
import { both, fingers } from './_pose.js';

const CUP = both({
  rightUpperArm: [0.08, 0.95, 0.72],
  rightLowerArm: [0, 1.75, -0.45, -0.55],
  rightHand: [-0.35, 0.12, 0.18],
  rightShoulder: [0, 0, -0.08],
});

export default {
  about: "lewd, teasing, cups her breasts, flirty hold",
  private: false,
  dur: 4.8, fade: [0.5, 0.7],
  keys: [
    [0.0, { ...CUP, ...fingers('right', 0.35), ...fingers('left', 0.35),
            '+spine': [0.04, 0, 0], '+chest': [0.03, 0, 0], '+head': [0.06, 0, -0.04] }],
    [1.0, { ...CUP, ...fingers('right', 0.45), ...fingers('left', 0.45),
            '+spine': [0.06, 0, 0.02], '+chest': [0.05, 0, 0], '+head': [0.08, -0.04, -0.08] }],
    [2.4, { '+spine': [0.07, 0, -0.02], '+chest': [0.06, 0, 0], '+head': [0.09, -0.02, -0.1] }],
    [3.6, { ...CUP, ...fingers('right', 0.42), ...fingers('left', 0.42),
            '+spine': [0.05, 0, 0.01], '+chest': [0.04, 0, 0], '+head': [0.07, -0.03, -0.07] }],
    [4.8, { ...CUP, ...fingers('right', 0.4), ...fingers('left', 0.4),
            '+spine': [0.04, 0, 0], '+chest': [0.03, 0, 0], '+head': [0.05, -0.02, -0.05] }],
  ],
  expr: {
    blush: [[0, 0], [0.8, 0.85], [3.8, 0.9], [4.8, 0.55]],
    relaxed: [[0, 0.2], [1.0, 0.55], [4.0, 0.5], [4.8, 0.3]],
    happy: [[0, 0], [1.2, 0.35], [3.5, 0.3], [4.8, 0.15]],
  },
};