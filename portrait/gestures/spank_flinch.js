// spank_flinch: a quick jolt when she's spanked - hips jump forward, back
// arches, shoulders snap up, a gasp and a blush, tail flicks. Short, so it
// can play on every spank. Played by the portrait's spank handling (her top
// two mood rows, a click on her bum), not picked from touch.json.
export default {
  about: "flinching from a spank, surprised and flustered",
  private: true,      // never from stream chat
  lewd: true,         // held back on a stream where lewd is off
  wag: 1,             // a tail flick
  dur: 0.9, fade: [0.04, 0.3],
  keys: [
    [0.0, {}],
    [0.07, { hips: [0, 0.012, 0.03], '+spine': [-0.12, 0, 0], '+chest': [-0.05, 0, 0], '+head': [-0.14, 0, 0.04],
             '+rightShoulder': [0, 0, -0.13], '+leftShoulder': [0, 0, 0.13] }],
    [0.35, { hips: [0, 0.004, 0.012], '+spine': [-0.05, 0, 0], '+chest': [-0.02, 0, 0], '+head': [-0.06, 0, 0.03],
             '+rightShoulder': [0, 0, -0.05], '+leftShoulder': [0, 0, 0.05] }],
    [0.9, { hips: [0, 0, 0], '+spine': [0, 0, 0], '+chest': [0, 0, 0], '+head': [0, 0, 0],
            '+rightShoulder': [0, 0, 0], '+leftShoulder': [0, 0, 0] }],
  ],
  expr: {
    surprised: [[0, 0], [0.07, 0.8], [0.5, 0.2], [0.9, 0]],
    blush:     [[0, 0.4], [0.1, 0.95], [0.9, 0.7]],
    aa:        [[0, 0], [0.08, 0.5], [0.35, 0]],       // the gasp
  },
};
