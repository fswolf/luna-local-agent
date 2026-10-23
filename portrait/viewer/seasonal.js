// Seasonal backgrounds: which picture in portrait/backgrounds/seasonal/ fits
// a date and time. Files are named <key>-day / <key>-night (or just <key>,
// or <key>-night alone), any picture type. A holiday wins on its days, then
// the season; a missing night falls back to the day picture and the other
// way round, a missing holiday to the season, and nothing at all to ''.

const ALIAS = { autumn: 'fall', xmas: 'christmas', 'new-years-eve': 'newyear', 'new-year': 'newyear', newyears: 'newyear',
                valentine: 'valentines', 'valentines-day': 'valentines' };
// [month, first day, last day] (months 1-12)
const HOLIDAYS = { halloween: [[10, 24, 31]], christmas: [[12, 15, 26]], newyear: [[12, 31, 31], [1, 1, 1]],
                   valentines: [[2, 13, 14]] };
// sunrise and sunset by month, local clock hours (about 52°N, with summer time;
// six months on for the south)
const SUN = [[8.6, 16.6], [7.8, 17.6], [7.6, 19.4], [6.6, 20.4], [5.6, 21.3], [5.2, 22.0],
             [5.5, 21.8], [6.3, 20.9], [7.2, 19.6], [8.0, 18.4], [7.9, 16.8], [8.6, 16.3]];

// South of the equator the seasons are the other way round. The page can't
// know where it is, so it guesses from the time zone: summer time in January,
// or a southern zone name. North when it can't tell.
const SOUTH_ZONES = /^(Australia|Antarctica)\/|^Pacific\/(Auckland|Chatham|Fiji|Noumea|Tahiti)|^America\/(Argentina|Santiago|Sao_Paulo|Montevideo|Asuncion|La_Paz|Lima|Punta_Arenas)|^Africa\/(Johannesburg|Maputo|Harare|Windhoek|Gaborone|Lusaka|Maseru|Mbabane)|^Indian\/(Mauritius|Reunion|Antananarivo)/;
export function south(year = new Date().getFullYear()) {
  const jan = new Date(year, 0, 1).getTimezoneOffset(), jul = new Date(year, 6, 1).getTimezoneOffset();
  if (jan !== jul) return jan < jul;
  try { return SOUTH_ZONES.test(Intl.DateTimeFormat().resolvedOptions().timeZone || ''); } catch (_) { return false; }
}
const flip = m => ((m + 5) % 12) + 1;     // a month six months on (1-12)

export function season(month, s = false) {
  if (s) month = flip(month);
  return [12, 1, 2].includes(month) ? 'winter' : month <= 5 ? 'spring' : month <= 8 ? 'summer' : 'fall';
}
export function holiday(month, day) {
  for (const [k, spans] of Object.entries(HOLIDAYS))
    if (spans.some(([m, a, b]) => month === m && day >= a && day <= b)) return k;
  return '';
}
export function isNight(d, s = false) {
  const [up, down] = SUN[s ? flip(d.getMonth() + 1) - 1 : d.getMonth()], h = d.getHours() + d.getMinutes() / 60;
  return h < up || h >= down;
}

export function seasonalPick(files, d = new Date(), s = south(d.getFullYear())) {
  if (isNaN(d)) d = new Date();
  const by = {};
  for (const f of files) {
    const m = String(f).toLowerCase().replace(/\.[a-z0-9]+$/, '').match(/^(.*?)(?:[-_ ](day|night))?$/);
    if (!m) continue;
    const key = ALIAS[m[1]] || m[1];
    (by[key] ||= {})[m[2] || 'day'] = f;
  }
  const when = isNight(d, s) ? 'night' : 'day', other = when === 'night' ? 'day' : 'night';
  for (const key of [holiday(d.getMonth() + 1, d.getDate()), season(d.getMonth() + 1, s)])
    if (key && by[key]) return by[key][when] || by[key][other];
  return '';
}
