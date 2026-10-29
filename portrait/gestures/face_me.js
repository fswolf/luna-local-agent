// face_me: turns the view, not her bones - the camera swings round her to 0°
// over about a second, and drifts back to the front after 120 s (face_me
// brings it back sooner). Her eyes stay ahead, so turned round you see the
// back of her head. Chat: !turn, !side, !front.
export default {
  view: 0,
  keywords: ["turns back to you", "faces you", "turns to face you", "turns back around", "turning back to you"],
  about: "turning back to face you, giving you her attention: the view swings back to her front",
};
