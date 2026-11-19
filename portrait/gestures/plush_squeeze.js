// plush_squeeze: a tighter hug, cheek down on its head, then back
// (life/plushie.py, now and then while she holds it).
import { HUG } from './_plush.js';

const TIGHT = { ...HUG, rightUpperArm: [0, 0.82, 1.0], leftUpperArm: [0, -0.82, -1.0] };
export default {
  dur: 3.0, fade: [0.4, 0.5],
  prop: 'plush',
  keys: [
    [0.0, { ...HUG, '+head': [0.12, 0, 0.05] }],
    [0.9, { ...TIGHT, '+spine': [0.06, 0, 0], '+head': [0.2, 0.05, 0.16] }],
    [2.1, { ...TIGHT, '+spine': [0.06, 0, 0.02], '+head': [0.2, 0.04, 0.18] }],
    [3.0, { ...HUG, '+head': [0.12, 0, 0.05] }],
  ],
  expr: { blink: [[0, 0], [0.8, 1], [2.2, 1], [2.6, 0]], relaxed: [[0, 0.4], [1, 0.7], [3, 0.4]] },
};
