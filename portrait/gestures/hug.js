// hug: arms open, then around you: leaning in, head on your shoulder, a slow sway
import { both, fingers, open } from './_pose.js';

// open wide, palms forward; then around you, palms on your back
const HUG_OPEN = both({ rightUpperArm: [0, 0.45, 0.35], rightLowerArm: [0, 0.4, -0.15], rightHand: [0, 0, 0], ...open('right') });
// arms rounded around you, palms in toward your back
const HUG_HOLD = both({ rightUpperArm: [0, 1.0, 0.1], rightLowerArm: [0, 1.1, -0.4, -0.72], rightHand: [-0.48, 0, 0], ...fingers('right', 0.15) });
const HUG_LET_GO = both({ rightUpperArm: [0, 0.6, 0.6], rightLowerArm: [0, 0.6, -0.1, 0.3], rightHand: [0.2, 0, 0], ...fingers('right', 0.15) });


export default {
  keywords: ["hug", "cuddle", "squeez", "embrace", "🤗"],   // in what she writes, *like this*
  about: "affectionate, comforting, glad you're here, missing you: arms open, then wraps you in a hug, head on your shoulder",   // offered to her as [hug] in tags mode
  dur: 4.6, fade: [0.4, 0.6],
  keys: [
    [0.0, { ...HUG_OPEN, '+spine': [-0.03, 0, 0], '+head': [-0.06, 0, 0] }],
    [0.8, { ...HUG_OPEN, '+spine': [0.02, 0, 0], '+head': [-0.03, 0, 0] }],
    [1.35, { ...HUG_HOLD, '+spine': [0.2, 0, 0], '+head': [0.1, 0, 0.18] }],
    [2.0, { ...HUG_HOLD, '+spine': [0.2, 0, 0.04], '+head': [0.12, 0.03, 0.22] }],
    [2.8, { ...HUG_HOLD, '+spine': [0.2, 0, -0.03], '+head': [0.11, 0.02, 0.2] }],
    [3.5, { ...HUG_HOLD, '+spine': [0.19, 0, 0.02], '+head': [0.1, 0.02, 0.19] }],
    [4.05, { ...HUG_LET_GO, '+spine': [0.04, 0, 0], '+head': [0, 0, 0.06] }],
    [4.6, { ...HUG_LET_GO, '+spine': [0.02, 0, 0], '+head': [0, 0, 0.04] }],
  ],
  expr: { blush: [[0, 0], [1.0, 0.6], [3.5, 0.6], [4.6, 0.3]],
          relaxed: [[0, 0], [1.0, 0.55], [3.5, 0.55], [4.0, 0]],
          happy: [[0, 0.6], [0.9, 0.6], [1.2, 0], [3.6, 0], [4.0, 0.55]],
          blink: [[0, 0], [1.0, 0], [1.3, 1], [3.4, 1], [3.7, 0]] },
};
