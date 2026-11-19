// plush_pickup: she picks up her moon-cat plush and hugs it to her chest
// (life/plushie.py). It appears at prop_at, and the hug is held (hold) until
// she puts it down.
import { HUG, REACH, REST } from './_plush.js';

export default {
  dur: 2.2, fade: [0.4, 0.5],
  prop: 'plush', prop_at: 0.8, hold: true,
  keys: [
    [0.0, REST],
    [0.8, { ...REACH, '+spine': [0.08, 0, 0], '+head': [0.12, 0, 0] }],
    [1.6, { ...HUG, '+spine': [0.05, 0, 0], '+head': [0.14, 0, 0.06] }],
    [2.2, { ...HUG, '+spine': [0.03, 0, 0], '+head': [0.12, 0, 0.05] }],
  ],
  expr: { relaxed: [[0, 0], [1.6, 0.5]], sad: [[0, 0.3], [2.2, 0.2]] },
};
