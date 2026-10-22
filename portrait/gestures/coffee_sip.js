// coffee_sip: a sip from her mug (coffee.py plays it every few minutes while
// she holds it). From the carry pose up to her lips, eyes half closed, and
// back. No about or keywords: only her coffee plays it. A starting point:
// tune it in the pose studio (load it, pose, save).
import { fingers } from './_pose.js';

const HAND = { ...fingers('right', 0.95),          // fingers through the handle, thumb round the mug
               rightThumbMetacarpal: [0, -0.3, 0.4], rightThumbProximal: [0, 0, 0.5], rightThumbDistal: [0, 0, 0.4] };
const CARRY = { rightUpperArm: [0, 0.6, 1.0], rightLowerArm: [0, 2.2, 0], rightHand: [-0.55, 0, 0], ...HAND };
const SIP = { rightUpperArm: [0, 0.75, 0.95], rightLowerArm: [0, 2.65, 0], rightHand: [-0.9, 0, -0.3], ...HAND };

export default {
  dur: 3.4, fade: [0.3, 0.3],
  prop: 'mug',
  keys: [
    [0.0, CARRY],
    [1.0, { ...SIP, '+head': [0.12, 0, 0] }],
    [2.2, { ...SIP, '+head': [0.1, 0, 0] }],
    [3.4, CARRY],
  ],
  expr: { blink: [[0, 0], [0.9, 0.6], [2.2, 0.6], [2.7, 0]], relaxed: [[0, 0], [2.4, 0.5], [3.4, 0.3]] },
};
