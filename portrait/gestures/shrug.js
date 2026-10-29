// shrug
import { both, open } from './_pose.js';

export default {
  keywords: ["shrug", "🤷"],   // in what she writes, *like this*
  about: "unsure, don't know, oh well, whatever: a shrug with open hands",   // offered to her as [shrug] in tags mode
  dur: 2.2, fade: [0.3, 0.45],
  keys: [[0, both({ rightUpperArm: [0, 0.3, 1.0], rightLowerArm: [0, 1.65, -0.75], rightHand: [-0.8, 0, 0], ...open('right'),
                    rightShoulder: [0, 0, -0.2] })],
         [2.2, both({ rightUpperArm: [0, 0.3, 1.0], rightLowerArm: [0, 1.65, -0.75], rightHand: [-0.8, 0, 0], ...open('right'),
                      rightShoulder: [0, 0, -0.2] })]],
  add: { '+head': [0.02, 0, 0.14] },
  expr: { relaxed: 0.3 },
};
