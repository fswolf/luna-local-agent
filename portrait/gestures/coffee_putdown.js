// coffee_putdown: the mug goes back down (coffee.py, props.js). It
// disappears at prop_at, as her hand opens out of view.
import { fingers } from './_pose.js';

const GRIP = { ...fingers('right', 0.95),          // still holding it until it's down
               rightThumbMetacarpal: [0, -0.3, 0.4], rightThumbProximal: [0, 0, 0.5], rightThumbDistal: [0, 0, 0.4] };
const REACH = { rightUpperArm: [0, 0.35, 1.05], rightLowerArm: [0, 1.2, 0], rightHand: [-0.2, 0, 0.1], ...GRIP };
const CARRY = { rightUpperArm: [0, 0.6, 1.0], rightLowerArm: [-0.15, 2.2, 0],   // the mug out in front of her, as coffee_pickup ends
                rightHand: [-0.55, 0, 0], ...GRIP };

export default {
  dur: 2.0, fade: [0.3, 0.5],
  prop: 'mug', prop_at: 1.1,
  keys: [
    [0.0, CARRY],
    [1.1, { ...REACH, '+head': [0.08, 0, 0] }],
    [2.0, { rightUpperArm: [0, 0.05, 1.22], rightLowerArm: [0, 0.22, 0], rightHand: [0, 0, 0.08], ...fingers('right', 0.2),
            rightThumbMetacarpal: [0, 0, 0], rightThumbProximal: [0, 0, 0], rightThumbDistal: [0, 0, 0] }],
  ],
  expr: { relaxed: [[0, 0.2], [2.0, 0.3]] },
};
