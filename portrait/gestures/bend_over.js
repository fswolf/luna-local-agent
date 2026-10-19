// bend_over: turned away from you, she bends straight over from the hips,
// hands on her backside, tail lifted and held up, head up looking ahead,
// blushing. Holds still - just breathing - then straightens up.
// Lewd; full body only. (bend_forward is the tame version.)
import { both } from './_pose.js';

const TURN = 2.2;       // radians: back to you
const BENT = {
  '+hips': [0, TURN, 0],
  '+spine': [1.0, 0, 0], '+chest': [0.55, 0, 0], '+upperChest': [0.25, 0, 0],   // a straight bend, no twist
  '+neck': [-0.3, 0, 0], '+head': [-0.45, 0, 0],      // head up, looking straight ahead
  // hands on her backside (solved in the viewer: each hand to her cheek)
  ...both({ rightUpperArm: [-0.99, 1.35, 1.92], rightLowerArm: [-0.06, 0, 0] }),
  rightUpperLeg: [0, 0, -0.08], leftUpperLeg: [0, 0, 0.08],
};
const BREATHE = d => ({ '+upperChest': [0.25 + d, 0, 0] });

export default {
  keywords: ["bends over", "bends right over", "bends over for you", "sticks her butt out", "presents herself"],
  about: "lewd, teasing: bends right over with her back to you, hands on her backside",
  private: true,      // never from stream chat
  lewd: true,         // held back on a stream where lewd is off (twitch/youtube "lewd": false)
  full: true,         // full body only
  tail_up: 0.9,       // tail lifted out of the way and held still
  touch: ['butt', 'back'], moods: ['lewd'],
  dur: 9.0, fade: [1.3, 1.4],
  keys: [
    [0.0, BENT],
    [2.6, BREATHE(0.03)], [4.2, BREATHE(-0.01)], [5.8, BREATHE(0.03)], [7.4, BREATHE(0)],
    [9.0, BENT],
  ],
  expr: {
    blush:   [[0, 0.5], [1.0, 1], [7.6, 1], [9, 0.6]],
    relaxed: [[0, 0], [1.3, 0.45], [7.6, 0.45], [9, 0.1]],
    happy:   [[0, 0], [1.5, 0.25], [7.6, 0.25], [9, 0.1]],
  },
};
