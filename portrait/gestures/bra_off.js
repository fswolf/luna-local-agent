// bra_off: reaches behind her back to the clasp, chest out and head down, works it
// loose, brings her hands round to hold the cups to her chest for a shy moment, then
// draws it away to her side with her right hand (it comes off there: clothes) and
// lets it drop, her left arm still across her chest until the end. No about or
// keywords: it plays when her clothes come off (portrait.js undress).
import { both, fingers, open, REST } from './_pose.js';

const CLASP = { ...both({ rightUpperArm: [1.25, 0.85, 0.95], rightLowerArm: [0, 2.2, 0], rightHand: [0, 0, 0.3] }),
                ...fingers('right', 0.5), ...fingers('left', 0.5) };
const LOOSE = { ...both({ rightUpperArm: [1.18, 0.85, 1.05], rightLowerArm: [0, 2.05, 0], rightHand: [0, 0, 0.15] }),
                ...fingers('right', 0.3), ...fingers('left', 0.3) };
// hands flat on the cups (hands_on_chest.js)
const ON_CHEST = side => {
  const r = { rightUpperArm: [0.2, 0.4, 0.8], rightLowerArm: [0, 2, 0, -1.35], rightHand: [0, 0.4, 1.0] };
  const p = side === 'right' ? r : Object.fromEntries(Object.entries(both(r)).filter(([k]) => k.startsWith('left')));
  return { ...p, ...open(side) };
};
const HOLD = { ...ON_CHEST('right'), ...ON_CHEST('left') };
// her right arm out to the side, the bra in her fist
const AWAY = { rightUpperArm: [0, 0.45, 0.45], rightLowerArm: [0, 0.5, 0], rightHand: [0, 0, 0.2], ...fingers('right', 0.7) };
const DROP = { rightUpperArm: [0, 0.3, 0.75], rightLowerArm: [0, 0.35, 0], rightHand: [0, 0, 0.35], ...open('right') };
const BODY0 = { '+spine': [0, 0, 0], '+chest': [0, 0, 0], '+head': [0, 0, 0] };

export default {
  dur: 5.6,
  fade: [0.5, 0.8],
  keys: [
    [0.9, { ...CLASP, '+spine': [-0.08, 0, 0], '+chest': [-0.1, 0, 0], '+head': [0.18, 0, 0] }],
    [1.4, { rightHand: [0, 0, 0.45], leftHand: [0, 0, -0.15], '+head': [0.2, 0.05, 0.04] }],   // working the hooks
    [1.8, { rightHand: [0, 0, 0.2], leftHand: [0, 0, -0.4], '+head': [0.2, -0.04, -0.03] }],
    [2.2, { ...LOOSE, '+spine': [-0.04, 0, 0], '+chest': [-0.05, 0, 0], '+head': [0.12, 0, 0] }],   // undone
    [3.0, { ...HOLD, '+spine': [0.06, 0, 0], '+chest': [0.04, 0, 0], '+head': [0.12, 0.1, 0.08] }],  // held to her chest
    [3.5, { '+head': [0.1, 0.16, 0.1] }],
    [4.0, { ...AWAY, ...ON_CHEST('left'), '+spine': [0.03, 0, 0], '+chest': [0, -0.08, 0], '+head': [0.08, -0.12, -0.05] }],
    [4.6, { ...DROP, ...ON_CHEST('left'), '+head': [0.05, -0.05, 0] }],
    [5.6, { ...REST, ...BODY0 }],
  ],
  expr: { relaxed: [[0, 0], [1, 0.3], [5.6, 0.25]], blush: [[2.4, 0], [3, 0.5], [5.6, 0.45]] },
  private: true,
  clothes: [{ at: 3.8, off: ['bra'] }],
};
