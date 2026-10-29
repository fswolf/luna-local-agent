// dance: a cute little dance on a 120 bpm beat - hips bobbing and swaying,
// knees giving on every beat, then hands up one at a time, then both.
import { both, fingers, open } from './_pose.js';

const BEAT = 0.5;                         // seconds per beat (120 bpm)

// arm poses (right side; both() mirrors)
const FISTS = both({ rightUpperArm: [0, 0.8, 1.05], rightLowerArm: [0, 2.0, -0.35], rightHand: [0, 0.2, 0], ...fingers('right', 0.8) });
// arms up, palms turned in to face each other (forearm and wrist share the turn)
const UP_R = { rightUpperArm: [0, 0.2, -1.1], rightLowerArm: [0, 0.3, -0.3, -1.65], rightHand: [-1.1, 0, 0], ...open('right') };
const UP_L = { leftUpperArm: [0, -0.2, 1.1], leftLowerArm: [0, -0.3, 0.3, -1.65], leftHand: [-1.1, 0, 0], ...open('left') };
const HIP_R = { rightUpperArm: [0, -0.3, 0.75], rightLowerArm: [0, 0.5, 1.3], rightHand: [0, 0.3, 0.6] };
const HIP_L = { leftUpperArm: [0, 0.3, -0.75], leftLowerArm: [0, -0.5, -1.3], leftHand: [0, -0.3, -0.6] };
const KNEES = (k) => both({ rightUpperLeg: [-0.18 * k, 0, 0], rightLowerLeg: [0.36 * k, 0, 0], rightFoot: [-0.18 * k, 0, 0] });

// 16 beats: 4 with fists at her chest, 4 right hand up, 4 left hand up, 4 both up
const ARMS = [FISTS, FISTS, FISTS, FISTS,
              { ...UP_R, ...HIP_L }, { ...UP_R, ...HIP_L }, { ...UP_R, ...HIP_L }, { ...UP_R, ...HIP_L },
              { ...UP_L, ...HIP_R }, { ...UP_L, ...HIP_R }, { ...UP_L, ...HIP_R }, { ...UP_L, ...HIP_R },
              { ...UP_R, ...UP_L }, { ...UP_R, ...UP_L }, { ...UP_R, ...UP_L }, { ...UP_R, ...UP_L }];

const keys = [];
for (let i = 0; i < 16; i++) {
  const t = i * BEAT, side = i % 2 ? -1 : 1;
  // on the beat: down, weight to one side, head tipped the other way
  keys.push([t, { ...ARMS[i], ...KNEES(1), hips: [0.035 * side, -0.035, 0],
                  '+spine': [0.03, 0, -0.07 * side], '+head': [0.06, 0.05 * side, 0.1 * side] }]);
  // between beats: back up
  keys.push([t + BEAT / 2, { ...KNEES(0.2), hips: [0, 0.01, 0], '+spine': [0, 0, 0], '+head': [-0.02, 0, 0] }]);
}
keys.push([16 * BEAT, { ...FISTS, ...KNEES(0), hips: [0, 0, 0], '+spine': [0, 0, 0], '+head': [0, 0, 0] }]);

export default {
  about: "celebrating, feeling great, music, playful: a cute dance to the beat",
  keywords: ["danc", "💃", "🕺"],
  dur: 16 * BEAT, fade: [0.5, 0.7],
  keys,
  expr: { happy: 0.7, blush: 0.2 },
};
