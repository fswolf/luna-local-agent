// Clothes in plain words (portrait.js; outfits.js does the taking off).
//
// clothesAsked(text)   what you said: "take off your top", "strip", "lose the
//                      tie", "put your shirt back on", "get dressed"
// clothesActed(text)   what she wrote in an action: *slips her top off*,
//                      *pulls her shirt back on*, (gets dressed), and in the
//                      first person: *unhooks my bra*, *slips out of my shorts*
//
// Both answer the same way, or null:
//   { wear: 'dressed' | 'underwear' | 'bare' }   everything on, down to her
//                                          underwear, or everything off
//   { off: [pieces] } / { on: [pieces] }   pieces by the labels outfits.js knows:
//                                          'top', 'tie', 'bottoms', 'shoes', 'socks',
//                                          'bra', 'panties' ("your shoes and socks" is
//                                          both; "your underwear" is bra and panties)
// "Strip" and "undress" mean down to her underwear; "naked" and "nude" mean
// everything, which only does more than that on a model whose underwear is
// its own pieces (outfits.js). The same rules either way (portrait.js clothes()).

const PIECES = [
  ['top', /\b(?:top|shirt|blouse|t-?shirt|tee|jacket|vest|sweater|hoodie)\b/],
  ['tie', /\b(?:tie|necktie|collar)\b/],
  ['bottoms', /\b(?:bottoms|shorts|skirt|pants|trousers|jeans)\b/],
  ['shoes', /\b(?:shoes|boots|sneakers|heels)\b/],
  ['socks', /\b(?:socks|stockings|tights)\b/],
  ['bra', /\b(?:bra|bralette|underwear|undies|lingerie)\b/],
  ['panties', /\b(?:panties|knickers|thong|briefs|underwear|undies|lingerie)\b/],
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
const STRIP = /(?:^|[.!?,;]\s*|\b(?:you|please|now|and|then|can|could|will|would|gonna|wanna|go|to)\s+)strip(?:\s+(?:down|off))?\b(?!\s*(?:tease|club|mall|steak|light|search))|\b(?:undress|get\s+undressed|take\s+(?:it\s+)?(?:all|everything)\s+off|down\s+to\s+(?:your|ur)\s+(?:underwear|undies|bra|panties))\b/;
const NAKED = /\b(?:get|go|be|strip)\s+(?:completely\s+|totally\s+|all\s+the\s+way\s+)?(?:naked|nude|bare)\b|\b(?:naked|nude)\s+for\s+me\b/;
const DRESS = /\b(?:get\s+dressed|dress\s+(?:up|back\s+up)|put\s+(?:your|ur|some)\s+clothes\s+(?:back\s+)?on|clothes\s+back\s+on|cover\s+up)\b/;
const OFF_ASK = re(String.raw`\b(?:take|pull|slip|peel|get|kick)\s+(?:your|ur|that|the)?\s*(W)\s*off\b|\b(?:take|pull|slip|peel|get|kick)\s+off\s+(?:your|ur|that|the)\s+(W)|\b(?:remove|lose|ditch|drop)\s+(?:your|ur|that|the)\s+(W)`);
const ON_ASK = re(String.raw`\b(?:put|pull|slip|get)\s+(?:your|ur|that|the)\s+(W)\s+(?:back\s+)?on\b|\b(?:put|pull|slip)\s+(?:back\s+)?on\s+(?:your|ur|that|the)\s+(W)`);

export function clothesAsked(text) {
  const t = String(text || '').toLowerCase().replace(/[’`]/g, "'");
  if (/\b(?:don'?t|do not|never|keep)\b/.test(t)) return null;      // "don't take your top off", "keep your shirt on"
  if (DRESS.test(t)) return { wear: 'dressed' };
  if (NAKED.test(t)) return { wear: 'bare' };
  if (STRIP.test(t)) return { wear: 'underwear' };
  let m = t.match(ON_ASK);
  if (m) return answer('on', piecesIn(m.slice(1).filter(Boolean).join(' ')));
  m = t.match(OFF_ASK);
  if (m) return answer('off', piecesIn(m.slice(1).filter(Boolean).join(' ')));
  return null;
}

// what she writes, about herself: in the third person (*slips her top off*,
// *takes off her tie*) or the first, the way she writes in a roleplay
// (*slips out of my shorts*, *unhooks my bra*, *slides the top off over my head*)
const S = "s?";                               // takes / take
const HER = "(?:her|my)";                     // whose: hers either way
const ANY = "(?:her|my|the)";                 // "the top" too, where the verb says enough
const V_OFF = `(?:take|pull|slip|slide|peel|shrug|wriggle|tug|kick)${S}`;
const her = src => re(src.replace(/HER/g, HER).replace(/ANY/g, ANY).replace(/VOFF/g, V_OFF));
const HER_STRIP = her(String.raw`\b(?:strips|undress(?:es)?|gets?\s+undressed|strip${S}\s+(?:down|off)|down\s+to\s+HER\s+(?:underwear|undies|bra))\b`);
const HER_NAKED = her(String.raw`\b(?:get|strip)${S}\s+(?:completely\s+|all\s+the\s+way\s+)?(?:naked|nude|bare)\b`);
const HER_DRESS = her(String.raw`\b(?:gets?\s+dressed|dresses|puts?\s+HER\s+clothes\s+(?:back\s+)?on)\b`);
// "off" has to be there: *tugs her skirt down* is fixing it, not taking it off
const HER_OFF = her(String.raw`\bVOFF\s+off\s+ANY\s+(W)|\bVOFF\s+ANY\s+(W)\s+off\b|\b(?:remove|shed|unhook|unclasp|unfasten)${S}\s+ANY\s+(W)|\b(?:slip|wriggle|step|shimmy|shimmie)${S}\s+out\s+of\s+ANY\s+(W)|\bpull${S}\s+HER\s+(W)\s+(?:up\s+)?over\s+HER\s+head|\blet${S}\s+ANY\s+(W)\s+(?:fall|drop)\b`);
// "back": *pulls my panties back into place*, *pulls her shorts back up* - after they were off
const HER_ON = her(String.raw`\b(?:put|pull|slip|tug)${S}\s+ANY\s+(W)\s+(?:back\s+)?on\b|\b(?:put|pull|slip)${S}\s+(?:back\s+)?on\s+ANY\s+(W)|\b(?:pull|tug|slip)${S}\s+ANY\s+(W)\s+back\s+(?:up|into\s+place)\b`);

export function clothesActed(text) {
  const t = String(text || '').toLowerCase().replace(/[’`]/g, "'");
  if (/\b(?:doesn'?t|does not|won'?t|keeps|refuses|teases|pretends|almost|starts?\s+to)\b/.test(t)) return null;
  if (HER_DRESS.test(t)) return { wear: 'dressed' };
  if (HER_NAKED.test(t)) return { wear: 'bare' };
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
