// note_show: a reminder came due (life/stickynotes.py): she holds up the
// sticky note she wrote, beside her face, so you can read it. The note
// (props.js, made in code with the reminder's words on it) appears at prop_at
// and goes at prop_off. No about/keywords: kept for reminders.
import { fingers, R } from './_pose.js';

const PINCH = { ...fingers('right', 0.55), rightThumbMetacarpal: [0, -0.3, 0.4], rightThumbProximal: [0, 0, 0.5], rightThumbDistal: [0, 0, 0.4] };
const UP = R({ rightUpperArm: [0, 0.95, 0.95], rightLowerArm: [0, -0.3, -2.3], rightHand: [-1.25, 0, -0.05], ...PINCH,
               '+head': [0, -0.1, -0.08], '+spine': [0, 0, -0.03] });

export default {
  dur: 5.2, fade: [0.45, 0.5],
  prop: 'note', prop_at: 0.45, prop_off: 4.8,
  place: { at: [-0.086, 0.002, 0.011], turn: [1.985, -0.259, 1.497] },   // where the note sits in her hand (props.js)
  keys: [
    [0.0, UP],
    [2.6, { ...UP, rightUpperArm: [0, 0.95, 0.92], '+head': [0.02, -0.12, -0.1] }],   // a little wiggle: look!
    [5.2, UP],
  ],
  osc: [['rightLowerArm', 2, 0.05, 1.6]],
  expr: { happy: [[0, 0], [0.6, 0.55], [4.6, 0.55], [5.2, 0.2]] },
};
