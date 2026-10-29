// cry: head down, shoulders shaking with little sobs, tears
export default {
  keywords: ["cries", "crying", "sob", "tears up", "😭", "😢"],   // in what she writes, *like this*
  about: "deeply sad, hurt, grieving, moved to tears: head down, shoulders shaking with sobs",   // offered to her as [cry] in tags mode
  dur: 7.0, fade: [0.9, 1.4],
  keys: [
    [0.0, { '+spine': [0.06, 0, 0], '+head': [0.1, 0, 0.05] }],
    [3.5, { '+spine': [0.08, 0, 0], '+head': [0.13, 0.05, 0.08] }],
    [7.0, { '+spine': [0.06, 0, 0], '+head': [0.1, 0, 0.04] }],
  ],
  osc: [],
  sob: true,
  expr: { tears: [[0, 0], [1.5, 1], [6, 1], [7, 0.8]], sad: 0.9, blink: [[0, 0], [2.4, 0], [2.6, 0.7], [3.4, 0.7], [3.6, 0]] },
};
