// look_back: she turns away from you, bends forward from the hips, and looks
// back over her shoulder - a slow sway while she holds it, then she
// straightens and turns back. Lewd idle; her butt comes into touch range
// while it plays (and her tail swishes).
//
// Turning: '+hips' spins her whole body round its own axis. The bend is all
// above the hips (spine, chest, upper chest), which already face the way she
// turned, so it tips her forward away from you; a hip tilt would tip her
// toward you instead. The upper body twists back and the head turns to you.
const TURN = 2.0;                  // radians: back mostly to you, room to look over her shoulder
const BEND = {
  '+hips': [0, TURN, 0],
  // twisting back toward you is negative y (positive turns her further away)
  '+spine': [0.78, -0.3, 0], '+chest': [0.5, -0.25, 0], '+upperChest': [0.25, -0.2, 0],
  '+neck': [-0.4, -0.45, 0], '+head': [-0.5, -0.7, 0.12],             // chin up, looking back at you
  // arms hang straight down from the bent body - toward her knees - which in
  // the bent chest's frame is a forward swing (x)
  rightUpperArm: [-0.9, 0, 1.4], rightLowerArm: [0, 0.25, 0],
  leftUpperArm: [-0.9, 0, -1.4], leftLowerArm: [0, -0.25, 0],
};
const SWAY = d => ({ '+hips': [0, TURN + d, d * 0.6] });

export default {
  about: "teasing, turns around and bends over, looking back at you",
  keywords: ["bends over", "turns around and bends", "looks back over her shoulder", "wiggles her butt"],
  private: true,      // never from stream chat
  lewd: true,         // held back on a stream where lewd is off (twitch/youtube "lewd": false)
  full: true,         // a deep bend drops her head out of the bust framing: full body only
  dur: 7.0, fade: [1.2, 1.4],
  keys: [
    [0.0, BEND],
    [2.4, SWAY(0.08)], [3.2, SWAY(-0.08)], [4.0, SWAY(0.08)], [4.8, SWAY(-0.06)],
    [7.0, BEND],
  ],
  expr: {
    blush:   [[0, 0.3], [1.2, 0.85], [5.5, 0.9], [7, 0.5]],
    happy:   [[0, 0], [1.4, 0.3], [5.5, 0.3], [7, 0.1]],
    relaxed: [[0, 0], [1.4, 0.35], [5.5, 0.35], [7, 0.1]],
  },
};
