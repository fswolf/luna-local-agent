// wave
import { open, R } from './_pose.js';

// rightHand x: the wrist turned so the palm faces whoever she's waving at
const WAVE_UP = R({ rightUpperArm: [0, 0.5, 0.75], rightLowerArm: [0, -0.2, -2.45], rightHand: [-1.2, 0, -0.1],
                    ...open('right'), '+head': [0, -0.08, -0.08], '+spine': [0, 0, -0.03] });

export default {
  keywords: ["wave", "waving", "👋"],   // in what she writes, *like this*
  about: "hello, goodbye, see you, welcome back: a friendly wave",   // offered to her as [wave] in tags mode
  left: true,         // also a left-handed version, wave_left
  dur: 2.6, fade: [0.35, 0.45],
  keys: [[0, WAVE_UP], [2.6, WAVE_UP]],
  osc: [['rightLowerArm', 2, 0.22, 2.3], ['rightHand', 1, 0.3, 2.3]],   // forearm sways, hand rocks in its own plane
  expr: { happy: 0.6 },
};
