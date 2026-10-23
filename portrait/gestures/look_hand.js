// look_hand
import { fingers } from './_pose.js';

export default {
  idle: ['grudge', 'cool', 'neutral', 'warm'],   // on her own, in these moods (studio: Details)
  dur: 3.6, fade: [0.6, 0.7],
  keys: [
    [0.0, { leftUpperArm: [0, -0.85, -0.75], leftLowerArm: [0, -1.9, 0.35], leftHand: [0.6, 0, 0.2], ...fingers('left', 0.1),
            '+head': [0.22, 0.18, 0.06] }],
    [1.8, { leftUpperArm: [0, -0.9, -0.7], leftLowerArm: [0, -1.95, 0.4], leftHand: [1.1, 0, 0.2], ...fingers('left', 0.5),
            '+head': [0.24, 0.2, 0.1] }],
    [3.6, { leftUpperArm: [0, -0.85, -0.75], leftLowerArm: [0, -1.9, 0.35], leftHand: [0.5, 0, 0.2], ...fingers('left', 0.2),
            '+head': [0.2, 0.16, 0.06] }],
  ],
  expr: { relaxed: 0.35 },
};
