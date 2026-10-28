// say_ah: open_wide's tame sister (Ryan, 2026-10-27) - touch her mouth and she
// just opens it, "aah", like at the dentist. Same mouth, nothing else: no blush,
// no eyes. Answers a mouth touch in the everyday moods, mixed in with what's there.
export default {
  dur: 2.8, fade: [0.4, 0.6],
  keys: [[0.0, { '+head': [-0.03, 0, 0] }], [2.8, { '+head': [-0.03, 0, 0] }]],
  expr: {
    aa: [[0, 0], [0.6, 1.0], [2.2, 1.0], [2.8, 0]],
    ou: [[0, 0], [0.6, 0.7], [2.2, 0.7], [2.8, 0]],
  },
  about: "opens her mouth wide, 'aah', like at the dentist; playful, a bit silly",
  touch: ['mouth'], moods: ['neutral', 'warm', 'loving'],
};
