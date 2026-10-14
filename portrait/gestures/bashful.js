// bashful: the classic shy anime pose - her right hand loosely fisted just
// under her collarbone, elbow down at her side; her left arm down in front
// with the hand at the middle of her body,
// head tipped down and a little to the side, blushing. Arm angles solved
// against her body so nothing goes through her.
import { fingers } from './_pose.js';

const POSE = {
  rightUpperArm: [-0.8, -0.1, 1, 0.4], rightLowerArm: [0, 2.4, 0.3], rightHand: [0, 0, 0],
  leftUpperArm: [0.4, -0.95, -0.6, 0.4], leftLowerArm: [0, -1.1, 0], leftHand: [0, 0, 0],
  ...fingers('right', 0.95), ...fingers('left', 0.35),
  rightThumbProximal: [0, 0, 0.6], rightThumbDistal: [0, 0, 0.6],   // tucked into the fist
};
const DOWN = { '+spine': [0.04, -0.05, 0], '+head': [0.28, -0.16, -0.08] };

export default {
  keywords: ["bashfully", "blushes", "looks down shyly"],   // in what she writes, *like this*
  about: "bashful, shy, flustered and quiet",
  private: true,
  dur: 5.5, fade: [0.7, 0.9],
  keys: [
    [0.0, { ...POSE, ...DOWN }],
    [2.2, { '+spine': [0.05, -0.06, 0], '+head': [0.32, -0.2, -0.1] }],    // sinks a little lower
    [3.6, { '+spine': [0.04, -0.04, 0], '+head': [0.2, -0.08, -0.06] }],   // a peek up at you
    [5.5, { ...POSE, ...DOWN }],
  ],
  // blushing, worried brows and eyes, mouth small
  expr: { blush: 1, sad: 0.4, relaxed: 0.15 },
};
