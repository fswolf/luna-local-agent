// Luna's portrait: the debug panel (?debug=1) and its light tour.
// Test buttons for her states, gestures, moods, face layers and lights, the
// model and view switches, and the bone list.
//
// Split out of portrait.js; it reaches back for what it needs through ctx.

import { FAILED as GESTURE_FAILED, NAMES as GESTURE_NAMES, GESTURES } from './gestures.js';
import { blush, tears } from './face_layers.js';
import { THREE } from './vendor/luna-three.js';

// What this borrows from portrait.js, read live (see bindDebugPanel there).
let ctx = null;
export function bindDebugPanel(c) { ctx = c; }

// The debug panel's "light tour": every way her light strips react, one
// after another, with a caption saying what you're looking at. Press again to stop.
let tourRun = 0, tourWas = null;
async function lightTour(toggle) {
  const run = ++tourRun;
  const cap = document.getElementById('lighttour') || Object.assign(document.body.appendChild(document.createElement('div')), { id: 'lighttour' });
  Object.assign(cap.style, { position: 'fixed', left: '50%', bottom: '18px', transform: 'translateX(-50%)', zIndex: 50,
    background: 'rgba(20,10,30,0.85)', color: '#ffd6ef', padding: '8px 14px', borderRadius: '8px', font: '14px sans-serif', pointerEvents: 'none' });
  const running = !!cap.dataset.on;
  if (!running) tourWas = { on: !!ctx.lights?.enabled, e: ctx.mind.energy, w: ctx.mind.warmth, label: ctx.mind.label, row: ctx.mind.row };
  const was = tourWas;
  const done = () => { cap.remove(); ctx.handle({ t: 'stage', status: 'Idle' }); ctx.throbAt = -99;
    ctx.handle({ t: 'mood', energy: was.e, warmth: was.w, label: was.label, row: was.row });
    if (!was.on && ctx.lights?.enabled) toggle(); };
  if (running) { tourRun++; done(); return; }                        // pressed while running: stop
  cap.dataset.on = '1';
  if (!ctx.lights?.enabled) toggle();
  const wait = s => new Promise(ok => setTimeout(ok, s * 1000));
  const step = async (text, s, fn) => { if (run !== tourRun) throw 0; cap.textContent = text; fn?.(); await wait(s); };
  const mood = (energy, warmth, row = '') => ctx.handle({ t: 'mood', energy, warmth, row, label: row ? 'heated' : '' });
  try {
    await step('light tour · at rest: dark', 2.5, () => { mood(0, 0.2); ctx.handle({ t: 'stage', status: 'Idle' }); });
    await step('listening: her ears glow', 3, () => ctx.handle({ t: 'stage', status: 'Listening...' }));
    await step('thinking: a sweep runs down her', 4.5, () => ctx.handle({ t: 'stage', status: 'Thinking...' }));
    await step('talking: they pulse with her voice', 3.5, () => { ctx.handle({ t: 'stage', status: 'Speaking...' }); ctx.fakeVoice(3.2); });
    await step('back to idle: dark again', 2, () => ctx.handle({ t: 'stage', status: 'Idle' }));
    for (const z of ['head', 'chest', 'arms', 'tummy', 'legs', 'tail'])
      await step(`a touch lights that part: ${z}`, 1.3, () => ctx.lights?.touched(z));
    await step('a tool failed: flicker', 2, () => ctx.lights?.failed());
    for (const [name, e, w, row] of [['sad: blue', -0.8, -0.1], ['mad: red', 0.2, -0.9], ['tired: violet', -0.8, 0.5], ['lewd: hot pink', 0.3, 0.9, 'lewd']])
      await step(`her mood picks the colour · ${name}`, 3, () => { mood(e, w, row); ctx.handle({ t: 'stage', status: 'Speaking...' }); ctx.fakeVoice(2.6); });
    await step('a lewd gesture: the throb builds, peaks, fades', 10.5, () => { ctx.handle({ t: 'stage', status: 'Idle' }); mood(0.3, 0.9, 'lewd'); ctx.throbAt = ctx.clock.elapsedTime; });
    await step('end of the tour', 1.5);
  } catch (_) { return; }
  if (run === tourRun) done();
}

export function debugPanel() {
  const buttons = {
    'light tour': () => lightTour(buttons['lights on/off']),
    'lights on/off': () => { const on = !(ctx.lights?.enabled ?? ctx.lightsCfg(ctx.cfg.lights || {}).enabled);
                             ctx.params.delete('lights'); ctx.setLights({ ...(ctx.cfg.lights || {}), enabled: on }); },
    throb: () => { if (!ctx.lights?.enabled) buttons['lights on/off'](); ctx.throbAt = ctx.clock.elapsedTime; },
    flicker: () => ctx.lights?.failed(),
    blink: () => { ctx.blink.next = 0; },
    twitch: () => ctx.twitch(0, 1),
    'left ear': () => ctx.twitch(1, 1),
    talk: () => { ctx.handle({ t: 'stage', status: 'Speaking...' }); ctx.fakeVoice(); },
    listen: () => ctx.handle({ t: 'stage', status: 'Listening...' }),
    think: () => ctx.handle({ t: 'stage', status: 'Thinking...' }),
    idle: () => ctx.handle({ t: 'stage', status: 'Idle' }),
    happy: () => ctx.handle({ t: 'mood', energy: 0.6, warmth: 1 }),
    sad: () => ctx.handle({ t: 'mood', energy: -0.8, warmth: -0.1 }),
    cross: () => ctx.handle({ t: 'mood', energy: 0.2, warmth: -0.9 }),
    neutral: () => ctx.handle({ t: 'mood', energy: 0, warmth: 0 }),
    // as agent/moods.json has them: the flirty mood, and the playful feeling
    flirty: () => { ctx.handle({ t: 'mood', energy: 0.5, warmth: 1, face: { happy: 0.3, blush: 0.4, lids: 0.45 }, emote: 'hearts' });
                    ctx.emoteLast = -99; ctx.emote('hearts'); },
    playful: () => ctx.handle({ t: 'feeling', face: { happy: 0.4, blush: 0.4, lids: 0.5 }, gesture: 'wink', seconds: 6 }),
    // the two rows past the grid, so touches answer from their lewd / grudge entries
    lewd: () => { ctx.handle({ t: 'mood', energy: 0.3, warmth: 0.9, label: 'frisky', row: 'lewd',
                           face: { happy: 0.4, blush: 0.55, lids: 0.5 }, emote: 'hearts' });
                  ctx.emoteLast = -99; ctx.emote('hearts'); },
    grudge: () => ctx.handle({ t: 'mood', energy: 0.8, warmth: -0.5, label: 'furious', row: 'grudge',
                           face: { angry: 0.9 }, emote: 'anger' }),
    'you: left': () => ctx.handle({ t: 'gaze', x: -0.8, y: -0.1 }),
    'you: right': () => ctx.handle({ t: 'gaze', x: 0.8, y: -0.1 }),
    'you: ahead': () => ctx.handle({ t: 'gaze', none: true }),
    glitch: () => ctx.holo?.glitch(1),
    fluster: () => { blush.fluster = 1; },
    'tears on/off': () => { tears.test = tears.test ? null : 1; },
    'wag tail': () => { ctx.moves.wag(1); setTimeout(() => ctx.moves.wag(0), 3000); },
    'holo on/off': () => ctx.setHolo(!(ctx.holo && ctx.holo.isOn())),
    hearts: () => { ctx.emoteLast = -99; ctx.emote('hearts'); },
    'sweat drop': () => { ctx.emoteLast = -99; ctx.emote('sweat'); },
    anger: () => { ctx.emoteLast = -99; ctx.emote('anger'); },
    question: () => { ctx.emoteLast = -99; ctx.emote('question'); },
  };
  const tune = document.getElementById('dtune');
  if (tune) {
    const row = document.createElement('label');
    row.style.display = 'block';
    row.textContent = 'mouth closed ';
    const r = document.createElement('input');
    Object.assign(r, { type: 'range', min: 0, max: 1, step: 0.05, value: ctx.mouthShut.amount });
    const out = document.createElement('span');
    out.textContent = ` ${ctx.mouthShut.amount}`;
    r.oninput = () => { ctx.mouthShut.amount = +r.value; out.textContent = ` ${r.value}  ("vrm": {"mouth_close": ${r.value}} in luna.json)`; };
    row.append(r, out);
    tune.appendChild(row);
    const row2 = document.createElement('label');
    row2.style.display = 'block';
    row2.textContent = 'blush ';
    const r2 = document.createElement('input');
    Object.assign(r2, { type: 'range', min: -0.05, max: 1, step: 0.05, value: -0.05, title: 'left end: automatic' });
    const out2 = document.createElement('span');
    out2.textContent = ' auto';
    r2.oninput = () => { blush.test = +r2.value < 0 ? null : +r2.value; out2.textContent = blush.test == null ? ' auto' : ` ${r2.value}`; };
    row2.append(r2, out2);
    row.after(row2);
  }
  // a button for every gesture file, labelled by its file name (blow_kiss.js -> "blow kiss"),
  // with a hover line saying what it is: about, touch zones, moods, and
  // 🔥 lewd, 🔒 private (never from stream chat), 🧍 full body only, ⛓ a chain of others
  const tips = {};
  for (const n of GESTURE_NAMES) {
    if (n.endsWith('_left')) continue;
    const label = n.replace(/_/g, ' '), g = GESTURES[n] || {};
    buttons[label] = () => ctx.gesture(n);
    tips[label] = [`${n}.js` + (g.lewd ? ' 🔥' : '') + (g.private ? ' 🔒' : '') + (g.full ? ' 🧍' : '') + (g.chain ? ` ⛓ ${g.chain.join(' → ')}` : ''),
                   g.about, g.touch && `touch: ${g.touch.join(', ')}`, g.moods && `moods: ${g.moods.join(', ')}`].filter(Boolean).join('\n');
  }
  // grouped, each group alphabetical; anything not listed is a gesture
  const GROUPS = [
    ['her state', ['idle', 'listen', 'talk', 'think']],
    ['face and mood', ['blink', 'cross', 'flirty', 'fluster', 'grudge', 'happy', 'lewd', 'neutral', 'playful', 'sad', 'tears on/off']],
    ['looking', ['you: ahead', 'you: left', 'you: right']],
    ['body', ['left ear', 'twitch', 'wag tail']],
    ['effects', ['glitch', 'holo on/off']],
    ['light strips (also: her state, mood, clicking her)', ['flicker', 'light tour', 'lights on/off', 'throb']],
    ['emotes', ['anger', 'hearts', 'question', 'sweat drop']],
  ];
  const grouped = new Set(GROUPS.flatMap(([, l]) => l));
  GROUPS.splice(1, 0, ['gestures', Object.keys(buttons).filter(l => !grouped.has(l))]);
  const box = document.getElementById('dbuttons');
  for (const [title, labels] of GROUPS) {
    const list = labels.filter(l => buttons[l]).sort((a, b) => a.localeCompare(b));
    if (!list.length) continue;
    const h = document.createElement('div');
    h.className = 'dim';
    h.style.margin = '6px 0 1px';
    h.textContent = title;
    box.appendChild(h);
    if (title === 'face and mood' && Array.isArray(ctx.cfg.moods) && ctx.cfg.moods.length) {
      // every mood in moods.json, top (lewd) to bottom (grudge): her face, idle
      // moves and emote as Luna would send them, so touches answer as in that mood
      const sel = document.createElement('select');
      sel.style.maxWidth = '100%';
      sel.add(new Option(`set her mood (${ctx.cfg.moods.length})`, ''));
      let og = null;
      ctx.cfg.moods.forEach((m, i) => {
        if (!og || og.label !== m.group) { og = document.createElement('optgroup'); og.label = m.group; sel.append(og); }
        og.append(new Option(m.name, String(i)));
      });
      sel.onchange = () => {
        const m = ctx.cfg.moods[+sel.value];
        if (!m) return;
        ctx.handle({ t: 'mood', label: m.name, row: m.row, energy: m.energy, warmth: m.warmth,
                 face: m.face, idle: m.idle, emote: m.emote, hold: '', tame: false });
        if (m.emote) { ctx.emoteLast = -99; ctx.emote(m.emote); }
        drawPool();
      };
      // what she'd drift into in this mood, and a button to play one of them
      const pool = document.createElement('div'), one = document.createElement('button');
      pool.className = 'dim'; pool.style.margin = '3px 0';
      one.textContent = '▶ play an idle';
      one.onclick = () => {
        const { mood, everyday } = ctx.idlePool(), all = [...new Set([...mood, ...everyday])];
        if (all.length) ctx.moves.play(all[Math.floor(Math.random() * all.length)]);
      };
      const drawPool = () => {
        const { mood, everyday } = ctx.idlePool();
        pool.textContent = `idles in ${ctx.mind.label || ctx.moodBand()} (${ctx.moodBand()}): ` +
          `mood ${mood.join(', ') || 'none'} · everyday ${everyday.join(', ') || 'none'}`;
      };
      drawPool();
      setInterval(drawPool, 3000);       // her mood moves on its own too
      box.append(sel, pool, one);
    }
    if (title === 'gestures') {
      // one menu, by file name: pick to play, ▶ to play it again
      const sel = document.createElement('select'), again = document.createElement('button');
      sel.style.maxWidth = '100%';
      sel.add(new Option(`pick a gesture (${list.length})`, ''));
      for (const label of list) {
        const n = label.replace(/ /g, '_'), g = GESTURES[n] || {};
        const o = new Option(n + (g.lewd ? ' 🔥' : '') + (g.private ? ' 🔒' : '') + (g.full ? ' 🧍' : '') + (g.chain ? ' ⛓' : ''), label);
        o.title = tips[label] || '';
        sel.add(o);
      }
      const play = () => { if (sel.value) buttons[sel.value](); sel.title = tips[sel.value] || ''; };
      sel.onchange = play;
      again.textContent = '▶'; again.title = 'play it again'; again.onclick = play;
      // this menu plays; ✎ opens the picked one in the pose studio to change it
      const edit = document.createElement('button');
      edit.textContent = '✎ edit'; edit.title = 'open it in the pose studio';
      edit.onclick = () => { const n = sel.value.replace(/ /g, '_'); if (n) ctx.studio?.open(n); else ctx.studio?.show(); };
      const key = document.createElement('div');
      key.className = 'dim';
      key.textContent = 'pick to play · ✎ edit opens it in the pose studio · 🔥 lewd · 🔒 never from stream chat · 🧍 full body only · ⛓ a chain';
      box.append(sel, again, edit, key);
      continue;
    }
    for (const label of list) {
      const b = document.createElement('button');
      b.textContent = label;
      if (tips[label]) b.title = tips[label];
      b.onclick = buttons[label];
      box.appendChild(b);
    }
    if (title === 'effects') box.appendChild(ctx.spankSlider());
  }
  if (ctx.fan) {            // the WiFi hologram fan, while casting is on
    const h = Object.assign(document.createElement('div'), { className: 'dim', textContent: 'hologram fan' });
    const line = Object.assign(document.createElement('div'), { className: 'dim' });
    h.style.margin = '6px 0 1px';
    const show = () => {
      const f = ctx.fan.status();
      line.textContent = !f.enabled ? 'cast is off (portrait.fan.cast)'
        : !f.connected ? `waiting for a fan (on its WiFi, or your router)${f.error ? ' · ' + f.error : ''}`
        : !f.type ? `a fan at ${f.ip}: asking which model it is...`
        : !f.geometry ? `a fan at ${f.ip} (type ${f.type}): a model we can't draw for`
        : `${f.model} (type ${f.type}) at ${f.ip} · ${f.casting ? `live ${f.fps}/s` : 'idle'} · jpeg q${f.quality}`
          + (f.geometry.support === 'legacy' ? ' · older format: may not show live' : '')
          + (f.error ? ' · ' + f.error : '');
    };
    show(); setInterval(show, 2000);
    box.append(h, line);
  }
  // the pose studio: its own window (studio.js); this button brings it back
  const open = document.createElement('button');
  open.textContent = '🎬 pose studio';
  open.onclick = () => ctx.studio?.show();
  box.appendChild(open);
  import('./studio.js').then(m => { ctx.studio = m.createStudio({ vrm: ctx.vrm, moves: ctx.moves, GESTURES, gesture: ctx.gesture, THREE, orbit: ctx.orbit, camera: ctx.camera, canvas: ctx.renderer.domElement, fx: ctx.fx, props: () => ctx.props }); })
    .catch(e => console.warn('pose studio:', e));
  // a gesture file with a mistake in it: say which and why, instead of a missing button
  if (Object.keys(GESTURE_FAILED).length) {
    const p = document.createElement('pre');
    p.style.color = '#ff8aa8';
    p.textContent = Object.entries(GESTURE_FAILED).map(([n, why]) => n.startsWith('(') ? why : `gestures/${n}.js didn't load: ${why}`).join('\n');
    box.appendChild(p);
  }
  document.getElementById('dears').textContent = ctx.ears.length
    ? ctx.ears.map(e => `${e.node.name} (${e.side > 0 ? 'left' : 'right'})`).join('\n')
    : 'none found - name them in config.json: "portrait": {"ear_bones": [...]}';
  document.getElementById('dexpr').textContent = [...ctx.has].join(', ') || 'none';
  const names = [];
  ctx.vrm.scene.traverse(o => { if (o.isBone || /ear|hair|j_sec/i.test(o.name)) names.push(o.name); });
  document.getElementById('dbones').textContent = names.filter(n => /ear|hair|sec/i.test(n)).join('\n') || '(none)';
  setInterval(() => { document.getElementById('dstate').textContent =
    `${ctx.mind.stage} · energy ${ctx.mind.energy.toFixed(2)} warmth ${ctx.mind.warmth.toFixed(2)}`; }, 300);
}

