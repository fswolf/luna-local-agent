// standing_split: facing you, she draws her right knee up, then extends the
// leg up her side into a near-vertical standing split, her right hand
// catching the ankle above her head, left arm out for balance. Holds with a
// small balance wobble and a bored, unimpressed look at you, then comes down.
// Neutral/bored: a leg touch or an idle when nothing's happening. Full body
// only. (leg_hold is the lewd version.)
import { fingers } from './_pose.js';

const BASE = { hips: [0.035, 0, 0], leftUpperLeg: [0, 0, -0.05], leftUpperArm: [0, 0, -0.1], leftLowerArm: [0, -0.15, 0] };
const SPLIT = {
  ...BASE,
  rightUpperLeg: [0, 0, -2.95], rightLowerLeg: [0, 0, 0], rightFoot: [0.6, 0, 0],     // leg straight up her side
  rightUpperArm: [0, 0.15, -1.1], rightLowerArm: [0, 0.4, 0], ...fingers('right', 0.75),   // hand at her ankle
  '+spine': [0, 0, -0.25], '+head': [0.06, 0.05, 0.12],
};
const WOBBLE = d => ({ '+spine': [0, 0, -0.25 + d], hips: [0.035 + d * 0.1, 0, 0] });

export default {
  keywords: ["standing split", "lifts her leg", "raises her leg", "high kick", "shows off her flexibility", "bored"],
  about: "bored, idly showing off: a standing split, leg held up by the ankle",
  full: true,         // her legs: full-body framing only
  touch: ['legs'], moods: ['neutral', 'calm', 'tired'],
  dur: 6.6, fade: [0.5, 0.9],
  keys: [
    [0.0, { ...BASE, rightUpperLeg: [0, 0, 0], rightLowerLeg: [0, 0, 0], rightUpperArm: [0, 0.05, 1.22], rightLowerArm: [0, 0.22, 0] }],
    [0.6, { ...BASE, rightUpperLeg: [-0.6, 0, -1.5], rightLowerLeg: [1.4, 0, 0], rightFoot: [0.4, 0, 0],      // knee up first
            rightUpperArm: [0, 0.15, -0.2], rightLowerArm: [0, 0.6, 0] }],
    [1.4, SPLIT],
    [2.4, WOBBLE(0.04)], [3.4, WOBBLE(-0.03)], [4.4, WOBBLE(0.03)],
    [5.0, SPLIT],
    [5.8, { ...BASE, rightUpperLeg: [-0.6, 0, -1.4], rightLowerLeg: [1.3, 0, 0], rightUpperArm: [0, 0.1, 0.4] }],
    [6.6, { ...BASE, rightUpperLeg: [0, 0, 0], rightLowerLeg: [0, 0, 0], rightUpperArm: [0, 0.05, 1.22] }],
  ],
  expr: {
    relaxed: [[0, 0.1], [1.4, 0.35], [5.0, 0.35], [6.6, 0.1]],
    blink:   [[0, 0.05], [1.4, 0.35], [5.0, 0.35], [6.6, 0.05]],     // heavy-lidded, bored
    ou:      [[0, 0], [2.6, 0], [2.9, 0.4], [3.4, 0]],      // a little sigh mid-hold
  },
};
