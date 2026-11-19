// note_write: you asked her to remind you (life/stickynotes.py): she holds a
// sticky note low in front of her and scribbles it down with her other hand,
// then tucks it away. No about/keywords: kept for reminders.
import { fingers } from './_pose.js';

const HOLD = { rightUpperArm: [0, 0.6, 1.0], rightLowerArm: [-0.15, 2.2, 0], rightHand: [-0.55, 0, 0], ...fingers('right', 0.6),
               rightThumbMetacarpal: [0, -0.3, 0.4], rightThumbProximal: [0, 0, 0.5], rightThumbDistal: [0, 0, 0.4] };
const WRITE = { leftUpperArm: [0, -0.62, -0.98], leftLowerArm: [0.1, -2.05, 0], leftHand: [-0.3, 0, -0.1], ...fingers('left', 0.7) };

export default {
  dur: 3.8, fade: [0.45, 0.5],
  prop: 'note', prop_at: 0.5, prop_off: 3.3,
  place: { at: [-0.025, -0.013, -0.04], turn: [-1.21, -0.864, 3.108] },   // flat in front of her, tipped up to write on
  keys: [
    [0.0, { ...HOLD, ...WRITE, '+head': [0.22, 0, 0], '+neck': [0.06, 0, 0] }],
    [3.8, { ...HOLD, ...WRITE, '+head': [0.2, 0.03, 0.02], '+neck': [0.06, 0, 0] }],
  ],
  osc: [['leftHand', 1, 0.18, 4.5], ['leftLowerArm', 1, 0.08, 1.1]],     // scribble scribble
  expr: { relaxed: 0.35, blink: [[0, 0], [0.4, 0.35], [3.4, 0.35], [3.8, 0]] },
};
