// jog: running on the spot - knees up, arms pumping, a little bounce on
// every step - and then she's out of breath (flows into pant).
import { fingers } from './_pose.js';

const STEP = 0.36;                        // seconds per step
const STEPS = 14;

// one leg: how far the knee comes up (0 = standing on it, 1 = knee high)
const leg = (side, up) => ({
  [side + 'UpperLeg']: [-0.08 - 0.95 * up, 0, 0],
  [side + 'LowerLeg']: [0.18 + 1.35 * up, 0, 0],
  [side + 'Foot']: [-0.08 + 0.25 * up, 0, 0],
});
// one arm, elbow bent: swing -1 = fist forward, +1 = elbow back
const arm = (side, swing) => {
  const s = side === 'right' ? 1 : -1;
  return {
    [side + 'UpperArm']: [0.55 * swing, 0.1 * s, s * 1.22],
    [side + 'LowerArm']: [0, s * (1.5 - 0.25 * swing), 0],
    [side + 'Hand']: [0, 0, s * 0.1],
  };
};
// loose fists, thumbs tucked over the fingers
const FISTS = { ...fingers('right', 0.85), ...fingers('left', 0.85),
                rightThumbProximal: [0, -0.5, 0.3], rightThumbDistal: [0, -0.6, 0],
                leftThumbProximal: [0, 0.5, -0.3], leftThumbDistal: [0, 0.6, 0] };

const keys = [];
for (let i = 0; i < STEPS; i++) {
  const t = i * STEP, r = i % 2 === 0;       // right knee up on even steps
  // landing: feet together, knees give, arms passing her sides
  keys.push([t, { ...leg('right', 0), ...leg('left', 0), ...arm('right', 0), ...arm('left', 0), ...FISTS,
                  hips: [0, -0.025, 0], '+spine': [0.08, 0, 0], '+head': [-0.04, 0, 0] }]);
  // the top of a step: one knee high, the opposite arm forward, body up
  keys.push([t + STEP / 2, { ...leg('right', r ? 1 : 0.05), ...leg('left', r ? 0.05 : 1),
                             ...arm('right', r ? 1 : -1), ...arm('left', r ? -1 : 1),
                             hips: [0, 0.02, 0], '+spine': [0.06, r ? 0.08 : -0.08, 0], '+head': [-0.02, r ? -0.06 : 0.06, 0] }]);
}
keys.push([STEPS * STEP, { ...leg('right', 0), ...leg('left', 0), ...arm('right', 0), ...arm('left', 0),
                           hips: [0, 0, 0], '+spine': [0.08, 0, 0], '+head': [0, 0, 0] }]);

export default {
  about: "energetic, restless, exercise, can't sit still: runs on the spot, then catches her breath",
  keywords: ["jog", "runs in place", "running in place", "runs on the spot", "sprint", "🏃"],
  dur: STEPS * STEP, fade: [0.4, 0.5],
  then: 'pant',
  keys,
  expr: { happy: [[0, 0.6], [3, 0.4], [STEPS * STEP, 0.1]], blush: [[0, 0], [STEPS * STEP, 0.5]],
          aa: [[0, 0], [3, 0.15], [STEPS * STEP, 0.3]] },
};
