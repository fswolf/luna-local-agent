// peace_dance: a cute TikTok / K-pop style bit - hips swaying side to side,
// peace signs popping up beside her face, one hand then the other, then both,
// with a wink to finish.
import { fingers } from './_pose.js';

const BEAT = 0.55;                        // seconds per beat (~110 bpm)

// a peace sign: index and middle up, the rest curled, thumb over them
const PEACE = side => ({ ...fingers(side, 0.95),
  // the two fingers spread apart into a V
  [`${side}IndexProximal`]: [0, 0.22 * (side === 'right' ? 1 : -1), 0], [`${side}IndexIntermediate`]: [0, 0, 0], [`${side}IndexDistal`]: [0, 0, 0],
  [`${side}MiddleProximal`]: [0, -0.18 * (side === 'right' ? 1 : -1), 0], [`${side}MiddleIntermediate`]: [0, 0, 0], [`${side}MiddleDistal`]: [0, 0, 0],
  [`${side}ThumbProximal`]: [0, side === 'right' ? 0.4 : -0.4, side === 'right' ? 0.3 : -0.3],
  [`${side}ThumbDistal`]: [0, side === 'right' ? 0.5 : -0.5, 0] });

// hand up beside her face, palm to the camera
const V_R = { rightUpperArm: [0, 1.3, 0.5], rightLowerArm: [0, 0.1, -2.2], rightHand: [0, 0, 0.25], ...PEACE('right') };
const V_L = { leftUpperArm: [0, -1.3, -0.5], leftLowerArm: [0, -0.1, 2.2], leftHand: [0, 0, -0.25], ...PEACE('left') };
// hands on hips, elbows out
const HIP_R = { rightUpperArm: [0, -0.3, 0.75], rightLowerArm: [0, 0.5, 1.3], rightHand: [0, 0.3, 0.6], ...fingers('right', 0.3) };
const HIP_L = { leftUpperArm: [0, 0.3, -0.75], leftLowerArm: [0, -0.5, -1.3], leftHand: [0, -0.3, -0.6], ...fingers('left', 0.3) };

// 16 beats: hands on hips, right peace, left peace, both
const ARMS = [];
for (let i = 0; i < 16; i++) ARMS.push(i < 4 ? { ...HIP_R, ...HIP_L } : i < 8 ? { ...V_R, ...HIP_L }
                                     : i < 12 ? { ...V_L, ...HIP_R } : { ...V_R, ...V_L });

const keys = [];
for (let i = 0; i < 16; i++) {
  const t = i * BEAT, side = i % 2 ? -1 : 1;     // her weight swings to one side each beat
  const bent = side > 0 ? 'left' : 'right';      // the other knee gives
  keys.push([t, { ...ARMS[i],
    hips: [0.045 * side, -0.015, 0],
    '+spine': [0.02, 0.06 * side, -0.09 * side], '+head': [0.04, -0.06 * side, 0.13 * side],
    [`${bent}UpperLeg`]: [-0.2, 0, 0], [`${bent}LowerLeg`]: [0.4, 0, 0], [`${bent}Foot`]: [-0.2, 0, 0],
    [`${bent === 'left' ? 'right' : 'left'}UpperLeg`]: [0, 0, 0], [`${bent === 'left' ? 'right' : 'left'}LowerLeg`]: [0, 0, 0],
    [`${bent === 'left' ? 'right' : 'left'}Foot`]: [0, 0, 0] }]);
}
keys.push([16 * BEAT, { ...V_R, ...V_L, hips: [0, 0, 0], '+spine': [0, 0, 0], '+head': [0.03, 0, 0.14],
  leftUpperLeg: [0, 0, 0], leftLowerLeg: [0, 0, 0], leftFoot: [0, 0, 0],
  rightUpperLeg: [0, 0, 0], rightLowerLeg: [0, 0, 0], rightFoot: [0, 0, 0] }]);

export default {
  about: "cute, playful, showing off, a little dance",
  keywords: ["peace sign", "tiktok dance", "✌"],
  dur: 16 * BEAT + 0.6, fade: [0.45, 0.7],
  keys,
  osc: [['rightHand', 2, 0.18, 1 / (2 * BEAT)], ['leftHand', 2, -0.18, 1 / (2 * BEAT)]],   // little wrist wiggles
  expr: { happy: 0.75, blush: 0.25,
          blinkRight: [[0, 0], [16 * BEAT - 0.1, 0], [16 * BEAT + 0.1, 1], [16 * BEAT + 0.5, 1], [16 * BEAT + 0.6, 0]] },
};
