// bend_forward: the tame bend-over - turned away, bending forward from the
// hips, arms hanging loose, looking back at you over her shoulder. Tail
// stays down, no hands. Holds, then straightens. Full body only.
// (bend_over is the lewd one.)
const TURN = 2.2;
const BENT = {
  '+hips': [0, TURN, 0],
  '+spine': [0.85, -0.3, 0], '+chest': [0.45, -0.25, 0], '+upperChest': [0.2, -0.2, 0],
  '+neck': [-0.45, -0.5, 0], '+head': [-0.55, -0.8, 0.12],
  rightUpperArm: [-1.3, 0, 1.3], rightLowerArm: [0, 0.15, 0],
  leftUpperArm: [-1.3, 0, -1.3], leftLowerArm: [0, -0.15, 0],
};
const BREATHE = d => ({ '+upperChest': [0.2 + d, -0.2, 0] });

export default {
  keywords: ["bends forward", "leans over", "bends down"],
  about: "playful, flirty: bends forward with her back to you, looking back over her shoulder",
  private: true,      // never from stream chat
  full: true,         // full body only
  touch: ['back'], moods: ['loving'],      // the very warm row, a step below lewd
  dur: 7.0, fade: [1.2, 1.3],
  keys: [
    [0.0, BENT],
    [2.4, BREATHE(0.03)], [4.0, BREATHE(-0.01)], [5.6, BREATHE(0.02)],
    [7.0, BENT],
  ],
  expr: {
    blush:   [[0, 0.2], [1.2, 0.55], [6, 0.55], [7, 0.3]],
    happy:   [[0, 0.1], [1.2, 0.35], [6, 0.35], [7, 0.15]],
  },
};
