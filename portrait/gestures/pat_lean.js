// pat_lean: a head pat she likes - she tips her head up into your hand, eyes
// closed, a content little smile, and holds it there a moment before settling.
// Joins head touches in the everyday moods.
const INTO = { '+spine': [-0.02, 0, 0], '+neck': [-0.04, 0, 0.05], '+head': [-0.1, 0.04, 0.14] };

export default {
  dur: 3.2, fade: [0.5, 0.8],
  keys: [
    [0.0, INTO],
    [1.6, { '+spine': [-0.03, 0, 0], '+neck': [-0.05, 0, 0.06], '+head': [-0.12, 0.05, 0.16] }],   // presses up a bit more
    [3.2, INTO],
  ],
  expr: {
    blink: [[0, 0], [0.4, 1], [2.7, 1], [3.2, 0.2]],          // eyes closed into it
    happy: [[0, 0.1], [0.5, 0.55], [3.2, 0.45]],
    relaxed: [[0, 0], [0.6, 0.3], [3.2, 0.25]],
    blush: [[0, 0], [0.8, 0.25], [3.2, 0.2]],
  },
  about: "enjoying a head pat: tips her head up into your hand, eyes closed, content",
  touch: ['head'], moods: ['neutral', 'warm', 'loving'],
};
