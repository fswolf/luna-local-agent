// pat_hmph: a head pat she didn't ask for - chin up, head turned away from you,
// eyes shut, a small pout. Not angry, just "hmph". Cool and grudge moods.
const AWAY = { '+neck': [-0.04, -0.12, 0], '+head': [-0.1, -0.3, -0.06] };

export default {
  dur: 2.6, fade: [0.25, 0.7],
  keys: [
    [0.0, AWAY],
    [1.3, { '+neck': [-0.05, -0.14, 0], '+head': [-0.12, -0.34, -0.07] }],
    [2.6, AWAY],
  ],
  expr: {
    blink: [[0, 0], [0.25, 1], [2.1, 1], [2.6, 0]],
    angry: [[0, 0], [0.3, 0.3], [2.6, 0.2]],
    ou: [[0, 0], [0.3, 0.25], [2.2, 0.25], [2.6, 0]],         // the pout
  },
  about: "hmph: chin up, turns her head away from a pat she didn't want, a small pout",
  touch: ['head'], moods: ['cool', 'grudge'],
};
