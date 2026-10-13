// pant: out of breath - bent over, hands on her knees, chest heaving and
// mouth open; then she straightens up, a hand on her chest, gets her
// breath back with one long sigh and a smile.
import { both, fingers, open } from './_pose.js';

const DUR = 7.5;

// bent over: knees soft, hips back, hands braced just above the knees
const BENT = {
  ...both({ rightUpperLeg: [-0.5, 0, 0], rightLowerLeg: [0.8, 0, 0], rightFoot: [-0.3, 0, 0] }),
  ...both({ rightUpperArm: [-0.4, 0, 1.38], rightLowerArm: [0, 0.3, 0], rightHand: [0.2, 0, 0.15] }),
  ...open('right'), ...open('left'),
  hips: [0, -0.1, -0.06], '+spine': [0.6, 0, 0], '+chest': [0.3, 0, 0], '+neck': [-0.25, 0, 0], '+head': [-0.5, 0, 0],
};
// upright again: right hand flat on her chest, left on her hip
const UP = {
  ...both({ rightUpperLeg: [-0.05, 0, 0], rightLowerLeg: [0.1, 0, 0], rightFoot: [-0.05, 0, 0] }),
  rightUpperArm: [0, 0.8, 1.15], rightLowerArm: [0, 2.2, -0.1], rightHand: [0, 0.3, 0], ...open('right'),
  leftUpperArm: [0, 0.3, -0.75], leftLowerArm: [0, -0.5, -1.3], leftHand: [0, -0.3, -0.6],
  hips: [0, 0, 0], '+spine': [0.05, 0, 0], '+chest': [0, 0, 0], '+neck': [0, 0, 0], '+head': [-0.05, 0, 0.06],
};

// the breaths: quick and deep while bent over, slowing once she's up
const keys = [[0, BENT]];
const mouth = [[0, 0.35]];
let t = 0.25;
while (t < 5.6) {
  const rate = t < 3.2 ? 0.4 : 0.4 + (t - 3.2) * 0.12;   // seconds per breath
  const deep = t < 3.2 ? 1 : 0.7;
  keys.push([t, { '+upperChest': [-0.06 * deep, 0, 0], '+rightShoulder': [0, 0, -0.07 * deep], '+leftShoulder': [0, 0, 0.07 * deep] }]);
  mouth.push([t, 0.55 * deep]);
  keys.push([t + rate * 0.45, { '+upperChest': [0.03, 0, 0], '+rightShoulder': [0, 0, 0.01], '+leftShoulder': [0, 0, -0.01] }]);
  mouth.push([t + rate * 0.45, 0.3 * deep]);
  t += rate;
}
keys.push([2.8, BENT]);
keys.push([3.8, UP]);
// the long sigh: chest rises, shoulders drop, then the smile
keys.push([5.9, { '+upperChest': [-0.09, 0, 0], '+rightShoulder': [0, 0, -0.1], '+leftShoulder': [0, 0, 0.1], '+head': [-0.12, 0, 0.04] }]);
keys.push([6.8, { '+upperChest': [0.04, 0, 0], '+rightShoulder': [0, 0, 0.04], '+leftShoulder': [0, 0, -0.04], '+head': [0.04, 0, 0.08] }]);
keys.push([DUR, { ...UP, '+upperChest': [0, 0, 0], '+rightShoulder': [0, 0, 0], '+leftShoulder': [0, 0, 0] }]);
keys.sort((a, b) => a[0] - b[0]);
mouth.push([5.9, 0.45], [6.8, 0.05], [DUR, 0]);
mouth.sort((a, b) => a[0] - b[0]);

export default {
  about: "out of breath, exhausted, worn out after effort",
  keywords: ["pant", "out of breath", "catches her breath", "catching her breath", "huff", "wheez", "😮‍💨"],
  dur: DUR, fade: [0.6, 0.9],
  keys,
  expr: { aa: mouth, blush: [[0, 0.6], [5, 0.5], [DUR, 0.2]], happy: [[0, 0], [6.2, 0], [7, 0.6]],
          blink: [[0, 0.3], [3.6, 0.3], [4, 0], [DUR, 0]] },
};
