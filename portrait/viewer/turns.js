// What you say that turns her round (portrait.js fromYou). The camera does
// the turning (turnTo), so this only works out where to:
//   { to: deg }   a fixed view: 0 her front, 180 her back, 90 her side
//   { by: deg }   from where she is now: + turns her right, - her left
//   { around }    "turn around": round, or back to you when she's turned away
//   null          not a turn
// People don't talk like settings, so it takes the plain ways of asking:
// "turn around", "show me your ass", "turn 90 deg", "turn left", "face me".
// Matched on what you said, before she answers.

const NUM = /\b(?:turn|spin|rotate)\s*(?:around\s*)?(-?\d{1,3})\s*(?:°|deg(?:ree)?s?\b)?/;
const LEFT = /\b(?:turn|spin|rotate)\s+(?:to\s+)?(?:your\s+|the\s+|ur\s+)?left\b/;
const RIGHT = /\b(?:turn|spin|rotate)\s+(?:to\s+)?(?:your\s+|the\s+|ur\s+)?right\b/;
const FRONT = /\b(?:face\s+me|turn\s+(?:back\s+)?(?:to|towards?)\s+me|turn\s+(?:back\s+)?around\s+to\s+(?:face\s+)?me|front\s+view|show\s+me\s+(?:your|ur)\s+(?:front|face))\b/;
const TURN_BACK = /\bturn\s+(?:back|back\s+around|round)\b/;
const BACK_PART = '(?:ass|butt|bum|booty|back|behind|rear|backside|tail|bottom)';
const AROUND = /\b(?:turn(?:\s+your)?\s+around|turn\s+your\s+back|spin\s+around|about\s+face)\b/;
const BACK = new RegExp(String.raw`\b(?:back\s+view|(?:show|give)\s+me\s+(?:your|ur|that)\s+${BACK_PART}|let\s+me\s+see\s+(?:your|ur|that)\s+${BACK_PART}|(?:wanna|want\s+to|can\s+i)\s+see\s+(?:your|ur|that)\s+${BACK_PART})\b`);
const SIDE = /\b(?:turn\s+(?:to\s+)?(?:the\s+|your\s+)?side(?:ways)?|turn\s+sideways|side\s+view|(?:show\s+me|let\s+me\s+see)\s+(?:your|ur)\s+(?:side|profile))\b/;

// "turn left", "turn around", "turn 90" and "turn back" are also how
// people talk about driving or a song ("turn left at the lights", "makes
// me turn around and smile"), so those count only in a short message: a
// request, not a sentence about something else. "Show me your ass" is
// never about anything else.
const SHORT = 8;

export function turnAsked(text) {
  const t = String(text || '').toLowerCase().replace(/[’`]/g, "'");
  const short = t.split(/\s+/).filter(Boolean).length <= SHORT;
  if (FRONT.test(t) || (short && TURN_BACK.test(t))) return { to: 0 };
  if (BACK.test(t)) return { to: 180 };
  if (SIDE.test(t)) return { to: 90 };
  if (!short) return null;
  if (AROUND.test(t)) return { around: true };      // round, or back to you if she's already turned
  if (LEFT.test(t)) return { by: -90 };
  if (RIGHT.test(t)) return { by: 90 };
  const n = t.match(NUM);
  if (n) {
    const deg = +n[1];
    if (deg % 360 === 0) return null;          // "turn 360": round and back where she was
    return { by: deg };
  }
  return null;
}
