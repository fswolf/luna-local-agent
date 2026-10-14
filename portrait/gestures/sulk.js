// sulk: arms crossed, chin up, head and shoulders turned away from you.
// Held for as long as she's walked away (mood.walk_away): the portrait
// keeps it playing while the mood says "hold": "sulk", and lets it go -
// she turns back - when she's talking again. No about/keywords on
// purpose: it's a state, not something to drop into a sentence.
import { fingers } from './_pose.js';

// Not mirrored: one forearm over the other, the right a touch higher and
// in front. Solved against her body so nothing goes through her - her
// forearms are short for her width, so they fold in front of her
// stomach rather than fully crossing.
const ARMS = {
  rightShoulder: [0, 0, -0.08], leftShoulder: [0, 0, 0.08],
  rightUpperArm: [-0.4, 0.8, 1.1, 0.6], rightLowerArm: [0, 1.45, 0], rightHand: [0, 0.35, 0],
  leftUpperArm: [0.1, -0.95, -0.95, -0.2], leftLowerArm: [0, -1.45, -0.3], leftHand: [0, -0.35, 0],
  ...fingers('right', 0.5), ...fingers('left', 0.5),
};
const AWAY = { '+spine': [0, 0.15, 0], '+head': [0.06, 0.75, -0.06] };

export default {
  dur: 600, fade: [0.9, 1.1],
  keys: [
    [0.0, { ...ARMS, ...AWAY }],
    [1.4, { '+spine': [0, 0.16, 0], '+head': [-0.04, 0.8, -0.08] }],    // a huff, chin up
    [2.4, { ...ARMS, ...AWAY }],
    [600, { ...ARMS, ...AWAY }],
  ],
  // cross and a bit hurt: brows down, mouth set, no smile
  expr: { angry: 0.45, sad: 0.4 },
};
