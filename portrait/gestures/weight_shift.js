// weight_shift: pleased and a bit posey - her hips sway onto her left
// leg, the right knee bends in, shoulders tip back over to balance, head
// tilted. Held for a few seconds, then back to standing.
const POSE = {
  hips: [0.055, -0.018, 0],
  leftUpperLeg: [0, 0, -0.09], leftLowerLeg: [0.04, 0, 0], leftFoot: [0, 0, 0.09],   // feet stay put
  rightUpperLeg: [-0.38, 0.15, 0.22], rightLowerLeg: [0.7, 0, 0], rightFoot: [-0.25, 0, -0.1],
  '+spine': [0, 0.08, 0.12], '+head': [0.04, -0.06, 0.18],
};

export default {
  about: "pleased, coy, showing off a little",
  full: true,                     // her legs: only offered in full-body framing
  touch: ['legs'],
  moods: ['warm', 'loving'],
  dur: 3.8, fade: [0.7, 0.9],
  keys: [[0, POSE], [3.8, { ...POSE, '+head': [0.04, -0.02, 0.1] }]],
  expr: { happy: 0.45, relaxed: 0.3, blush: [[0, 0], [1.2, 0.35], [3.8, 0.25]] },
};
