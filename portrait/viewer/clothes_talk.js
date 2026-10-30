// Clothes in plain words (portrait.js; outfits.js does the taking off).
//
// clothesAsked(text)   what you said: "take off your top", "strip", "lose the
//                      tie", "put your shirt back on", "get dressed"
// clothesActed(text)   what she wrote in an action: *slips her top off*,
//                      *pulls her shirt back on*, (gets dressed)
//
// Both answer the same way, or null:
//   { wear: 'dressed' | 'underwear' }      everything on, or everything off
//   { off: [pieces] } / { on: [pieces] }   pieces by the labels outfits.js knows:
//                                          'top', 'tie', 'bottoms', 'shoes', 'socks'
//                                          ("your shoes and socks" is both)
// "Naked" and "nude" mean down to her underwear here: the topless model is a
// switch you make yourself, never something she does.

const PIECES = [
  ['top', /\b(?:top|shirt|blouse|t-?shirt|tee|jacket|vest|sweater|hoodie)\b/],
  ['tie', /\b(?:tie|necktie|collar)\b/],
  ['bottoms', /\b(?:bottoms|shorts|skirt|pants|trousers|jeans)\b/],
  ['shoes', /\b(?:shoes|boots|sneakers|heels)\b/],
  ['socks', /\b(?:socks|stockings|tights)\b/],
];
const ALL = /\b(?:clothes|outfit|everything|it all|uniform)\b/;

// every piece named, in order; 'all' for "clothes", "everything"
function piecesIn(t) {
  const out = PIECES.filter(([, re]) => re.test(t)).map(([name]) => name);
  return out.length ? out : ALL.test(t) ? ['all'] : [];
}
const answer = (dir, pieces) =>
  pieces[0] === 'all' ? { wear: dir === 'off' ? 'underwear' : 'dressed' } : pieces.length ? { [dir]: pieces } : null;
// the words after "your": "top", "shoes and socks", "top, tie and skirt"
const W = "[a-z-]+(?:\\s*(?:,|and|&)\\s*(?:your\\s+|ur\\s+|her\\s+|the\\s+)?[a-z-]+){0,2}";
const re = src => new RegExp(src.replace(/W/g, W));

// what you say
// "strip" on its own only as something asked: "strip", "strip for me",
// "can you strip" - not "the comic strip" or "strip tease"
const STRIP = /(?:^|[.!?,;]\s*|\b(?:you|please|now|and|then|can|could|will|would|gonna|wanna|go|to)\s+)strip(?:\s+(?:down|off))?\b(?!\s*(?:tease|club|mall|steak|light|search))|\b(?:undress|get\s+(?:naked|undressed)|take\s+(?:it\s+)?(?:all|everything)\s+off|down\s+to\s+(?:your|ur)\s+(?:underwear|undies|bra|panties))\b/;
const DRESS = /\b(?:get\s+dressed|dress\s+(?:up|back\s+up)|put\s+(?:your|ur|some)\s+clothes\s+(?:back\s+)?on|clothes\s+back\s+on|cover\s+up)\b/;
const OFF_ASK = re(String.raw`\b(?:take|pull|slip|peel|get|kick)\s+(?:your|ur|that|the)?\s*(W)\s*off\b|\b(?:take|pull|slip|peel|get|kick)\s+off\s+(?:your|ur|that|the)\s+(W)|\b(?:remove|lose|ditch|drop)\s+(?:your|ur|that|the)\s+(W)`);
const ON_ASK = re(String.raw`\b(?:put|pull|slip|get)\s+(?:your|ur|that|the)\s+(W)\s+(?:back\s+)?on\b|\b(?:put|pull|slip)\s+(?:back\s+)?on\s+(?:your|ur|that|the)\s+(W)`);

export function clothesAsked(text) {
  const t = String(text || '').toLowerCase().replace(/[’`]/g, "'");
  if (/\b(?:don'?t|do not|never|keep)\b/.test(t)) return null;      // "don't take your top off", "keep your shirt on"
  if (DRESS.test(t)) return { wear: 'dressed' };
  if (STRIP.test(t)) return { wear: 'underwear' };
  let m = t.match(ON_ASK);
  if (m) return answer('on', piecesIn(m.slice(1).filter(Boolean).join(' ')));
  m = t.match(OFF_ASK);
  if (m) return answer('off', piecesIn(m.slice(1).filter(Boolean).join(' ')));
  return null;
}

// what she writes, about herself
const HER_STRIP = /\b(?:strips|undresses|gets\s+undressed|strips\s+(?:down|off)|down\s+to\s+her\s+(?:underwear|undies|bra))\b/;
const HER_DRESS = /\b(?:gets\s+dressed|dresses|puts\s+her\s+clothes\s+(?:back\s+)?on)\b/;
// "off" has to be there: *tugs her skirt down* is fixing it, not taking it off
const HER_OFF = re(String.raw`\b(?:takes|pulls|slips|peels|shrugs|wriggles|tugs|kicks)\s+off\s+her\s+(W)|\b(?:takes|pulls|slips|peels|shrugs|wriggles|tugs|kicks)\s+her\s+(W)\s+off\b|\b(?:removes|sheds)\s+her\s+(W)|\b(?:slips|wriggles|steps|shimmies)\s+out\s+of\s+her\s+(W)|\bpulls\s+her\s+(W)\s+(?:up\s+)?over\s+her\s+head|\blets\s+her\s+(W)\s+(?:fall|drop)\b`);
const HER_ON = re(String.raw`\b(?:puts|pulls|slips|tugs)\s+her\s+(W)\s+(?:back\s+)?on\b|\b(?:puts|pulls|slips)\s+(?:back\s+)?on\s+her\s+(W)`);

export function clothesActed(text) {
  const t = String(text || '').toLowerCase().replace(/[’`]/g, "'");
  if (/\b(?:doesn'?t|does not|won'?t|keeps|refuses|teases|pretends|almost|starts?\s+to)\b/.test(t)) return null;
  if (HER_DRESS.test(t)) return { wear: 'dressed' };
  if (HER_STRIP.test(t)) return { wear: 'underwear' };
  let m = t.match(HER_ON);
  if (m) return answer('on', piecesIn(m.slice(1).filter(Boolean).join(' ')));
  m = t.match(HER_OFF);
  if (m) {
    const pieces = piecesIn(m.slice(1).filter(Boolean).join(' '));
    if (pieces.length) return answer('off', pieces);
  }
  return null;
}
