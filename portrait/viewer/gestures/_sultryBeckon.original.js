// sultryBeckon.js
import { fingers } from './_pose.js';

export default {
  about: "sultry come-hither, teasing", // [beckon] [tease]
  private: true,
  dur: 3.4,
  fade: [0.45, 0.6],
  keys: [
    [0.0, {
      '+hips': [0, 0.05, 0.03],
      '+spine': [0.02, -0.03, -0.02],
      '+head': [0.05, -0.06, -0.04],

      rightUpperArm: [0.1, 1.15, 0.35],
      rightLowerArm: [0, 1.95, -0.55, -0.45],
      rightHand: [-0.45, 0.1, 0.15],
      ...fingers('right', 0.55),

      leftUpperArm: [0, -0.35, -0.25],
      leftLowerArm: [0, 0.55, 0.2, 0.35],
      leftHand: [0.2, -0.15, 0]
    }],

    [0.9, {
      '+hips': [0, 0.08, 0.05],
      '+spine': [0.05, -0.02, -0.01],
      '+head': [0.1, -0.1, -0.08],

      rightUpperArm: [0.05, 1.25, 0.45],
      rightLowerArm: [0, 2.2, -0.7, -0.55],
      rightHand: [-0.6, 0.15, 0.25],
      ...fingers('right', 0.25),

      leftUpperArm: [0, -0.4, -0.3],
      leftLowerArm: [0, 0.6, 0.25, 0.4],
      leftHand: [0.25, -0.2, 0]
    }],

    [1.7, {
      '+hips': [0, 0.1, 0.06],
      '+spine': [0.08, 0.02, 0.01],
      '+head': [0.12, -0.04, 0.05],

      rightUpperArm: [0.1, 1.35, 0.55],
      rightLowerArm: [0, 2.3, -0.8, -0.65],
      rightHand: [-0.5, 0.25, 0.2],
      ...fingers('right', 0.1),

      leftUpperArm: [0, -0.45, -0.35],
      leftLowerArm: [0, 0.65, 0.3, 0.45],
      leftHand: [0.3, -0.25, 0]
    }],

    [2.5, {
      '+hips': [0, 0.06, 0.04],
      '+spine': [0.05, 0.04, 0.02],
      '+head': [0.08, 0.02, 0.04],

      rightUpperArm: [0.12, 1.25, 0.45],
      rightLowerArm: [0, 2.05, -0.6, -0.45],
      rightHand: [-0.4, 0.15, 0.1],
      ...fingers('right', 0.3),

      leftUpperArm: [0, -0.35, -0.25],
      leftLowerArm: [0, 0.55, 0.2, 0.35],
      leftHand: [0.2, -0.15, 0]
    }],

    [3.4, {
      '+hips': [0, 0.02, 0.01],
      '+spine': [0.02, 0, 0],
      '+head': [0.04, 0, 0],

      rightUpperArm: [0.1, 1.15, 0.35],
      rightLowerArm: [0, 1.95, -0.55, -0.45],
      rightHand: [-0.45, 0.1, 0.15],
      ...fingers('right', 0.5),

      leftUpperArm: [0, -0.3, -0.2],
      leftLowerArm: [0, 0.5, 0.2, 0.3],
      leftHand: [0.15, -0.1, 0]
    }]
  ]
};