// shy: hands together at her chest, looking away, then a peek at you
import { both, fingers } from './_pose.js';

export default {
  keywords: ["bashful", "shyly", "looks away", "fidget"],   // in what she writes, *like this*
  about: "shy, flustered by a compliment, sweet on you: hands together at her chest, looks away shyly, then peeks back at you",   // offered to her as [shy] in tags mode
  private: true,      // never from stream chat
  dur: 4.2, fade: [0.6, 0.8],
  keys: [
    [0.0, { ...both({ rightUpperArm: [0, 0.8, 1.15], rightLowerArm: [0, 2.15, -0.15], rightHand: [0, 0.2, 0],
                      rightShoulder: [0, 0, -0.12] }), ...fingers('right', 0.45), ...fingers('left', 0.45),
            '+spine': [0.05, 0, 0.03], '+head': [0.2, 0.28, 0.12] }],
    [1.6, { '+spine': [0.06, 0, -0.03], '+head': [0.22, 0.3, 0.14] }],
    [2.2, { '+spine': [0.05, 0, 0], '+head': [0.12, 0.06, 0.08] }],       // a peek
    [2.9, { '+spine': [0.05, 0, 0.02], '+head': [0.12, 0.05, 0.08] }],
    [3.4, { '+spine': [0.06, 0, 0.03], '+head': [0.2, 0.26, 0.12] }],     // and away again
    [4.2, { '+spine': [0.05, 0, 0.0], '+head': [0.18, 0.24, 0.1] }],
  ],
  expr: { blush: 1, relaxed: 0.35 },
};
