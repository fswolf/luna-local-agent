// arch_stretch: hands go up behind her head, elbows out, and she arches her
// back - chest out, chin up, eyes closed - leans a little each way, sighs,
// and lets go. An idle: she does it on her own, any mood.
import { both } from './_pose.js';

const HANDS = both({ rightUpperArm: [0, -0.3, -1.1], rightLowerArm: [0, 0.7, -2.2] });   // hands behind her head
const ARCH = d => ({ '+spine': [-0.12, 0, d], '+chest': [-0.08, 0, 0], '+head': [-0.08, 0, -d] });

export default {
  keywords: ["arches her back", "hands behind her head", "stretches out"],
  about: "relaxed, stretching, arching her back with her hands behind her head",
  idle: true,         // one of the things she does on her own
  dur: 5.0, fade: [0.9, 1.0],
  keys: [
    [0.0, { ...HANDS, ...ARCH(0) }],
    [1.6, { ...ARCH(0.06), '+spine': [-0.16, 0, 0.06] }],      // deeper, leaning one way
    [2.8, { ...ARCH(-0.06), '+spine': [-0.16, 0, -0.06] }],    // and the other
    [3.8, { ...ARCH(0) }],
    [5.0, { ...HANDS, ...ARCH(0) }],
  ],
  expr: {
    relaxed: [[0, 0.2], [1.0, 0.6], [3.8, 0.6], [5.0, 0.2]],
    blink:   [[0, 0], [0.8, 1], [3.6, 1], [4.1, 0]],
    ou:      [[0, 0], [3.4, 0], [3.7, 0.35], [4.2, 0]],        // a contented sigh as she lets go
  },
};
