// book_open_pickup: she brings up an open book to read (reading.py, props.js).
// Rough first pass: the book appears at prop_at as her hands come up.
import { DOWN, HOLD, READING, GRIP } from './_book.js';
import { both } from './_pose.js';

export default {
  dur: 1.8, fade: [0.4, 0.4],
  prop: 'book_open', prop_at: 0.7,
  hold: true,                       // she keeps holding it between the reading moves
  keys: [
    [0.0, DOWN],
    [0.8, { ...both({ rightUpperArm: [0.05, 0.3, 1.12], rightLowerArm: [-0.2, 1.1, 0], rightHand: [-0.15, 0, -0.1] }), ...GRIP }],
    [1.6, { ...HOLD, ...READING }],
    [1.8, { ...HOLD, ...READING }],
  ],
  expr: { relaxed: [[0, 0], [1.6, 0.35]] },
};
