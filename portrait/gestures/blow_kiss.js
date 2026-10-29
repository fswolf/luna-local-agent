// blow_kiss: fingers to her lips, eyes closed, then blown your way (then her open palm toward you, like the wave's)
import { fingers, open } from './_pose.js';

export default {
  keywords: ["blows a kiss", "blowing a kiss", "blows you a kiss", "😘"],   // in what she writes, *like this*
  about: "fond, affectionate, sending love, goodnight: fingers to her lips, then blows you a kiss",   // offered to her as [blow_kiss] in tags mode
  dur: 3.0, fade: [0.45, 0.6],
  keys: [
    [0.0, { rightUpperArm: [0, 1.2, 0.4], rightLowerArm: [0, 2.0, -0.55, -0.4], rightHand: [-0.4, 0, 0], ...fingers('right', 0.45),
            '+head': [0.06, -0.05, -0.06], '+spine': [0.03, 0, 0] }],
    [1.0, { rightUpperArm: [0, 1.2, 0.4], rightLowerArm: [0, 2.0, -0.55, -0.4], rightHand: [-0.4, 0, 0], ...fingers('right', 0.5),
            '+head': [0.08, -0.05, -0.08], '+spine': [0.04, 0, 0] }],
    [1.45, { rightUpperArm: [0, 1.0, 0.9], rightLowerArm: [0, -0.1, -2.3], rightHand: [-1.2, 0, -0.25], ...open('right'),
             '+head': [-0.04, -0.04, -0.1], '+spine': [0.07, 0, 0] }],
    [3.0, { rightUpperArm: [0, 1.0, 0.95], rightLowerArm: [0, -0.1, -2.25], rightHand: [-1.2, 0, -0.25], ...open('right'),
            '+head': [-0.02, -0.03, -0.12], '+spine': [0.05, 0, 0] }],
  ],
  expr: { blush: 0.85, blink: [[0, 0], [0.3, 1], [1.15, 1], [1.45, 0]], ou: [[0, 0], [0.3, 0.75], [1.05, 0.75], [1.3, 0]],
          happy: [[0, 0], [1.25, 0], [1.6, 0.6]] },
};
