// cup_breasts: both hands cup her chest, holds the pose, looks at you with blush
import { both, fingers } from './_pose.js';

// Same palm/twist as the working shy_cup, but less forearm bend toward center
// so the hands stay on each breast instead of crossing
const CUP = both({
  rightUpperArm: [0.06, 0.82, 0.88],
  rightLowerArm: [0, 1.4, -0.35, -0.55],
  rightHand: [-0.35, 0.12, 0.18],
  rightShoulder: [0, 0, -0.08],
});

export default {
  keywords: [
    "cups her breasts", "cups her chest", "hands on her breasts",
    "holds her breasts", "squeezes her breasts", "grabs her breasts",
    "hands under her breasts", "cups them", "holds them up",
    "presents her chest", "pushes them together",
  ],
  about: "lewd, teasing, cups her breasts, flirty hold",
  private: false,
  dur: 6.2, fade: [0.55, 0.75],
  keys: [
    [0.0, {
      ...CUP,
      ...fingers('right', 0.35),
      ...fingers('left', 0.35),
      '+spine': [0.03, 0, 0],
      '+chest': [0.02, 0, 0],
      '+head': [0.05, 0, -0.03],
    }],
    [1.1, {
      ...CUP,
      ...fingers('right', 0.48),
      ...fingers('left', 0.48),
      '+spine': [0.05, 0, 0.015],
      '+chest': [0.045, 0, 0],
      '+head': [0.08, -0.035, -0.08],
    }],
    [2.6, {
      '+spine': [0.06, 0, -0.015],
      '+chest': [0.055, 0, 0],
      '+head': [0.09, -0.02, -0.09],
    }],
    [4.0, {
      ...CUP,
      ...fingers('right', 0.45),
      ...fingers('left', 0.45),
      '+spine': [0.055, 0, 0.01],
      '+chest': [0.05, 0, 0],
      '+head': [0.085, -0.03, -0.075],
    }],
    [5.2, {
      '+spine': [0.05, 0, -0.01],
      '+chest': [0.045, 0, 0],
      '+head': [0.08, -0.025, -0.08],
    }],
    [6.2, {
      ...CUP,
      ...fingers('right', 0.42),
      ...fingers('left', 0.42),
      '+spine': [0.04, 0, 0],
      '+chest': [0.035, 0, 0],
      '+head': [0.06, -0.02, -0.05],
    }],
  ],
  expr: {
    blush: [[0, 0], [0.9, 0.8], [1.5, 0.95], [5.0, 0.9], [6.2, 0.5]],
    relaxed: [[0, 0.15], [1.2, 0.55], [5.2, 0.5], [6.2, 0.25]],
    happy: [[0, 0], [1.4, 0.3], [4.5, 0.28], [6.2, 0.12]],
  },
};
