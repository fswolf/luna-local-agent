// giggle: a little "hehe" - hand comes up to cover her mouth (fingers
// loosely curled, the back of her hand to you), shoulders bob in quick small
// hitches, eyes squeeze happy, head tips. Not a laugh: small and quick.
import { fingers } from './_pose.js';

// the shh arm, forearm twisted so the back of her hand faces you and the
// curled fingers sit over her lips (hand rolled ~180: palm to her lips)
const COVER = { rightUpperArm: [0, 1.15, 0.3], rightLowerArm: [0, 2.35, -0.3, 1.0], rightHand: [-2.74, 0.35, -0.6],
                ...fingers('right', 0.35) };
const HITCH = (t, d) => [t, { '+rightShoulder': [0, 0, -0.05 * d], '+leftShoulder': [0, 0, 0.05 * d],
                               '+upperChest': [-0.03 * d, 0, 0] }];

export default {
  keywords: ["giggle", "giggles", "hehe", "tee hee", "teehee", "titters"],
  about: "giggling, amused, tickled, a little embarrassed",
  touch: ['tummy'], moods: ['warm', 'loving', 'lewd'],
  dur: 2.4, fade: [0.3, 0.55],
  keys: [
    [0.0, { ...COVER, '+head': [0.06, -0.08, 0.12], '+spine': [0.03, 0, 0.02] }],
    // the giggle itself: quick little hitches, fading out
    HITCH(0.35, 1), HITCH(0.5, -0.3), HITCH(0.65, 1), HITCH(0.8, -0.3),
    HITCH(0.95, 0.8), HITCH(1.1, -0.2), HITCH(1.28, 0.55), HITCH(1.45, 0), HITCH(1.7, 0.3), HITCH(1.9, 0),
    [2.4, { ...COVER, '+head': [0.04, -0.06, 0.08], '+spine': [0.02, 0, 0.01] }],
  ],
  expr: {
    happy: [[0, 0.2], [0.3, 0.85], [1.9, 0.8], [2.4, 0.4]],
    blush: [[0, 0.1], [0.5, 0.45], [2.4, 0.3]],
    blink: [[0, 0], [0.3, 0.55], [1.9, 0.55], [2.4, 0]],      // eyes squeezed into happy crescents
  },
};
