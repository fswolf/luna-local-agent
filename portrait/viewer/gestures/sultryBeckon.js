// sultryBeckon: a come-hither curl of the fingers, other hand on her hip,
// weight on one leg, a sly smile. Ryan's first gesture, tidied up.
import { fingers } from './_pose.js';

// right hand out in front, palm up; the fingers curl in and out to beckon
const ARM = { rightUpperArm: [0, 1.1, 0.6], rightLowerArm: [0, 0.6, -0.5, -1.44], rightHand: [-0.96, 0, 0] };
// left hand on her hip, elbow out
const HIP = { leftUpperArm: [0, 0.3, -0.75], leftLowerArm: [0, -0.5, -1.3], leftHand: [0, -0.3, -0.6] };
// weight on one leg: hips shift to her right, upper body leans back the other way
const POP = { hips: [-0.025, 0, 0], '+spine': [0, 0, 0.06], '+chest': [0, 0, -0.03] };

export default {
  about: "sultry come-hither, teasing, inviting",
  private: true,
  dur: 3.4,
  fade: [0.45, 0.6],
  keys: [
    [0.0, { ...ARM, ...HIP, ...POP, ...fingers('right', 0.1), '+head': [0.05, -0.06, 0.08] }],
    [0.7, { ...fingers('right', 0.95), '+head': [0.08, -0.08, 0.12] }],   // curl
    [1.1, { ...fingers('right', 0.15) }],
    [1.6, { ...fingers('right', 0.95) }],                                 // and again
    [2.0, { ...fingers('right', 0.15), '+head': [0.06, -0.04, 0.1] }],
    [3.4, { ...ARM, ...HIP, ...POP, ...fingers('right', 0.3), '+head': [0.04, 0, 0.06] }],
  ],
  expr: { relaxed: 0.3, blush: 0.4,
          blinkRight: [[0, 0], [2.2, 0], [2.4, 1], [2.75, 1], [2.95, 0]] },   // and a wink to finish
};
