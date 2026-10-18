// step_back: "hey." A small step back on her right foot, leaning away,
// shoulders turned and her chin up, looking off to the side.
const BACK = {
  hips: [0, -0.008, -0.05],
  rightUpperLeg: [0.32, 0, 0.04], rightLowerLeg: [0.28, 0, 0], rightFoot: [-0.15, 0, 0],
  leftUpperLeg: [-0.12, 0, 0], leftLowerLeg: [0.14, 0, 0],
  '+spine': [-0.07, -0.18, 0], '+head': [-0.06, -0.3, 0.04],
};

export default {
  about: "annoyed, backing off, not having it",
  full: true,                     // her legs: only offered in full-body framing
  touch: ['legs'],
  moods: ['cool'],
  dur: 2.8, fade: [0.25, 0.8],
  keys: [[0, BACK], [2.8, { ...BACK, '+head': [-0.04, -0.22, 0.03] }]],
  expr: { angry: 0.45 },
};
