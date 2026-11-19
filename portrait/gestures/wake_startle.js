// wake_startle: you woke her (life/dozing.py) - a little jolt, head up, eyes
// wide for a moment, then she blinks and settles, still groggy. No
// about/keywords: kept for waking up, not offered as a tag.
export default {
  dur: 2.2, fade: [0.08, 0.8],
  keys: [
    [0.0,  { '+spine': [0.04, 0, 0], '+neck': [0.08, 0, 0.04], '+head': [0.16, 0.05, 0.1] }],
    [0.18, { '+spine': [-0.05, 0, 0], '+neck': [-0.06, 0, -0.01], '+head': [-0.14, -0.04, -0.03],
             '+leftShoulder': [0, 0, 0.12], '+rightShoulder': [0, 0, -0.12] }],                         // the jolt
    [0.9,  { '+spine': [-0.02, 0, 0], '+head': [-0.06, 0.06, 0], '+leftShoulder': [0, 0, 0.04], '+rightShoulder': [0, 0, -0.04] }],
    [1.5,  { '+head': [-0.04, -0.05, 0.02] }],                                                         // where am I
    [2.2,  { '+head': [0, 0, 0] }],
  ],
  expr: { surprised: [[0, 0], [0.15, 0.7], [0.7, 0.4], [1.4, 0]], blink: [[0, 1], [0.12, 0], [1.2, 0], [1.35, 1], [1.5, 0], [2.2, 0.25]],
          relaxed: [[1.2, 0], [2.2, 0.4]] },
};
