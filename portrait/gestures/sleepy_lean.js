// sleepy_lean: the tired in-between for a touch (touch.json "soft"): she
// doesn't jump into it, she settles into it - head tips to the side and down,
// shoulders drop, a slow breath, eyes half closed. No about/keywords on
// purpose: kept for touches, not offered as a tag.
const LEAN = { '+spine': [0.03, 0, 0.03], '+neck': [0.05, 0.03, 0.06], '+head': [0.12, 0.07, 0.12] };

export default {
  dur: 4.6, fade: [1.0, 1.2],
  keys: [
    [0.0, LEAN],
    [2.0, { '+spine': [0.05, 0, 0.04], '+neck': [0.06, 0.04, 0.08], '+head': [0.15, 0.08, 0.15] }],   // sinks in a little more
    [3.4, { '+spine': [0.04, 0, 0.035], '+neck': [0.055, 0.035, 0.07], '+head': [0.14, 0.075, 0.14] }],
    [4.6, LEAN],
  ],
  expr: { relaxed: [[0, 0.2], [1.2, 0.6], [4.6, 0.5]], blink: [[0, 0], [1.4, 0.45], [3.8, 0.45], [4.6, 0.2]],
          blush: [[0, 0.2], [1.5, 0.45], [4.6, 0.35]] },
};
