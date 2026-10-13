// wink: a playful wink with a little head tilt and a smile; the head tips
// towards the winking eye (her right), the way people do it
export default {
  keywords: ["wink", "😉"],   // in what she writes, *like this*
  about: "playful, teasing, a little flirty",
  dur: 1.6, fade: [0.25, 0.4],
  keys: [
    [0.0, { '+head': [0.02, 0, 0] }],
    [0.35, { '+head': [0.04, 0.06, 0.16] }],
    [1.1, { '+head': [0.04, 0.06, 0.17] }],
    [1.6, { '+head': [0.01, 0, 0.04] }],
  ],
  expr: { blinkRight: [[0, 0], [0.3, 1], [0.95, 1], [1.2, 0]], relaxed: [[0, 0], [0.3, 0.55], [1.6, 0.4]], blush: 0.25 },
};
