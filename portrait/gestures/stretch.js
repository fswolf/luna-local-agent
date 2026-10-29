// stretch
import { both } from './_pose.js';

export default {
  keywords: ["stretch", "yawn"],   // in what she writes, *like this*
  about: "tired, sleepy, just woke up: arms up over her head in a big stretch and a yawn",   // offered to her as [stretch] in tags mode
  idle: ['cool', 'neutral', 'warm', 'loving'],   // on her own, in these moods (studio: Details)
  dur: 4.2, fade: [0.8, 0.9],
  keys: [
    [0.0, { ...both({ rightUpperArm: [0, 0.1, -1.35], rightLowerArm: [0, 0.6, 0], rightHand: [0, 0.3, 0] }),
            '+spine': [-0.07, 0, 0], '+head': [-0.18, 0, 0] }],
    [1.6, { ...both({ rightUpperArm: [0, 0.05, -1.45], rightLowerArm: [0, 0.3, 0], rightHand: [0, 0.3, 0] }),
            '+spine': [-0.1, 0, 0.06], '+head': [-0.2, 0, 0.08] }],
    [3.0, { ...both({ rightUpperArm: [0, 0.05, -1.45], rightLowerArm: [0, 0.3, 0], rightHand: [0, 0.3, 0] }),
            '+spine': [-0.1, 0, -0.06], '+head': [-0.2, 0, -0.08] }],
    [4.2, { ...both({ rightUpperArm: [0, 0.1, -1.3], rightLowerArm: [0, 0.6, 0], rightHand: [0, 0.3, 0] }),
            '+spine': [-0.05, 0, 0], '+head': [-0.1, 0, 0] }],
  ],
  expr: { relaxed: 0.6, blink: [[0, 0], [0.5, 1], [3.4, 1], [3.9, 0]], aa: [[0, 0], [0.8, 0.55], [2.0, 0.6], [2.6, 0]] },
};
