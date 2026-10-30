// tie_off: takes her tie off. A hand to the knot, two tugs to loosen it, both
// hands lift the loop over her head (the tie comes off there: clothes), and a
// little toss to the side. A rough first pass, to refine in the pose studio.
// No about or keywords: it plays when her clothes come off (portrait.js
// undress), not as a gesture of its own.
import { both, open, fingers, REST } from './_pose.js';

// elbow down by her side, fingers on the knot at her collar
const KNOT = { rightUpperArm: [0.4, 0.8, 0.95], rightLowerArm: [0, 2.6, 0, -1.4], rightHand: [0, 0.4, 0.5], ...fingers('right', 0.7) };
const TUG = { rightUpperArm: [0.4, 0.8, 1.05], rightLowerArm: [0, 2.4, 0, -1.4], rightHand: [0, 0.4, 0.5], ...fingers('right', 0.7) };
const OVER = { ...both({ rightUpperArm: [0, 0.0, -0.95], rightLowerArm: [0, 1.6, 0], rightHand: [0, 0.2, 0] }),
               ...fingers('right', 0.7), ...fingers('left', 0.7) };
const TOSS = { rightUpperArm: [0, 0.6, 0.55], rightLowerArm: [0, 0.5, 0], rightHand: [0, 0, 0.3], ...open('right') };

export default {
  private: true,
  dur: 3.6, fade: [0.5, 0.7],
  keys: [
    [0.6, { ...REST, ...KNOT, '+head': [-0.1, 0, 0] }],
    [1.0, { ...REST, ...TUG, '+head': [-0.15, 0.1, 0.05] }],
    [1.35, { ...REST, ...KNOT, '+head': [-0.1, 0, 0] }],
    [1.7, { ...REST, ...TUG, '+head': [-0.15, 0.1, 0.05] }],
    [2.3, { ...OVER, '+head': [0.2, 0, 0] }],
    [2.9, { ...REST, ...TOSS, '+head': [0, -0.25, 0] }],
    [3.6, { ...REST, '+head': [0, -0.1, 0] }],
  ],
  clothes: [{ at: 2.2, off: ['tie'] }],
  expr: { relaxed: [[0, 0], [0.8, 0.4], [3.6, 0.2]], happy: [[2.6, 0], [3.0, 0.4], [3.6, 0.2]] },
};
