// knee_lift: ticklish - the knee jerks up and in, she leans over it with a
// squeak and a laugh, then puts her foot back down. Her right leg; the
// touch zones play knee_lift_left when it's her left leg you touched.
import { both } from './_pose.js';

const UP = { rightUpperLeg: [-1.05, 0, 0.18], rightLowerLeg: [1.45, 0, 0], rightFoot: [0.35, 0, 0],
             leftUpperLeg: [-0.06, 0, 0.03], leftLowerLeg: [0.1, 0, 0],
             ...both({ rightUpperArm: [0.15, 0.25, 1.05], rightLowerArm: [0, 0.6, 0] }) };

export default {
  about: "ticklish, giggly, startled by a touch",
  full: true,                     // her legs: only offered in full-body framing
  touch: ['legs'],                 // answers a touch on her legs...
  moods: ['neutral', 'warm'],      // ...in these moods
  left: true,
  dur: 1.9, fade: [0.12, 0.5],
  keys: [
    [0.00, { hips: [0, 0, 0], '+spine': [0, 0, 0], '+head': [0, 0, 0] }],
    [0.18, { ...UP, hips: [0.012, 0.02, 0], '+spine': [0.12, 0, 0.04], '+head': [0.1, 0, 0.06] }],
    [1.10, { ...UP, hips: [0.012, 0.015, 0], '+spine': [0.1, 0, 0.05], '+head': [0.08, 0.05, 0.1] }],
    [1.90, { hips: [0, 0, 0], '+spine': [0.02, 0, 0], '+head': [0.02, 0, 0.04] }],
  ],
  expr: { surprised: [[0, 0], [0.15, 0.8], [0.6, 0.2], [1.9, 0]],
          happy: [[0, 0], [0.4, 0.2], [0.8, 0.8], [1.9, 0.5]],
          blush: [[0, 0], [0.5, 0.5], [1.9, 0.3]] },
};
