// nose_tease: a boop on the nose when she's in the mood. Chin dips, head
// tilts, eyes stay on you (her gaze keeps tracking you as the head goes
// down, so they look up), lips part, blush rises, and she holds it - with a
// little drool from the corner of her mouth. Then she lets it go.
export default {
  about: "lewd, teasing: looks up at you, lips parted, blushing",
  private: true,      // never from stream chat
  lewd: true,         // held back on a stream where lewd is off (twitch/youtube "lewd": false)
  touch: ['nose'], moods: ['lewd'],
  dur: 4.2, fade: [0.5, 0.8],
  keys: [
    [0.0, { '+head': [0, 0, 0], '+spine': [0, 0, 0] }],
    [0.6, { '+head': [0.26, -0.04, 0.12], '+neck': [0.06, 0, 0.03], '+spine': [0.06, 0, 0.02] }],
    [2.8, { '+head': [0.28, -0.05, 0.14], '+neck': [0.06, 0, 0.04], '+spine': [0.07, 0, 0.02] }],
    [4.2, { '+head': [0.04, 0, 0.02], '+spine': [0.01, 0, 0] }],
  ],
  expr: {
    blush:   [[0, 0.2], [0.6, 0.85], [2.8, 1], [4.2, 0.6]],
    aa:      [[0, 0], [0.5, 0], [0.9, 0.6], [2.8, 0.62], [3.4, 0.05]],
    relaxed: [[0, 0], [0.7, 0.35], [2.8, 0.4], [4.2, 0.1]],
    drool:   [[0, 0], [1.0, 0], [2.0, 1], [3.0, 1], [4.2, 0]],
  },
};
