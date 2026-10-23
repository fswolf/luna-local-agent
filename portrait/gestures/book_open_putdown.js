// book_open_putdown: she closes the book and lowers it; it goes at prop_at.
// Rough first pass.
import { DOWN, HOLD, READING } from './_book.js';

export default {
  dur: 1.8, fade: [0.3, 0.5],
  prop: 'book_open', prop_at: 1.0,
  keys: [
    [0.0, { ...HOLD, ...READING }],
    [1.0, { ...HOLD, '+head': [0.05, 0, 0] }],
    [1.8, DOWN],
  ],
  expr: { relaxed: [[0, 0.35], [1.8, 0.2]] },
};
