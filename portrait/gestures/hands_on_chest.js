// hands_on_chest: both hands laid flat on her upper chest, one over the
// other, a soft breath, head tipped a little. No about/keywords on
// purpose: kept for the touch zones (a chest touch), not offered as a
// tag or played from chat yet.
import { both, open } from './_pose.js';

const HANDS = {
  ...both({ rightUpperArm: [0, 0.5, 1.42], rightLowerArm: [0, 2.35, -0.1, -0.8], rightHand: [0, 0.25, 0.9] }),
  ...open('right'), ...open('left'),
};

export default {
  dur: 4.0, fade: [0.6, 0.8],
  keys: [
    [0.0, { ...HANDS, '+spine': [0.03, 0, 0], '+head': [0.05, 0, 0] }],
    [1.6, { '+spine': [0.05, 0, 0], '+head': [0.1, 0.06, 0.08] }],     // a breath in, head tips
    [3.0, { '+spine': [0.03, 0, 0], '+head': [0.08, 0.05, 0.07] }],
    [4.0, { ...HANDS, '+spine': [0.03, 0, 0], '+head': [0.04, 0, 0.03] }],
  ],
  expr: { relaxed: 0.35 },
};
