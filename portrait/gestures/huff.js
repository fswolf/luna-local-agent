// huff: arms fold hard, shoulders jerk up on a sharp breath, chin up and the
// head snaps away from you; she holds it, then lets it go. Grudge.
import { fingers } from './_pose.js';

// Crossed arms, high: forearms folded across her chest so it reads in the
// bust framing (sulk.js folds lower, at the stomach). Clear of her body.
export const ARMS = {
  rightUpperArm: [-0.45, 0.95, 0.72, 0.6], rightLowerArm: [0, 2.2, 0], rightHand: [0, 0.3, 0],
  leftUpperArm: [0.1, -1.1, -0.62, -0.2], leftLowerArm: [0, -2.2, -0.3], leftHand: [0, -0.3, 0],
  ...fingers('right', 0.55), ...fingers('left', 0.55),
};
const UP = { '+rightShoulder': [0, 0, -0.16], '+leftShoulder': [0, 0, 0.16], '+upperChest': [-0.06, 0, 0] };
const DOWN = { '+rightShoulder': [0, 0, 0.02], '+leftShoulder': [0, 0, -0.02], '+upperChest': [0.03, 0, 0] };

export default {
  about: "annoyed huff, arms crossed, looking away",
  private: false,
  touch: ['head', 'tummy', 'arms'], moods: ['grudge'],
  dur: 3.0, fade: [0.25, 0.7],
  keys: [
    [0.0, {}],
    [0.28, { ...ARMS, ...UP, '+head': [-0.12, 0.55, -0.08], '+neck': [-0.04, 0.2, 0], '+spine': [-0.02, 0.12, 0] }],
    [0.6, { ...ARMS, ...DOWN, '+head': [-0.08, 0.62, -0.06], '+neck': [-0.03, 0.22, 0], '+spine': [0, 0.14, 0] }],
    [2.3, { ...ARMS, '+head': [-0.06, 0.58, -0.05], '+neck': [-0.02, 0.2, 0], '+spine': [0, 0.12, 0] }],
    [3.0, { ...ARMS, '+head': [-0.02, 0.3, -0.02], '+spine': [0, 0.05, 0] }],
  ],
  expr: {
    angry: [[0, 0.2], [0.3, 0.75], [2.4, 0.7], [3.0, 0.4]],
    ou:    [[0, 0], [0.3, 0], [0.42, 0.55], [0.7, 0]],      // the puff of breath
  },
};
