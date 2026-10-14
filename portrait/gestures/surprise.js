// surprise: a happy gasp - a little jolt back, hands fly to her chest, eyes
// wide, then the smile catches up and she bounces once with delight.
import { both, open } from './_pose.js';

// hands up on her upper chest, elbows out so the forearms clear her chest
const HANDS = {
  ...both({ rightUpperArm: [-0.2, 0.5, 0.7], rightLowerArm: [0, 2.25, 0.2, -1.35], rightHand: [0, 0.6, 0.4] }),
  ...open('right'), ...open('left'),
};

export default {
  about: "happy surprise, delighted by something unexpected",
  keywords: ["gasp", "😮", "😲"],
  dur: 3.2, fade: [0.15, 0.7],
  keys: [
    [0.00, { hips: [0, 0, 0], '+spine': [0, 0, 0], '+head': [0, 0, 0] }],
    [0.22, { ...HANDS, hips: [0, 0.015, -0.01], '+spine': [-0.07, 0, 0], '+head': [-0.12, 0, 0] }],   // the jolt
    [0.9,  { ...HANDS, hips: [0, 0, 0], '+spine': [-0.03, 0, 0], '+head': [-0.06, 0, 0.03] }],
    [1.5,  { hips: [0, -0.012, 0], '+spine': [0.04, 0, 0], '+head': [0.04, 0.03, 0.08] }],             // and the delight
    [1.8,  { hips: [0, 0.01, 0] }],
    [2.1,  { hips: [0, -0.006, 0] }],
    [3.2,  { ...HANDS, hips: [0, 0, 0], '+spine': [0.02, 0, 0], '+head': [0.02, 0.02, 0.06] }],
  ],
  expr: { surprised: [[0, 0], [0.2, 1], [1.0, 0.75], [1.8, 0.15], [3.2, 0]],
          happy: [[0, 0], [1.1, 0], [1.8, 0.8], [3.2, 0.7]],
          blink: [[0, 0], [3.2, 0]] },
};
