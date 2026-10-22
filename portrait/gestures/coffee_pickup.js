// coffee_pickup: she picks up her morning mug (coffee.py, props.js).
// No about or keywords: only her coffee plays it. The mug appears at
// prop_at, as her hand closes, and hold keeps her last pose (the mug held
// in front of her) until she puts it down. Tune it in the pose studio.
import { fingers } from './_pose.js';

const REACH = { rightUpperArm: [0, 0.35, 1.05], rightLowerArm: [0, 1.2, 0], rightHand: [-0.2, 0, 0.1], ...fingers('right', 0.15) };
const CARRY = { rightUpperArm: [0, 0.6, 1.0], rightLowerArm: [0, 2.2, 0], rightHand: [-0.55, 0, 0], ...fingers('right', 0.95),
                rightThumbMetacarpal: [0, -0.3, 0.4], rightThumbProximal: [0, 0, 0.5], rightThumbDistal: [0, 0, 0.4] };   // thumb round the mug

export default {
  dur: 2.2, fade: [0.5, 0.4],
  prop: 'mug', prop_at: 0.9, hold: true,
  keys: [
    [0.0, { rightUpperArm: [0, 0.05, 1.22], rightLowerArm: [0, 0.22, 0], rightHand: [0, 0, 0.08], ...fingers('right', 0.2),
            rightThumbMetacarpal: [0, 0, 0], rightThumbProximal: [0, 0, 0], rightThumbDistal: [0, 0, 0] }],
    [0.9, { ...REACH, '+head': [0.08, 0, 0] }],
    [1.6, { ...CARRY, '+head': [0.04, 0, 0] }],
    [2.2, CARRY],
  ],
  expr: { happy: [[0, 0], [1.4, 0.35], [2.2, 0.2]] },
};
