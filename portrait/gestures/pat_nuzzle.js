// pat_nuzzle: a head pat when she's very fond of you - she nuzzles up into your
// hand, rubbing her head side to side against it like a cat, eyes closed,
// blushing and happy. Joins head touches when she's very warm or in the lewd row.
const N = (t, d) => [t, { '+spine': [-0.02, 0, 0], '+neck': [-0.05, 0.05 * d, 0.04 * d], '+head': [-0.11, 0.08 * d, 0.12 * d] }];

export default {
  dur: 3.4, fade: [0.45, 0.8],
  keys: [N(0.0, 0.3), N(0.5, 1), N(1.0, -0.6), N(1.5, 1), N(2.0, -0.6), N(2.5, 0.8), N(3.4, 0.3)],
  expr: {
    blink: [[0, 0], [0.35, 1], [3.0, 1], [3.4, 0.2]],
    happy: [[0, 0.2], [0.4, 0.7], [3.4, 0.5]],
    blush: [[0, 0.2], [0.6, 0.55], [3.4, 0.45]],
  },
  about: "nuzzling into a head pat like a cat, eyes closed, blushing and happy",
  touch: ['head'], moods: ['loving', 'lewd'],
};
