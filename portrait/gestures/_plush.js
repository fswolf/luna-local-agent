// Shared by the plush gestures: her moon-cat plush (portrait/props/plush.glb,
// life/plushie.py) hugged to her chest, both arms round it.
import { both, fingers } from './_pose.js';

export const HUG = { ...both({ rightUpperArm: [0, 0.75, 1.05], rightLowerArm: [0, 2.0, 0], rightHand: [-0.3, 0, 0], ...fingers('right', 0.4) }) };
export const REACH = both({ rightUpperArm: [0, 0.45, 1.1], rightLowerArm: [0, 0.9, 0], rightHand: [-0.2, 0, 0.1], ...fingers('right', 0.3) });
export const REST = both({ rightUpperArm: [0, 0.05, 1.22], rightLowerArm: [0, 0.22, 0], rightHand: [0, 0, 0.08], ...fingers('right', 0.2) });
