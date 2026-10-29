// jump
import { both, open, REST } from './_pose.js';

export default {
  keywords: ["jump", "leap"],   // in what she writes, *like this*
  about: "big excitement, great news, thrilled: jumps for joy",   // offered to her as [jump] in tags mode
  dur: 1.35, fade: [0.12, 0.3],
  keys: [
    [0.00, { ...REST }],
    [0.22, { ...both({ rightUpperArm: [0, -0.35, 1.3], rightLowerArm: [0, 0.3, 0] }),
             ...both({ rightUpperLeg: [-0.55, 0, 0], rightLowerLeg: [1.05, 0, 0], rightFoot: [-0.5, 0, 0] }),
             '+spine': [0.12, 0, 0], hips: [0, -0.09, 0] }],
    [0.42, { ...both({ rightUpperArm: [0, 0.2, -0.7], rightLowerArm: [0, 0.2, -0.2], ...open('right') }),
             ...both({ rightUpperLeg: [0.05, 0, 0], rightLowerLeg: [0.1, 0, 0], rightFoot: [0.3, 0, 0] }),
             '+spine': [-0.06, 0, 0], '+head': [-0.1, 0, 0], hips: [0, 0.16, 0] }],
    [0.62, { ...both({ rightUpperArm: [0, 0.2, -0.4], rightLowerArm: [0, 0.2, -0.3] }),
             ...both({ rightUpperLeg: [-0.25, 0, 0], rightLowerLeg: [0.4, 0, 0], rightFoot: [0, 0, 0] }),
             hips: [0, 0.11, 0] }],
    [0.80, { ...both({ rightUpperArm: [0, 0, 0.9], rightLowerArm: [0, 0.4, 0] }),
             ...both({ rightUpperLeg: [-0.5, 0, 0], rightLowerLeg: [0.9, 0, 0], rightFoot: [-0.4, 0, 0] }),
             '+spine': [0.1, 0, 0], hips: [0, -0.07, 0] }],
    [1.35, { ...REST, hips: [0, 0, 0] }],
  ],
  expr: { happy: 0.9, surprised: [[0, 0], [0.35, 0.5], [0.8, 0]] },
};
