// book_read_turn: reading, she turns a page with her left hand. Rough first pass.
import { HOLD, READING } from './_book.js';

const REACH = { leftUpperArm: [0.1, -0.75, -0.95], leftLowerArm: [-0.4, -2.05, 0], leftHand: [-0.3, 0.15, 0.25] };
export default {
  dur: 2.4, fade: [0.3, 0.3],
  keys: [
    [0.0, { ...HOLD, ...READING }],
    [0.8, { ...HOLD, ...REACH, ...READING }],
    [1.5, { ...HOLD, ...READING, '+head': [0.3, -0.05, 0] }],
    [2.4, { ...HOLD, ...READING }],
  ],
  expr: { relaxed: [[0, 0.35], [2.4, 0.35]] },
};
