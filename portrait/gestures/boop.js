// boop: a poke on the nose. Her head bobs back, eyes squeeze shut, a little
// "hey!" mouth, then a happy, slightly flustered smile as she settles. Quick.
// Joins nose touches in the everyday moods, mixed in with what's there.
export default {
  dur: 1.8, fade: [0.1, 0.5],
  keys: [
    [0.0, { '+head': [0, 0, 0], '+neck': [0, 0, 0] }],
    [0.12, { '+head': [-0.14, 0, -0.03], '+neck': [-0.05, 0, 0] }],     // bobs back from the poke
    [0.5, { '+head': [0.03, 0.04, 0.07], '+neck': [0, 0, 0] }],
    [1.8, { '+head': [0.04, 0.05, 0.08], '+neck': [0, 0, 0] }],          // settles, head tipped
  ],
  expr: {
    blink: [[0, 0], [0.08, 1], [0.4, 1], [0.65, 0.15], [1.8, 0]],       // squeezed shut
    ou: [[0, 0], [0.1, 0.45], [0.4, 0.2], [0.6, 0]],                    // "hey!"
    happy: [[0, 0], [0.4, 0.6], [1.8, 0.35]],
    blush: [[0, 0], [0.3, 0.3], [1.8, 0.2]],
  },
  about: "booped on the nose: squeezes her eyes shut, 'hey!', then a happy flustered smile",
  keywords: ["boop", "boops"],
  touch: ['nose'], moods: ['neutral', 'warm', 'loving'],
};
