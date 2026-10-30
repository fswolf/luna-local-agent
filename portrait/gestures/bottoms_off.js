// bottoms_off: thumbs in the waistband, bends and pushes her shorts or skirt
// down to her knees (they come off there: clothes), steps out of them one
// foot then the other, and straightens up. A rough first pass, to refine in
// the pose studio. No about or keywords: it plays when her clothes come off
// (portrait.js undress). Her legs: full body framing reads best.
import { both, fingers, REST } from './_pose.js';

const HOOK = { ...fingers('right', 0.6), ...fingers('left', 0.6) };
const LEGS = (u, l) => ({ rightUpperLeg: [-u, 0, 0], leftUpperLeg: [-u, 0, 0], rightLowerLeg: [l, 0, 0], leftLowerLeg: [l, 0, 0] });
const STRAIGHT = { ...LEGS(0, 0), rightFoot: [0, 0, 0], leftFoot: [0, 0, 0] };

export default {
  private: true,
  dur: 5.0, fade: [0.5, 0.8],
  keys: [
    [0.6, { ...both({ rightUpperArm: [0, 0.0, 1.25], rightLowerArm: [0, 0.6, 0, -0.6], rightHand: [0, 0.3, 0.3] }), ...HOOK,
            '+spine': [0, 0, 0], '+chest': [0, 0, 0], '+head': [0.12, 0, 0], ...STRAIGHT, hips: [0, 0, 0] }],
    [1.4, { ...both({ rightUpperArm: [-0.6, 0.1, 1.2], rightLowerArm: [0, 0.2, 0, -0.6], rightHand: [0, 0.1, 0.2] }), ...HOOK,
            '+spine': [0.45, 0, 0], '+chest': [0.15, 0, 0], '+head': [-0.15, 0, 0], ...LEGS(0.25, 0.35) }],
    [2.2, { ...both({ rightUpperArm: [-1.1, 0.1, 1.2], rightLowerArm: [0, 0.1, 0, -0.6], rightHand: [0, 0.1, 0.2] }), ...HOOK,
            '+spine': [0.8, 0, 0], '+chest': [0.2, 0, 0], '+head': [-0.35, 0, 0], ...LEGS(0.35, 0.5), hips: [0, -0.04, -0.03] }],
    [3.0, { ...both({ rightUpperArm: [-0.3, 0.1, 1.15], rightLowerArm: [0, 0.4, 0] }),
            '+spine': [0.25, 0, 0], '+chest': [0.05, 0, 0], '+head': [-0.05, 0, 0], hips: [0, 0, 0],
            rightUpperLeg: [-1.0, 0, 0.08], rightLowerLeg: [1.4, 0, 0], rightFoot: [0.35, 0, 0], leftUpperLeg: [0, 0, 0], leftLowerLeg: [0, 0, 0] }],
    [3.5, { ...STRAIGHT, '+spine': [0.2, 0, 0] }],
    [4.0, { leftUpperLeg: [-1.0, 0, -0.08], leftLowerLeg: [1.4, 0, 0], leftFoot: [0.35, 0, 0], rightUpperLeg: [0, 0, 0], rightLowerLeg: [0, 0, 0],
            '+spine': [0.2, 0, 0] }],
    [4.5, { ...REST, ...STRAIGHT, '+spine': [0.05, 0, 0], '+head': [0, 0, 0] }],
    [5.0, { ...REST, ...STRAIGHT, '+spine': [0, 0, 0], '+chest': [0, 0, 0] }],
  ],
  clothes: [{ at: 2.3, off: ['bottoms'] }],
  expr: { relaxed: [[0, 0], [1.0, 0.3], [5.0, 0.2]], blush: [[2.0, 0], [2.8, 0.4], [5.0, 0.3]] },
};
