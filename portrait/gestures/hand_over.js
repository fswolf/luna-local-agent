// hand_over: the "mhmm, okay" in-between for a chest touch (touch.json "soft"):
// she lays her right hand flat over her heart, fingers across her chest, and lets it
// rest there with a slow breath, head tipped down a little. Left arm stays down.
// No about/keywords on purpose: kept for touches, not offered as a tag.
import { open } from './_pose.js';

// from bashful's arm (elbow down at her side, solved against her body), the forearm
// only a little twisted: a big twist read as a broken elbow (2026-10-27)
const HAND = { rightUpperArm: [-0.6, 0.1, 1.0, 0.4], rightLowerArm: [0, 2.3, 0.2, -0.6], rightHand: [0, 0.3, 0.9], ...open('right') };

export default {
  dur: 4.2, fade: [0.9, 1.0],
  keys: [
    [0.0, { ...HAND, '+spine': [0.03, 0, 0], '+head': [0.1, -0.05, 0.05] }],
    [1.8, { '+spine': [0.05, 0, 0], '+head': [0.14, -0.06, 0.07] }],     // a slow breath in
    [3.2, { '+spine': [0.03, 0, 0], '+head': [0.12, -0.05, 0.06] }],
    [4.2, { ...HAND, '+spine': [0.03, 0, 0], '+head': [0.1, -0.05, 0.05] }],
  ],
  expr: { relaxed: [[0, 0.2], [1.0, 0.5], [4.2, 0.4]], blush: [[0, 0.3], [1.2, 0.6], [4.2, 0.5]], blink: [[0, 0], [1.2, 0.3], [4.2, 0.2]] },
};
