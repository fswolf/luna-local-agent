// bend_forward: the everyday bend, facing you - bends at the waist and looks up
// at you, arms hanging loose, then straightens. The lewd one with her back to
// you is bend_over. First pass: the spine and head are bend_over's, the arms
// are left to hang; refine it in the pose studio (hands on her knees, a little
// bounce) and save over this file.
const BENT = {
  "+spine": [0.85, 0.0, 0.0], "+chest": [0.18, 0.0, 0.0], "+upperChest": [0.18, 0.0, 0.0],
  "+neck": [-0.35, 0.0, 0.0], "+head": [-0.5, 0.0, 0.0],
  "rightUpperLeg": [0.0, 0.0, -0.06], "leftUpperLeg": [0.0, 0.0, 0.06],
};

export default {
  dur: 4.0,
  fade: [1.0, 1.1],
  keys: [
    [0, BENT],
    [1.8, { ...BENT, "+head": [-0.56, 0.0, 0.04] }],      // a small tilt while she looks up at you
    [4.0, BENT],
  ],
  expr: { happy: [[0, 0], [1.0, 0.35], [3.4, 0.35], [4.0, 0.1]] },
  about: "bending forward at the waist toward you, looking up at you: a stretch, a closer look",
  keywords: ["bends forward", "bends down", "bending forward", "bending at the waist", "bends at the waist",
             "leans way forward", "touches her toes"],
  full: true,
  moods: ["neutral", "warm", "loving"],
};
