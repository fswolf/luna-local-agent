// squirm: a quick little wriggle, the in-between for a touch when she's awake
// but not all the way into it yet (touch.json "soft"): shoulders hitch up, she
// twists a little side to side, a flustered smile. Small and quick.
// No about/keywords on purpose: kept for touches, not offered as a tag.
const W = (t, d) => [t, { '+spine': [0.02, 0.06 * d, 0.05 * d], '+upperChest': [0, 0.05 * d, 0],
                          '+rightShoulder': [0, 0, -0.06], '+leftShoulder': [0, 0, 0.06], '+head': [0.06, -0.08 * d, 0.06 * d] }];

export default {
  dur: 2.0, fade: [0.35, 0.6],
  keys: [W(0.0, 0), W(0.3, 1), W(0.6, -1), W(0.9, 0.8), W(1.2, -0.6), W(1.5, 0.3), W(2.0, 0)],
  expr: { blush: [[0, 0.4], [0.4, 0.85], [2.0, 0.6]], happy: [[0, 0.1], [0.4, 0.35], [2.0, 0.2]], blink: [[0, 0], [0.3, 0.35], [1.6, 0.35], [2.0, 0]] },
};
