// plush_putdown: she sets her plush down, feeling better (life/plushie.py).
import { HUG, REACH, REST } from './_plush.js';

export default {
  dur: 2.0, fade: [0.3, 0.5],
  prop: 'plush', prop_at: 1.1,
  keys: [
    [0.0, HUG],
    [1.1, { ...REACH, '+spine': [0.08, 0, 0], '+head': [0.1, 0, 0] }],
    [2.0, REST],
  ],
  expr: { happy: [[0, 0], [2.0, 0.3]] },
};
