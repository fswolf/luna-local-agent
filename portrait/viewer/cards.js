// Luna's portrait: the control panel's Cards tab (web/cards.py; docs/portrait.md, Cards).
// A card is a picture of her that is also her look: a PNG with her model, look,
// clothes map, gestures and voice inside. Saving takes the picture from the view
// as it is; putting one on reloads the portrait as that look. Kept in portrait/cards/.

const el = (tag, props = {}, ...kids) => { const n = Object.assign(document.createElement(tag), props); n.append(...kids); return n; };
const btn = (text, onclick, title = '') => el('button', { textContent: text, onclick, title });
const post = (what, body, headers = { 'Content-Type': 'application/json' }) =>
  fetch('cards/' + what, { method: 'POST', headers, body: typeof body === 'string' || body instanceof Blob ? body : JSON.stringify(body) })
    .then(async r => { let out; try { out = await r.json(); } catch (_) { out = {}; }
      if (!out.ok) throw new Error(out.error || `the server said ${r.status}`); return out; });

const MAX_CARD = 96 * 1024 * 1024;           // web/cards.py's limit, checked here first
const PARTS = [['model', 'model', true, 'the .vrm itself (16-22 MB). Off: a light card, for someone who has the model already'],
               ['look', 'look', true, 'background, framing, hologram, light strips (as saved in settings)'],
               ['clothes', 'clothes map', true, "the model's outfits.json, if it has one"],
               ['voice', 'voice', false, 'her Kokoro voice and speed']];

// The picture is what's on screen, background included, framed as a trading card with the
// card's name. The page's background is CSS behind a see-through canvas, so it's drawn in first.
async function background(c, g) {
  const b = document.body, bg = b.style.getPropertyValue('--user-bg').trim();
  if (b.classList.contains('transparent') || b.classList.contains('clear')) return;        // see-through stays so
  if (b.classList.contains('custom-bg') && /^url\(/.test(bg)) {
    const img = new Image();
    img.src = bg.replace(/^url\(["']?/, '').replace(/["']?\)$/, '');
    try { await img.decode(); } catch (_) { img.src = ''; }
    if (img.naturalWidth) {                                  // "cover", centred, like the page
      const s = Math.max(c.width / img.naturalWidth, c.height / img.naturalHeight);
      g.drawImage(img, (c.width - img.naturalWidth * s) / 2, (c.height - img.naturalHeight * s) / 2,
                  img.naturalWidth * s, img.naturalHeight * s);
      return;
    }
  }
  if (b.classList.contains('solid') && bg) { g.fillStyle = bg; g.fillRect(0, 0, c.width, c.height); return; }
  const css = getComputedStyle(document.documentElement);                // her usual glow
  const r = g.createRadialGradient(c.width / 2, c.height * 0.2, 0, c.width / 2, c.height * 0.2, Math.max(c.width, c.height) * 0.9);
  r.addColorStop(0, css.getPropertyValue('--bg-top').trim() || '#22142f');
  r.addColorStop(1, css.getPropertyValue('--bg-bottom').trim() || '#0b0711');
  g.fillStyle = r; g.fillRect(0, 0, c.width, c.height);
}

// A trading card, 3:4: a glowing border, the picture in its window, and her card's name on
// a plate under it. src: the whole view; the window takes the middle of it, at its own shape.
function frame(src, title) {
  const H = Math.min(1024, Math.round(src.height * 4 / 3 >= src.width ? src.height : src.width * 4 / 3)), W = Math.round(H * 3 / 4);
  const c = el('canvas', { width: W, height: H }), g = c.getContext('2d');
  const r = W * 0.05, b = W * 0.04, ir = r * 0.6, gap = W * 0.018;
  const edge = g.createLinearGradient(0, 0, W, H);
  edge.addColorStop(0, '#f6b6e4'); edge.addColorStop(0.35, '#e07ac8'); edge.addColorStop(0.7, '#8a5ad8'); edge.addColorStop(1, '#3a2466');
  g.fillStyle = edge; g.beginPath(); g.roundRect(0, 0, W, H, r); g.fill();
  g.strokeStyle = 'rgba(255,255,255,0.55)'; g.lineWidth = Math.max(1, W * 0.004);
  g.beginPath(); g.roundRect(W * 0.012, W * 0.012, W - W * 0.024, H - W * 0.024, r * 0.85); g.stroke();
  const iw = W - 2 * b, ph = H * 0.085, ih = H - 2 * b - ph - gap, py = b + ih + gap;
  // the picture: the middle of the view, cut to the window's shape
  const s = Math.min(src.width / iw, src.height / ih), sw = iw * s, sh = ih * s;
  g.save(); g.beginPath(); g.roundRect(b, b, iw, ih, ir); g.clip();
  g.drawImage(src, (src.width - sw) / 2, (src.height - sh) / 2, sw, sh, b, b, iw, ih);
  g.restore();
  g.strokeStyle = 'rgba(0,0,0,0.45)'; g.lineWidth = Math.max(1, W * 0.003);
  g.beginPath(); g.roundRect(b, b, iw, ih, ir); g.stroke();
  // the name plate
  const plate = g.createLinearGradient(0, py, 0, py + ph);
  plate.addColorStop(0, '#2a1d40'); plate.addColorStop(1, '#120c1e');
  g.fillStyle = plate; g.beginPath(); g.roundRect(b, py, iw, ph, ir); g.fill(); g.stroke();
  let size = ph * 0.52;
  const font = px => `600 ${px}px system-ui, "Segoe UI", sans-serif`;
  g.font = font(size);
  while (g.measureText(title).width > iw * 0.88 && size > 8) g.font = font(size -= 1);   // a long name shrinks to fit
  g.textAlign = 'center'; g.textBaseline = 'middle';
  g.shadowColor = '#e07ac8'; g.shadowBlur = size * 0.5;
  g.fillStyle = '#fff0fa'; g.fillText(title, W / 2, py + ph / 2 + H * 0.002);
  return c;
}

async function grab(canvas, title) {
  const full = el('canvas', { width: canvas.width, height: canvas.height });
  const g = full.getContext('2d');
  await background(full, g);
  // her, as just drawn (and not waiting forever in a tab that's in the background, where frames stop)
  await Promise.race([new Promise(ok => requestAnimationFrame(ok)), new Promise(ok => setTimeout(ok, 250))]);
  g.drawImage(canvas, 0, 0);
  return frame(full, title).toDataURL('image/png');
}

// page: the tab's element; canvas: the portrait's; GESTURES: every gesture loaded
export function cardsPage({ page, canvas, GESTURES }) {
  const status = el('div', { className: 'status' });
  const say = (msg, ms = 6000) => { status.textContent = msg; clearTimeout(say.t); if (ms) say.t = setTimeout(() => { status.textContent = ''; }, ms); };
  let list = [];

  const name = el('input', { type: 'text', placeholder: 'robot, human...', maxLength: 40 });
  const parts = {};
  const ticks = el('div', { className: 'chips' });
  for (const [p, label, on, tip] of PARTS) {
    parts[p] = el('input', { type: 'checkbox', checked: on });
    ticks.append(el('label', { title: tip }, parts[p], ' ' + label));
  }
  const mine = el('div', { className: 'chips' });
  const mineNote = el('div', { className: 'dim', style: 'margin-top:6px' });
  const picked = new Set();
  async function fillMine() {
    let names = null;
    try { names = await (await fetch('cards/yours.json', { cache: 'no-store' })).json(); } catch (_) { /* git can't say */ }
    const known = Object.keys(GESTURES).filter(n => !n.startsWith('__') && !n.endsWith('_left'));
    const own = (Array.isArray(names) ? names.filter(n => GESTURES[n]) : known).sort();
    mineNote.textContent = Array.isArray(names) ? 'your own gestures to carry (the ones that come with Luna, everyone has):'
      : "gestures to carry (this copy of Luna isn't from git, so which are yours can't be told: pick the ones you made):";
    mine.replaceChildren();
    if (!own.length) mine.append(el('span', { className: 'dim', textContent: 'none yet: make one in the pose studio and it shows up here' }));
    for (const n of own) {
      const b = el('input', { type: 'checkbox', checked: picked.has(n) });
      b.onchange = () => (b.checked ? picked.add(n) : picked.delete(n));
      mine.append(el('label', { title: GESTURES[n].about || '' }, b, ' ' + n + (GESTURES[n].clothes ? ' 👕' : '')));
    }
    for (const n of [...picked]) if (!own.includes(n)) picked.delete(n);
  }

  async function save() {
    if (saveBtn.disabled) return;                       // Enter again while it's still saving
    const n = name.value.trim();
    if (!n) { name.focus(); return say('give the card a name first'); }
    const slug = n.toLowerCase().replace(/[^a-z0-9_-]+/g, '-').replace(/^-+|-+$/g, '');
    if (list.some(c => c.name === slug) && !confirm(`There's a card called "${slug}" already. Replace it?`)) return;
    const carry = Object.fromEntries(Object.entries(parts).map(([p, b]) => [p, b.checked]));
    const gestures = [...picked].filter(g => GESTURES[g]).map(g => JSON.parse(JSON.stringify({ ...GESTURES[g], name: g })));
    carry.gestures = gestures.length > 0;
    saveBtn.disabled = true;
    say('making the card...', 0);
    try {
      // the model on screen, which ?model= or the model menu may have changed from the saved one
      const shown = await fetch('config.json' + location.search).then(r => r.json()).then(c => c.model || '').catch(() => '');
      const out = await post('save', { name: n, image: await grab(canvas, n), carry, gestures, model: shown });
      say(`saved "${out.name}": ${out.carries.join(', ') || 'just the picture'}` + (out.skipped.length ? ` · left out: ${out.skipped.join('; ')}` : ''), 12000);
      fill();
    } catch (e) { say('not saved: ' + e.message, 10000); }
    saveBtn.disabled = false;
  }

  async function putOn(c) {
    if (!confirm(`Put on "${c.name}"?\n\nIt carries: ${c.carries.join(', ') || 'nothing but a picture'}.` +
                 (c.carries.includes('look') ? '\nIts look replaces your saved one.' : '') + '\nThe portrait reloads.')) return;
    say(`putting on "${c.name}"...`, 0);
    try {
      const out = await post('load', { name: c.name });
      if (out.skipped.length) alert(`"${c.name}" is on, but left out:\n\n` + out.skipped.join('\n'));
      // the page reloads by itself (the "reload" event); if that never comes (the live feed
      // dropped), the same here
      setTimeout(() => {
        const u = new URL(location.href);
        if (out.model && u.searchParams.has('model')) { u.searchParams.set('model', out.model); location.replace(u.toString()); }
        else location.reload();
      }, 3000);
    } catch (e) { say('not put on: ' + e.message, 10000); }
  }

  async function forget(c) {
    if (!confirm(`Delete the card "${c.name}"? (A model it brought in stays in portrait/models/cards/.)`)) return;
    try { await post('delete', { name: c.name }); fill(); } catch (e) { say('not deleted: ' + e.message, 8000); }
  }

  async function takeIn(file) {
    if (!file) return;
    if (!/\.png$/i.test(file.name) && file.type !== 'image/png') return say(`${file.name}: a card is a .png`);
    if (file.size > MAX_CARD) return say(`${file.name}: too big for a card (at most 96 MB)`);
    say('reading the card...', 0);
    try {
      const out = await post('import', file, { 'Content-Type': 'image/png', 'X-Card-Name': encodeURIComponent(file.name.replace(/\.png$/i, '')) });
      const c = out.card;
      say(`added "${c.name}": ${c.carries.join(', ') || 'only a picture'}` + (c.gestures.length ? ` (gestures: ${c.gestures.join(', ')})` : '') + '. Click it to put it on.', 12000);
      fill();
    } catch (e) { say('not added: ' + e.message, 10000); }
  }

  const grid = el('div', { className: 'cardgrid' });
  const file = el('input', { type: 'file', accept: 'image/png,.png', hidden: true });
  const takeAll = async files => { for (const f of files) await takeIn(f); };   // several at once, one after another
  file.multiple = true;
  file.onchange = () => { takeAll([...file.files]); file.value = ''; };
  grid.ondragover = e => { e.preventDefault(); grid.classList.add('drop'); };
  grid.ondragleave = e => { if (!grid.contains(e.relatedTarget)) grid.classList.remove('drop'); };
  grid.ondrop = e => { e.preventDefault(); grid.classList.remove('drop'); takeAll([...e.dataTransfer.files]); };

  async function fill() {
    try { list = await (await fetch('cards/index.json', { cache: 'no-store' })).json(); } catch (_) { list = []; }
    grid.replaceChildren();
    if (!list.length) grid.append(el('div', { className: 'dim', style: 'grid-column: 1 / -1', textContent: 'no cards yet: save one above, or drop one here' }));
    for (const c of list) {
      const mb = c.size / 1048576;
      const tip = `${c.name}\ncarries: ${c.carries.join(', ') || 'only a picture'}` + (c.gestures.length ? `\ngestures: ${c.gestures.join(', ')}` : '') +
                  `\nmodel: ${c.model || '?'}\n${mb >= 1 ? mb.toFixed(0) : mb.toFixed(1)} MB · ${c.made.replace('T', ' ')}\nclick to put it on`;
      grid.append(el('div', { className: 'card' },
        el('button', { className: 'put', title: tip, onclick: () => putOn(c) },
           el('img', { src: `cards/thumb/${c.name}.png?v=${encodeURIComponent(c.made)}`, alt: '', loading: 'lazy' }),
           el('span', { textContent: c.name })),
        el('div', { className: 'cact' },
           el('a', { href: c.file, download: c.name + '.png', textContent: '⤓', title: 'save the card file, to share it' }),
           btn('✕', () => forget(c), 'delete this card'))));
    }
  }

  const saveBtn = btn('save card', save, 'saved in portrait/cards/');
  page.append(
    el('h4', { textContent: 'save a card' }),
    el('div', { className: 'dim', textContent: 'a picture of her that is also her look. The picture is what you see now, so pose and frame her first' }),
    el('div', { className: 'row' }, el('span', { className: 'l', textContent: 'name' }), name),
    ticks,
    mineNote, mine,
    el('div', { className: 'row' }, saveBtn), status,
    el('h4', { textContent: 'cards' }),
    el('div', { className: 'dim' }, 'click one to put it on · drop a card here, or ', btn('add a card…', () => file.click())),
    grid, file);
  name.onkeydown = e => { if (e.key === 'Enter') save(); };
  return { show() { fill(); fillMine(); } };
}
