// open_wide: Ryan's face from the pose studio (2026-10-27) - blushing, eyes half
// closed, mouth falling open and held there. Innocent on its face, not so much
// in the lewd row. Face only, no arms: a touch on her mouth answers with it in
// teasing, frisky and heated alike, mixed in with blow_kiss.
export default {
  dur: 4.0, fade: [0.6, 0.8],
  keys: [
    [0.0, { '+head': [-0.04, 0, 0.03] }],
    [1.6, { '+head': [-0.08, 0, 0.05] }],      // tips back a little as it opens
    [4.0, { '+head': [-0.05, 0, 0.04] }],
  ],
  expr: {
    blush: [[0, 0.2], [0.8, 0.35], [4.0, 0.35]],
    relaxed: [[0, 0.1], [0.8, 0.2], [4.0, 0.2]],
    blink: [[0, 0], [0.7, 0.5], [3.6, 0.5], [4.0, 0.2]],       // eyes half closed
    aa: [[0, 0], [0.9, 1.0], [3.4, 1.0], [4.0, 0]],
    ou: [[0, 0], [0.9, 0.7], [3.4, 0.7], [4.0, 0]],
  },
  about: "lewd, teasing: blushing, eyes half closed, mouth opened wide and held",
  private: true,
  lewd: true,
  touch: ['mouth'], moods: ['lewd'],
};
