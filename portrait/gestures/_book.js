// Shared poses for the book gestures (book_open_pickup, book_read_turn,
// book_read_lookup, book_open_putdown). A rough first pass, 2026-10-23: the
// book sits in her right hand (props.json "book_open"), the left hand holds
// the other side.
import { both, fingers } from './_pose.js';

export const DOWN = both({ rightUpperArm: [0, 0.05, 1.22], rightLowerArm: [0, 0.22, 0], rightHand: [0, 0, 0.08], ...fingers('right', 0.2) });
export const GRIP = { ...fingers('right', 0.35), ...fingers('left', 0.35) };
// both hands up in front of her chest, the open book between them
export const HOLD = { ...both({ rightUpperArm: [0.1, 0.4, 1.05], rightLowerArm: [-0.4, 1.9, 0], rightHand: [-0.3, 0, -0.2] }),
                      leftUpperArm: [0.1, -0.32, -1.05], ...GRIP };                     // Ryan's pass, 2026-10-23
export const READING = { '+neck': [0.08, 0, 0], '+head': [0.28, 0, 0] };      // looking down into it
