// cup_breasts: both hands cup her chest, holds the pose, looks at you with blush
import { both, fingers } from './_pose.js';

// Hands on the breasts (lower than last), pressed against the chest
const CUP = both({
  rightUpperArm: [0.05, 0.75, 1.05],
  rightLowerArm: [0, 2.0, -0.15, -0.65],
  rightHand: [-0.4, 0.05, 0.08],
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
  dur: 8.5, fade: [0.6, 0.8],
  keys: [
    [0.0, {
      ...CUP,
      ...fingers('right', 0.4),
      ...fingers('left', 0.4),
      '+spine': [0.03, 0, 0],
      '+chest': [0.02, 0, 0],
      '+head': [0.05, 0, -0.03],
    }],
    [1.4, {
      ...CUP,
      ...fingers('right', 0.52),
      ...fingers('left', 0.52),
      '+spine': [0.05, 0, 0.015],
      '+chest': [0.045, 0, 0],
      '+head': [0.08, -0.035, -0.08],
    }],
    [3.5, {
      '+spine': [0.06, 0, -0.015],
      '+chest': [0.055, 0, 0],
      '+head': [0.09, -0.02, -0.09],
    }],
    [5.5, {
      ...CUP,
      ...fingers('right', 0.5),
      ...fingers('left', 0.5),
      '+spine': [0.055, 0, 0.01],
      '+chest': [0.05, 0, 0],
      '+head': [0.085, -0.03, -0.075],
    }],
    [7.2, {
      '+spine': [0.05, 0, -0.01],
      '+chest': [0.045, 0, 0],
      '+head': [0.08, -0.025, -0.08],
    }],
    [8.5, {
      ...CUP,
      ...fingers('right', 0.48),
      ...fingers('left', 0.48),
      '+spine': [0.04, 0, 0],
      '+chest': [0.035, 0, 0],
      '+head': [0.06, -0.02, -0.05],
    }],
  ],
  expr: {
    blush: [[0, 0], [1.2, 0.8], [2.0, 0.95], [7.0, 0.9], [8.5, 0.5]],
    relaxed: [[0, 0.15], [1.6, 0.55], [7.2, 0.5], [8.5, 0.25]],
    happy: [[0, 0], [1.8, 0.3], [6.5, 0.28], [8.5, 0.12]],
  },
};
