// leg_hold: turned slightly, raised leg toward you, she lifts her right leg straight up
// in front of her shoulder, hooks her arm round the back of the thigh and
// brings the hand back to her chest, leg pinned against her. Other hand rests
// back at her hip. Head tips to you: smug, half-lidded, blushing. Lewd leg
// touch; full body only. (standing_split is the bored, showy version.)
import { fingers } from './_pose.js';

const BASE = { hips: [0.03, 0, 0], leftUpperLeg: [0, 0, -0.04], leftUpperArm: [0.35, 0, -1.2], leftLowerArm: [0, -0.35, 0],
               '+hips': [0, 0.185, 0], '+spine': [-0.08, 0, 0.08] };   // turned a little, raised leg toward you
const HOLD = { ...BASE,
  rightUpperLeg: [-2.75, 0, -0.35], rightLowerLeg: [0, 0, 0], rightFoot: [0.6, 0, 0],      // up in front of her shoulder
  rightUpperArm: [0, 0.3, -0.2], rightLowerArm: [0, 2.3, 0.4], ...fingers('right', 0.5),    // round the thigh, hand at her chest
  '+head': [0.12, -0.1, -0.12] };
const SWAY = d => ({ '+spine': [-0.08 + d * 0.5, 0, 0.08 + d], '+head': [0.12, -0.1, -0.12 - d] });
const FRONT = { '+hips': [0, 0, 0], '+spine': [0, 0, 0] };   // square to you, before and after
const DOWN = { rightUpperLeg: [0, 0, 0], rightLowerLeg: [0, 0, 0], rightUpperArm: [0, 0.05, 1.22], rightLowerArm: [0, 0.22, 0] };

export default {
  keywords: ["holds her leg up", "leg up against her shoulder", "flexible tease", "standing split"],
  about: "smug, teasing: leg held straight up against her shoulder, arm hooked round it",
  private: true,      // never from stream chat
  lewd: true,         // held back on a stream where lewd is off (twitch/youtube "lewd": false)
  full: true,         // her legs: full-body framing only
  touch: ['legs'], moods: ['lewd'],
  dur: 7.2, fade: [0.6, 0.9],
  keys: [
    [0.0, { ...BASE, ...DOWN, ...FRONT }],
    [0.8, { ...BASE, rightUpperLeg: [-1.6, 0, -0.3], rightLowerLeg: [1.4, 0, 0], rightFoot: [0.4, 0, 0],   // knee up, arm under it
            rightUpperArm: [0, 0.5, 0.5], rightLowerArm: [0, 1.5, 0.2], '+head': [0.06, -0.05, -0.05] }],
    [1.7, HOLD],
    [2.8, SWAY(0.03)], [4.0, SWAY(-0.02)], [5.0, SWAY(0.02)],
    [5.6, HOLD],
    [6.4, { ...BASE, rightUpperLeg: [-1.5, 0, -0.3], rightLowerLeg: [1.3, 0, 0], rightUpperArm: [0, 0.3, 0.8], rightLowerArm: [0, 0.8, 0] }],
    [7.2, { ...BASE, ...DOWN, ...FRONT }],
  ],
  expr: {
    blush:   [[0, 0.3], [1.7, 0.8], [5.6, 0.85], [7.2, 0.45]],
    relaxed: [[0, 0], [1.7, 0.45], [5.6, 0.45], [7.2, 0.1]],
    happy:   [[0, 0.1], [1.7, 0.3], [5.6, 0.3], [7.2, 0.1]],
    blink:   [[0, 0], [1.7, 0.35], [5.6, 0.35], [7.2, 0]],          // half-lidded
  },
};
