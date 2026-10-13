// explain: a hand that comes up while she talks
import { fingers } from './_pose.js';

export default {
  left: true,         // also a left-handed version, explain_left
  dur: 2.4, fade: [0.5, 0.6],
  keys: [[0, { rightUpperArm: [0, 0.3, 1.05], rightLowerArm: [0, 1.2, 0], rightHand: [-0.9, 0, 0.15], ...fingers('right', 0.1) }],
         [1.2, { rightUpperArm: [0, 0.35, 1.0], rightLowerArm: [0, 1.3, 0], rightHand: [-1.1, 0, 0.1], ...fingers('right', 0.1) }],
         [2.4, { rightUpperArm: [0, 0.3, 1.05], rightLowerArm: [0, 1.2, 0], rightHand: [-0.9, 0, 0.15], ...fingers('right', 0.15) }]],
};
