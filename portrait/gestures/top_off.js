// top_off: pulls her top off over her head. Hands to the hem, up past her
// chest, over her face (the top and the tie with it come off there:
// clothes), arms up and out, then down with a little shake of her hair.
// A rough first pass, to refine in the pose studio. No about or keywords:
// it plays when her clothes come off (portrait.js undress).
import { both, fingers, REST } from './_pose.js';

const GRIP = { ...fingers('right', 0.8), ...fingers('left', 0.8) };
const arms = p => ({ ...both(p), ...GRIP });

export default {
  private: true,
  dur: 4.4, fade: [0.5, 0.8],
  keys: [
    [0.6, { ...arms({ rightUpperArm: [0.3, 0.75, 1.05], rightLowerArm: [0, 1.5, 0, -0.8], rightHand: [0, 0, 0.3] }),
            '+spine': [0.08, 0, 0], '+head': [0.15, 0, 0] }],
    [1.3, { ...arms({ rightUpperArm: [0.3, 0.9, 0.35], rightLowerArm: [0, 1.9, 0, -0.8], rightHand: [0, 0, 0.3] }),
            '+spine': [0, 0, 0], '+head': [0.2, 0, 0] }],
    [2.0, { ...arms({ rightUpperArm: [0, 0.45, -0.7], rightLowerArm: [0, 1.5, 0], rightHand: [0, 0.2, 0] }),
            '+spine': [-0.04, 0, 0], '+head': [0.3, 0, 0] }],
    [2.6, { ...arms({ rightUpperArm: [0, 0.1, -1.1], rightLowerArm: [0, 0.6, 0], rightHand: [0, 0.2, 0] }),
            '+spine': [-0.06, 0, 0], '+head': [-0.1, 0, 0] }],
    [3.3, { ...REST, '+head': [0.05, 0.12, 0.1] }],
    [3.7, { '+head': [0.05, -0.12, -0.1] }],
    [4.4, { ...REST, '+head': [0, 0, 0] }],
  ],
  clothes: [{ at: 2.05, off: ['tie', 'top'] }],     // the tie sits on its collar: it goes with it
  expr: { relaxed: [[0, 0], [1.0, 0.3], [4.4, 0.2]], blush: [[2.4, 0], [3.0, 0.5], [4.4, 0.4]] },
};
