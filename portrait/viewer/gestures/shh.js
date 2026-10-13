// shh: finger to her lips, a sly little smile
import { fingers } from './_pose.js';

// index finger up and straight, the rest curled in
const SHH_HAND = { ...fingers('right', 0.9), rightIndexProximal: [0, 0, 0], rightIndexIntermediate: [0, 0, 0],
                   rightIndexDistal: [0, 0, 0], rightThumbProximal: [0, 0.4, 0.3], rightThumbDistal: [0, 0.5, 0] };
const SHH = { rightUpperArm: [0, 1.1, 0.4], rightLowerArm: [0, 2.2, -0.3, 0.18], rightHand: [0.12, -0.3, -1.0], ...SHH_HAND };

export default {
  keywords: ["shh", "finger to her lips", "finger to my lips", "🤫"],   // in what she writes, *like this*
  about: "a secret, mischief, being sly",
  dur: 2.8, fade: [0.45, 0.6],
  keys: [
    [0.0, { ...SHH, '+head': [0.06, -0.06, 0.1] }],
    [1.4, { ...SHH, '+head': [0.08, -0.08, 0.12] }],
    [2.8, { ...SHH, '+head': [0.06, -0.06, 0.1] }],
  ],
  expr: { relaxed: 0.3, ou: [[0, 0], [0.4, 0.35], [1.2, 0.35], [1.6, 0]] },   // 'shh' lips, then a sly smile
};
