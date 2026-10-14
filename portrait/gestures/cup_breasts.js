// cup_breasts: hands laid flat on each side of her chest (same placement as
// hands_on_chest.js), holding the pose with a soft breath, blush, and
// panting borrowed from pant.js.
import { both, open } from './_pose.js';

// Hands flat on her chest, elbows out so the forearms clear her — lifted
// directly from hands_on_chest.js.
const HANDS = {
  ...both({ rightUpperArm: [0.2, 0.4, 0.8], rightLowerArm: [0, 2, 0, -1.35], rightHand: [0, 0.4, 1.0] }),
  ...open('right'), ...open('left'),
};

// Panting: the same shoulder / upperChest hitcher from pant.js, lighter so it
// reads as breathless rather than exhausted. Slow down mid-way so it feels
// like she's settling rather than running out of air.
const DUR = 8.5;
const PANT_KEYS = [];
const PANT_MOUTH = [[0, 0.15]];
let t = 0.4;
while (t < 7.8) {
  const rate = t < 4.0 ? 0.6 : 0.85;   // seconds per breath, slows over time
  const deep = t < 4.0 ? 1 : 0.7;
  PANT_KEYS.push([t, {
    '+upperChest': [-0.05 * deep, 0, 0],
    '+rightShoulder': [0, 0, -0.055 * deep],
    '+leftShoulder': [0, 0, 0.055 * deep],
  }]);
  PANT_MOUTH.push([t, 0.4 * deep]);
  PANT_KEYS.push([t + rate * 0.45, {
    '+upperChest': [0.025, 0, 0],
    '+rightShoulder': [0, 0, 0.01],
    '+leftShoulder': [0, 0, -0.01],
  }]);
  PANT_MOUTH.push([t + rate * 0.45, 0.25 * deep]);
  t += rate;
}
PANT_MOUTH.push([7.8, 0.12], [DUR, 0.04]);

const keys = [
  [0.0, {
    ...HANDS,
    '+spine': [0.03, 0, 0],
    '+chest': [0.02, 0, 0],
    '+head': [0.05, 0, 0],
  }],
  [1.6, {
    ...HANDS,
    '+spine': [0.05, 0, 0],
    '+chest': [0.04, 0, 0],
    '+head': [0.1, 0.06, 0.08],       // breath in, head tips away
  }],
  [3.0, {
    '+spine': [0.03, 0, 0],
    '+chest': [0.02, 0, 0],
    '+head': [0.08, 0.05, 0.07],
  }],
  [5.5, {
    ...HANDS,
    '+spine': [0.05, 0, -0.01],
    '+chest': [0.04, 0, 0],
    '+head': [0.09, 0.03, 0.06],
  }],
  [7.2, {
    '+spine': [0.04, 0, 0],
    '+chest': [0.03, 0, 0],
    '+head': [0.08, 0.02, 0.05],
  }],
  [DUR, {
    ...HANDS,
    '+spine': [0.03, 0, 0],
    '+chest': [0.02, 0, 0],
    '+head': [0.05, 0, 0.02],
  }],
  // Panting overlays on top of the pose keys.
  ...PANT_KEYS,
];
keys.sort((a, b) => a[0] - b[0]);

export default {
  keywords: [
    "cups her breasts", "cups her chest", "hands on her breasts",
    "holds her breasts", "squeezes her breasts", "grabs her breasts",
    "hands under her breasts", "cups them", "holds them up",
    "presents her chest", "pushes them together",
  ],
  about: "lewd, teasing, hands flat on her chest, blush, panting",
  private: false,
  dur: DUR, fade: [0.6, 0.8],
  keys,
  expr: {
    blush:  [[0, 0], [1.2, 0.8], [2.0, 0.95], [7.0, 0.9], [DUR, 0.5]],
    relaxed:[[0, 0.15], [1.6, 0.55], [7.2, 0.5], [DUR, 0.25]],
    happy:  [[0, 0], [1.8, 0.3], [6.5, 0.28], [DUR, 0.12]],
    aa:     PANT_MOUTH,
  },
};