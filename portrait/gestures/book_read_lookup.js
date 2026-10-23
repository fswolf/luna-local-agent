// book_read_lookup: reading, she looks up over the book at you for a moment,
// smiles, and goes back to it. Rough first pass.
import { HOLD, READING } from './_book.js';

export default {
  dur: 4.0, fade: [0.3, 0.3],
  keys: [
    [0.0, { ...HOLD, ...READING }],
    [0.9, { ...HOLD, '+neck': [0.02, 0, 0], '+head': [0.02, 0, 0] }],
    [2.8, { ...HOLD, '+neck': [0.02, 0, 0], '+head': [0.0, 0, 0.04] }],
    [4.0, { ...HOLD, ...READING }],
  ],
  expr: { happy: [[0, 0], [1.1, 0.4], [2.8, 0.4], [4.0, 0]], relaxed: [[0, 0.35], [4.0, 0.35]] },
};
