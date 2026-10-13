// bounce: a happy little double bob
import { both } from './_pose.js';

export default {
  keywords: ["bounc", "hops", "hopping", "wiggle"],   // in what she writes, *like this*
  about: "happy, playful",   // offered to her as [bounce] in tags mode
  idle: true,         // one of the things she does on her own
  dur: 1.3, fade: [0.15, 0.3],
  keys: [
    [0.00, { hips: [0, 0, 0], ...both({ rightUpperLeg: [0, 0, 0], rightLowerLeg: [0, 0, 0] }) }],
    [0.18, { hips: [0, -0.035, 0], ...both({ rightUpperLeg: [-0.25, 0, 0], rightLowerLeg: [0.45, 0, 0], rightFoot: [-0.2, 0, 0] }) }],
    [0.38, { hips: [0, 0.03, 0], ...both({ rightUpperLeg: [0, 0, 0], rightLowerLeg: [0, 0, 0], rightFoot: [0, 0, 0] }) }],
    [0.58, { hips: [0, -0.035, 0], ...both({ rightUpperLeg: [-0.25, 0, 0], rightLowerLeg: [0.45, 0, 0], rightFoot: [-0.2, 0, 0] }) }],
    [0.80, { hips: [0, 0.025, 0], ...both({ rightUpperLeg: [0, 0, 0], rightLowerLeg: [0, 0, 0], rightFoot: [0, 0, 0] }) }],
    [1.30, { hips: [0, 0, 0] }],
  ],
  add: { '+head': [0, 0, 0.08] },
  expr: { happy: 0.75 },
};
