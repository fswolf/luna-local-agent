// look_back: she turns away from you, bends forward from the hips with her
// hands on her thighs, and looks back over her shoulder - a slow sway while
// she holds it, then she straightens and turns back. Lewd idle; her butt
// comes into touch range while it plays (and her tail swishes).
//
// The body is bend_over's (turned, bent at the spine, no twist below the
// shoulders); only her upper chest, neck and head turn back toward you. The
// arms were fitted so the palms rest on the front of her thighs: lower arm
// y is the elbow hinge only, the left side mirrors the right.
const TURN = 2.3;
const ARM = { rightUpperArm: [-0.966, -0.123, 1.614], rightLowerArm: [-0.217, -0.158, 0], rightHand: [-0.157, 0.002, 0.708] };
const mirror = a => [a[0], -a[1], -a[2]];
const FINGERS = {};
['Index', 'Middle', 'Ring', 'Little'].forEach((f, i) => {
  const c = 0.18 + i * 0.04;
  FINGERS[`right${f}Proximal`] = [0, 0, c]; FINGERS[`right${f}Intermediate`] = [0, 0, c + 0.1]; FINGERS[`right${f}Distal`] = [0, 0, c * 0.8];
});
for (const [k, v] of Object.entries({ ...ARM, ...FINGERS })) FINGERS[k.replace('right', 'left')] = mirror(v);
const BEND = {
  '+hips': [0, TURN, 0],
  '+spine': [0.85, 0, 0], '+chest': [0.25, 0, 0], '+upperChest': [0.2, -0.25, 0],
  '+neck': [-0.3, -0.45, 0], '+head': [-0.35, -0.75, 0.15],             // chin up, looking back at you
  rightUpperLeg: [0, 0, -0.06], leftUpperLeg: [0, 0, 0.06],
  ...ARM, ...FINGERS,
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
