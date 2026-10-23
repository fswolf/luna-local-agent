// tuck_hair
import { fingers } from './_pose.js';

export default {
  keywords: ["tucks her hair", "tucks a strand", "brushes her hair"],   // in what she writes, *like this*
  idle: ['cool', 'neutral', 'warm', 'loving', 'lewd'],   // on her own, in these moods (studio: Details)
  left: true,         // also a left-handed version, tuck_hair_left
  dur: 2.6, fade: [0.55, 0.6],
  keys: [
    [0.0, { rightUpperArm: [0, 0.7, 0.5], rightLowerArm: [0, 0, -2.55, -1.0], rightHand: [-1.1, 0.3, 0], ...fingers('right', 0.15),
            '+head': [0, -0.1, -0.14] }],
    [1.4, { rightUpperArm: [0, 0.7, 0.45], rightLowerArm: [0, 0, -2.65, -1.0], rightHand: [-1.2, 0.45, 0], ...fingers('right', 0.15),
            '+head': [0, -0.12, -0.18] }],
    [2.6, { rightUpperArm: [0, 0.68, 0.55], rightLowerArm: [0, 0, -2.45, -1.0], rightHand: [-1.1, 0.3, 0], ...fingers('right', 0.15),
            '+head': [0, -0.08, -0.1] }],
  ],
  expr: { relaxed: 0.4 },
};
