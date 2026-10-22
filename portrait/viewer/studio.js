// The pose studio (debug viewer only): make and edit gestures without code.
//
//   pose     click a part of her (or pick a bone), drag x / y / z / twist,
//            mirror to the other side, face sliders. Copy gives the lines.
//   animate  keyframes on a timeline: posing at a time makes a key there
//            (or changes the one that's there). Scrub, play, loop.
//   details  name, what it's for, when it plays (touches, moods), flags,
//            sound, emotes, tail.
//   link     a chain: gestures one after another, saved as one.
//   prop     something in her hand (props.js): pick it, move and turn it in
//            the hand, size it, save where it sits (portrait/props/props.json).
//            A gesture can be made with it: when it appears or goes, and
//            whether her last pose is held while she carries it.
//
// Save writes portrait/gestures/<name>.js through the portrait server (your
// own machine only; an existing gesture is backed up before it's replaced).
// The pose plays through the gesture engine itself (moves.studio), so what
// you see is exactly what the saved file does.
//
// Torso and head bones are '+' (added on top of her breathing and posture,
// as gesture files write them); arms, legs, hands and fingers are set outright.
import { mirrorName, fingers, REST } from './gestures/_pose.js';
import { sample, sampleScalar } from './gestures.js';
import { makeWindow } from './windows.js';

const ADDED = new Set(['hips', 'spine', 'chest', 'upperChest', 'neck', 'head']);
const FACE = ['blush', 'happy', 'relaxed', 'sad', 'angry', 'surprised', 'aa', 'ou', 'blink', 'drool', 'tears'];
const ZONES = ['head', 'nose', 'mouth', 'neck', 'chest', 'arms', 'tummy', 'back', 'groin', 'butt', 'legs', 'tail'];
const BANDS = ['cool', 'neutral', 'warm', 'loving', 'lewd', 'grudge'];
const EMOTES = ['hearts', 'sweat', 'anger', 'question'];
const r2 = v => Math.round(v * 100) / 100;
const near = (a, b) => Math.abs(a - b) < 0.015;

export function createStudio({ vrm, moves, GESTURES, gesture, THREE, orbit, camera, canvas, fx = 1, props = null }) {
  const P = () => (typeof props === 'function' ? props() : props);
  const bones = Object.keys(vrm.humanoid.humanBones)
    .filter(n => vrm.humanoid.getNormalizedBoneNode(n) && !/Eye|jaw/.test(n));
  const key = b => (ADDED.has(b) ? '+' + b : b);

  // -- what's being made -----------------------------------------------------
  const fresh = () => ({ name: '', about: '', keywords: '', dur: 3, fade: [0.4, 0.5],
                         keys: [], expr: {}, private: false, lewd: false, full: false, idle: false,
                         touch: [], moods: [], sound: { name: '', from: '', len: '' }, emote: [],
                         tail: 'none', tailLevel: 0.8, chain: [], extra: {} });
  let A = fresh();
  const st = { on: false, live: null, bone: 'rightUpperArm', t: 0, playing: false, loop: false, timer: 0 };
  const view = {}, viewExpr = {};          // what she shows right now (handed to moves.studio)
  let sounds = [];
  fetch('sounds/index.json').then(r => (r.ok ? r.json() : {})).then(j => { sounds = Object.keys(j || {}).sort(); fillSounds(); }).catch(() => {});

  // -- building blocks ---------------------------------------------------------
  const el = (tag, props = {}, ...kids) => { const n = Object.assign(document.createElement(tag), props); n.append(...kids); return n; };
  const btn = (text, onclick, title = '') => el('button', { textContent: text, onclick, title });
  const row = (label, ...kids) => el('div', { className: 'row' }, el('span', { className: 'l', textContent: label }), ...kids);
  const status = el('div', { className: 'status' });
  const say = (msg, ms = 4000) => { status.textContent = msg; clearTimeout(say.t); if (ms) say.t = setTimeout(() => { status.textContent = ''; }, ms); };

  // -- the window --------------------------------------------------------------
  const posingDot = el('span', { className: 'posing', title: 'posing: she holds the pose you make' });
  const bar = el('div', { className: 'pbar' }, el('b', { textContent: 'pose studio' }), posingDot);
  const win = el('div', { id: 'studio', className: 'panel' }, bar);
  document.body.appendChild(win);
  const tabsRow = el('div', { className: 'tabs' });
  const pages = {};
  for (const name of ['pose', 'animate', 'details', 'link', 'prop']) {
    pages[name] = el('div', { hidden: name !== 'pose' });
    tabsRow.appendChild(btn(name, () => {
      for (const [n, p] of Object.entries(pages)) p.hidden = n !== name;
      for (const b of tabsRow.children) b.classList.toggle('on', b.textContent === name);
      if (name === 'animate') drawTimeline();
      if (name === 'prop') fillProps();
    }));
  }
  tabsRow.firstChild.classList.add('on');
  const onOff = btn('start posing', () => (st.on ? stop() : start()));
  const undoBtn = btn('↶', () => undo(), 'undo (Ctrl+Z)'), redoBtn = btn('↷', () => redo(), 'redo (Ctrl+Y)');
  // the camera, so you can check a pose from every side
  const cam = (yaw, label) => btn(label, () => { if (orbit) { orbit.yaw = yaw; } }, 'look at her from here');
  const zoom = (f, label) => btn(label, () => { if (orbit) orbit.zoom = Math.max(0.25, Math.min(4, orbit.zoom * f)); }, 'zoom');
  win.append(el('div', { className: 'row' }, onOff, btn('new', () => { if (confirm('Start a new gesture? What isn\'t saved is lost.')) { remember(); A = fresh(); refreshAll(); } }),
                  loadSel(), btn('load', load), undoBtn, redoBtn),
             el('div', { className: 'row' }, el('span', { className: 'l', textContent: 'view' }),
                cam(0, 'front'), cam(-0.8, '¾'), cam(-Math.PI / 2, 'side'), cam(Math.PI, 'back'), zoom(0.8, '＋'), zoom(1.25, '－')),
             tabsRow, ...Object.values(pages), status);
  const winCtl = makeWindow(win, bar, 'studio', 'pose studio');

  // -- pose page ---------------------------------------------------------------
  // the bone list, grouped the way you think about a body
  const GROUPS = [
    ['body and head', /^(hips|spine|chest|upperChest|neck|head)$/],
    ['right arm', /^right(Shoulder|UpperArm|LowerArm|Hand)$/], ['left arm', /^left(Shoulder|UpperArm|LowerArm|Hand)$/],
    ['right leg', /^right(UpperLeg|LowerLeg|Foot|Toes)$/], ['left leg', /^left(UpperLeg|LowerLeg|Foot|Toes)$/],
    ['right fingers', /^right(Thumb|Index|Middle|Ring|Little)/], ['left fingers', /^left(Thumb|Index|Middle|Ring|Little)/],
  ];
  const nice = b => b.replace(/^(right|left)/, '').replace(/([A-Z])/g, ' $1').trim().toLowerCase() + (ADDED.has(b) ? ' (+)' : '');
  const pick = el('select');
  const ordered = [];
  for (const [g, re] of GROUPS) {
    const og = el('optgroup', { label: g });
    for (const b of bones.filter(b => re.test(b))) { og.append(new Option(nice(b), b)); ordered.push(b); }
    if (og.children.length) pick.append(og);
  }
  for (const b of bones) if (!ordered.includes(b)) { pick.add(new Option(nice(b), b)); ordered.push(b); }
  pick.value = st.bone;
  pick.onchange = () => selectBone(pick.value);
  const stepBone = d => selectBone(ordered[(ordered.indexOf(st.bone) + d + ordered.length) % ordered.length]);
  const mirror = el('input', { type: 'checkbox' });
  const showAxes = el('input', { type: 'checkbox', checked: true });
  showAxes.onchange = () => moveGizmo();
  const sliders = {};
  const sliderBox = el('div');
  const AXC = { x: '#ff6b6b', y: '#6bdc7b', z: '#6ba8ff', twist: '#d9d4ec' };
  ['x', 'y', 'z', 'twist'].forEach((ax, i) => {
    const r = el('input', { type: 'range', min: -3.14, max: 3.14, step: 0.01, value: 0, style: `width:170px;accent-color:${AXC[ax]}`,
                            title: 'drag · double-click: back to 0' });
    const n = el('input', { type: 'number', step: 0.01, value: 0, style: 'width:58px' });
    const set = v => { v = r2(Math.max(-3.14, Math.min(3.14, v))); r.value = n.value = v; setBone(i, v); };
    r.oninput = () => set(+r.value);
    r.ondblclick = () => set(0);
    n.onchange = () => set(+n.value);
    const nudge = d => btn(d > 0 ? '+' : '−', e => set((+n.value || 0) + d * (e.shiftKey ? 0.2 : 1)), `${d > 0 ? '+' : ''}${d} (shift: ×0.2)`);
    sliders[ax] = { r, n, set };
    sliderBox.append(el('div', { className: 'row' }, el('span', { className: 'l', textContent: ax, style: `color:${AXC[ax]}` }),
                        nudge(-0.05), r, nudge(0.05), n));
  });
  const chips = el('div', { className: 'keys' });
  // hands: one curl for all the fingers of a hand
  const handSide = el('select');
  handSide.add(new Option('right hand', 'right')); handSide.add(new Option('left hand', 'left'));
  const curl = el('input', { type: 'range', min: 0, max: 1.3, step: 0.05, value: 0.3, style: 'width:120px', title: '0 open · 1.3 fist' });
  curl.oninput = () => setHand(+curl.value);
  const faceBox = el('details', { open: false }, el('summary', { textContent: 'face (at this moment)' }));
  const faceSliders = {};
  for (const f of FACE) {
    const r = el('input', { type: 'range', min: 0, max: 1, step: 0.05, value: 0, style: 'width:170px', title: 'double-click: 0' });
    r.oninput = () => setFace(f, +r.value);
    r.ondblclick = () => { r.value = 0; setFace(f, 0); };
    faceSliders[f] = r;
    faceBox.append(row(f, r));
  }
  const poseText = el('pre', { style: 'user-select:text' });
  pages.pose.append(
    el('div', { className: 'dim', textContent: 'click a part of her, or pick a bone · drag a ring on her (or a slider) to turn it · red x, green y, blue z, white twist' }),
    row('bone', btn('◀', () => stepBone(-1), 'previous bone'), pick, btn('▶', () => stepBone(1), 'next bone')),
    el('div', { className: 'row' }, el('span', { className: 'l' }), el('label', {}, mirror, ' mirror the other side'), ' ',
       el('label', {}, showAxes, ' show rings')),
    sliderBox,
    el('div', { className: 'row' }, btn('reset bone', resetBone), btn('copy bone', copyBone), btn('copy pose', () => copy(poseText.textContent))),
    el('div', { className: 'dim', textContent: 'moved in this key (click one to pick it):' }), chips,
    row('hand', handSide, curl, btn('open', () => { curl.value = 0.05; setHand(0.05); }), btn('fist', () => { curl.value = 1.2; setHand(1.2); })),
    faceBox, poseText);

  // -- animate page --------------------------------------------------------------
  const time = el('input', { type: 'range', min: 0, max: 3, step: 0.05, value: 0, hidden: true });
  const tl = el('canvas', { className: 'timeline', title: 'click to go there · drag a key to move it' });
  const timeN = el('input', { type: 'number', step: 0.05, value: 0, style: 'width:62px' });
  time.oninput = () => { timeN.value = time.value; seek(+time.value); };
  timeN.onchange = () => { time.value = timeN.value; seek(+timeN.value); };
  const durN = el('input', { type: 'number', step: 0.1, min: 0.2, value: A.dur, style: 'width:62px' });
  durN.onchange = () => { A.dur = Math.max(0.2, +durN.value || 1); time.max = A.dur; drawKeys(); };
  const keyBox = el('div', { className: 'keys' });
  const loopBox = el('input', { type: 'checkbox' });
  loopBox.onchange = () => { st.loop = loopBox.checked; };
  const playBtn = btn('▶ play', () => (st.playing ? stopPlay() : play()));
  pages.animate.append(
    el('div', { className: 'dim', textContent: 'pose at a time and it becomes a key there · click a key to go to it' }),
    tl, row('time', time, timeN, btn('◀ key', () => stepKey(-1), 'previous key (←)'), btn('key ▶', () => stepKey(1), 'next key (→)')),
    row('length', durN, el('span', { className: 'dim', textContent: ' seconds' })),
    el('div', { className: 'row' }, btn('+ key here', () => { remember(); keyAt(st.t, true); show(); }, 'K'), btn('copy key', copyKey),
       btn('paste key', pasteKey), btn('delete key', deleteKey)),
    el('div', { className: 'row' }, btn('◀ 0.5s', () => nudgeKey(-0.5)), btn('0.5s ▶', () => nudgeKey(0.5)),
       el('span', { className: 'dim', textContent: ' move the key (or drag it on the timeline)' })),
    el('div', { className: 'dim', textContent: 'keys: space play · ← → keys · K add · Del delete · Ctrl+Z undo' }),
    keyBox,
    el('div', { className: 'row' }, playBtn, el('label', {}, loopBox, ' loop'),
       btn('save', () => saveIt(false)), btn('save as…', () => saveIt(true))));

  // -- details page --------------------------------------------------------------
  const nameIn = el('input', { type: 'text', placeholder: 'my_gesture (letters, numbers, _)' });
  const aboutIn = el('input', { type: 'text', placeholder: 'what it is and when: "shy, flustered by a compliment"' });
  const kwIn = el('input', { type: 'text', placeholder: 'words she writes that play it, comma separated' });
  const fadeIn = el('input', { type: 'number', step: 0.05, min: 0, value: 0.4, style: 'width:62px' });
  const fadeOut = el('input', { type: 'number', step: 0.05, min: 0, value: 0.5, style: 'width:62px' });
  const flagBoxes = {};
  const flags = el('div', { className: 'chips' });
  for (const [f, label] of [['private', '🔒 never from chat'], ['lewd', '🔥 lewd'], ['full', '🧍 full body only'], ['idle', 'idle (on her own)']]) {
    flagBoxes[f] = el('input', { type: 'checkbox' });
    flags.append(el('label', {}, flagBoxes[f], ' ' + label));
  }
  const zoneBoxes = {}, zones = el('div', { className: 'chips' });
  for (const z of ZONES) { zoneBoxes[z] = el('input', { type: 'checkbox' }); zones.append(el('label', {}, zoneBoxes[z], ' ' + z)); }
  const bandBoxes = {}, bands = el('div', { className: 'chips' });
  for (const b of BANDS) { bandBoxes[b] = el('input', { type: 'checkbox' }); bands.append(el('label', {}, bandBoxes[b], ' ' + b)); }
  const moodIn = el('input', { type: 'text', placeholder: 'or mood names: flirty, heated…', style: 'width:200px' });
  const soundSel = el('select');
  const soundFrom = el('input', { type: 'text', placeholder: 'from: random or seconds', style: 'width:120px' });
  const soundLen = el('input', { type: 'number', step: 0.5, min: 0, placeholder: 'length', style: 'width:62px' });
  const emoteBox = el('div');
  const tailSel = el('select');
  for (const [v, l] of [['none', 'tail: as it is'], ['wag', 'tail: swishes'], ['tail_up', 'tail: lifted and held']]) tailSel.add(new Option(l, v));
  const tailLvl = el('input', { type: 'range', min: 0.1, max: 1, step: 0.05, value: 0.8, style: 'width:100px' });
  pages.details.append(
    row('name', nameIn), row('about', aboutIn), row('keywords', kwIn), row('fade', fadeIn, fadeOut, el('span', { className: 'dim', textContent: ' in / out' })),
    el('div', { className: 'dim', textContent: 'flags' }), flags,
    el('div', { className: 'dim', textContent: 'touches that play it' }), zones,
    el('div', { className: 'dim', textContent: 'in these moods (none ticked: any mood)' }), bands, row('', moodIn),
    row('sound', soundSel), row('', soundFrom, soundLen),
    el('div', { className: 'row' }, el('span', { className: 'l', textContent: 'emotes' }), btn('+ emote', () => { A.emote.push({ name: 'hearts', at: +st.t.toFixed(2) }); drawEmotes(); })),
    emoteBox, row('tail', tailSel, tailLvl),
    el('div', { className: 'row' }, btn('save', () => saveIt(false)), btn('save as…', () => saveIt(true))));

  // -- link page -----------------------------------------------------------------
  const linkSel = el('select');
  const chainBox = el('div');
  pages.link.append(
    el('div', { className: 'dim', textContent: 'gestures one after another, saved as one (details: name, flags, sound, emotes)' }),
    el('div', { className: 'row' }, linkSel, btn('+ add', () => { if (linkSel.value) { A.chain.push(linkSel.value); drawChain(); } })),
    chainBox,
    el('div', { className: 'row' }, btn('▶ play chain', playChain), btn('save chain', () => saveIt(false, true)), btn('save chain as…', () => saveIt(true, true))));

  // -- prop page -------------------------------------------------------------------
  // what she holds, where it sits in her hand (saved for every gesture), and
  // what this gesture does with it
  const PI = Math.PI;
  const propSel = el('select'), handSel = el('select');
  for (const h of ['right', 'left']) handSel.add(new Option(h + ' hand', h));
  const pp = { name: '', shown: '' };
  const propSliders = {};
  const propBox = el('div');
  const PF = [['at', 0, 'x', -0.25, 0.25, 0.002], ['at', 1, 'y', -0.25, 0.25, 0.002], ['at', 2, 'z', -0.25, 0.25, 0.002],
              ['turn', 0, 'turn x', -PI, PI, 0.01], ['turn', 1, 'turn y', -PI, PI, 0.01], ['turn', 2, 'turn z', -PI, PI, 0.01],
              ['scale', -1, 'size', 0.2, 2, 0.01]];
  for (const [field, i, label, lo, hi, step] of PF) {
    const r = el('input', { type: 'range', min: lo, max: hi, step, value: 0, style: 'width:150px' });
    const n = el('input', { type: 'number', step, style: 'width:64px' });
    const set = v => {
      const p = P()?.PROPS[pp.name];
      if (!p) return;
      v = Math.round(Math.max(lo, Math.min(hi, v)) / step) * step;
      v = +v.toFixed(4);
      r.value = n.value = v;
      if (i < 0) P().set(pp.name, { [field]: v });
      else { const a = p[field].slice(); a[i] = v; P().set(pp.name, { [field]: a }); }
    };
    r.oninput = () => set(+r.value);
    n.onchange = () => set(+n.value);
    const nudge = d => btn(d > 0 ? '+' : '−', e => set((+n.value || 0) + d * step * (e.shiftKey ? 1 : 5)), 'shift: finer');
    propSliders[label] = { r, n, field, i };
    const color = { x: AXC.x, y: AXC.y, z: AXC.z }[label.slice(-1)];
    propBox.append(el('div', { className: 'row' }, el('span', { className: 'l', textContent: label, style: color ? `color:${color}` : '' }),
                      nudge(-1), r, nudge(1), n));
  }
  const propUses = el('input', { type: 'checkbox' }), propHold = el('input', { type: 'checkbox' });
  const propAt = el('input', { type: 'number', step: 0.05, min: 0, placeholder: 'seconds', style: 'width:72px' });
  propUses.onchange = () => { remember(); A.extra.prop = propUses.checked && pp.name ? pp.name : undefined; drawPropUse(); };
  propHold.onchange = () => { remember(); A.extra.hold = propHold.checked || undefined; };
  propAt.onchange = () => { remember(); A.extra.prop_at = propAt.value === '' ? undefined : r2(+propAt.value); };
  pages.prop.append(
    el('div', { className: 'dim', textContent: 'a 3D model in her hand (portrait/props/*.glb); it moves with every gesture' }),
    row('prop', propSel, handSel),
    propBox,
    el('div', { className: 'dim', textContent: 'x y z move it in the hand (metres), turn spins it, size scales it · pose her arm on the pose page to check it from every side' }),
    el('div', { className: 'row' }, btn('save placement', saveProp, 'where it sits, for every gesture (portrait/props/props.json)'),
       btn('put it away', () => { propSel.value = ''; pickProp(); })),
    el('div', { className: 'dim', textContent: 'this gesture (saved with it)' }),
    el('div', { className: 'row' }, el('label', {}, propUses, ' made with it (in her hand when it\'s opened)')),
    row('at', propAt, el('span', { className: 'dim', textContent: ' s, when it appears or goes ' }), btn('now', () => { propAt.value = st.t; propAt.onchange(); }, 'the time on the timeline')),
    el('div', { className: 'row' }, el('label', {}, propHold, ' hold her last pose while she carries it')));
  propSel.onchange = () => pickProp();
  handSel.onchange = () => { if (pp.name) { P().set(pp.name, { hand: handSel.value }); } };
  async function fillProps() {
    const pr = P();
    if (!pr) return;
    await pr.ready;
    const cur = propSel.value || pp.name;
    propSel.textContent = '';
    propSel.add(new Option('nothing in her hand', ''));
    for (const n of pr.names()) propSel.add(new Option(n, n));
    propSel.value = pr.names().includes(cur) ? cur : '';
    drawProp(); drawPropUse();
  }
  function pickProp() {
    const pr = P();
    if (!pr) return;
    // only put away what the studio got out (not her coffee, if she's drinking it)
    if (pp.shown && pp.shown !== propSel.value) { pr.hide(pp.shown); pp.shown = ''; }
    pp.name = propSel.value;
    if (pp.name) {
      handSel.value = pr.side(pp.name);
      const already = pr.held(pp.name);
      pr.show(pp.name, handSel.value).then(ok => { if (ok && !already) pp.shown = pp.name; });
    }
    drawProp(); drawPropUse();
  }
  function drawProp() {
    const p = P()?.PROPS[pp.name];
    propBox.hidden = handSel.disabled = !p;
    if (!p) return;
    for (const s of Object.values(propSliders)) s.r.value = s.n.value = +(s.i < 0 ? (p.scale ?? 1) : p[s.field][s.i]).toFixed(4);
  }
  function drawPropUse() {
    propUses.checked = !!A.extra.prop;
    propUses.disabled = !pp.name && !A.extra.prop;
    propHold.checked = !!A.extra.hold;
    propAt.value = A.extra.prop_at ?? '';
  }
  async function saveProp() {
    const p = P()?.PROPS[pp.name];
    if (!p) return say('pick a prop first');
    try {
      const r = await fetch('props/save', { method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ name: pp.name, hand: handSel.value, at: p.at, turn: p.turn, scale: p.scale ?? 1 }) });
      const j = await r.json();
      say(j.ok ? `saved where the ${pp.name} sits` : j.error || 'not saved', 6000);
    } catch (e) { say(`couldn't save: ${e.message || e}`, 8000); }
  }

  // -- posing ----------------------------------------------------------------------
  function start() {
    if (st.on) return;
    stopPlay();
    st.on = true; onOff.textContent = 'stop posing'; posingDot.textContent = '● posing';
    st.live = moves.studio(view, viewExpr);
    show();
  }
  function stop() {
    stopPlay();
    st.on = false; onOff.textContent = 'start posing'; posingDot.textContent = '';
    st.live?.stop(); st.live = null;
  }
  // the key at time t (made if asked)
  function keyAt(t, make) {
    let k = A.keys.find(k => near(k.t, t));
    if (!k && make) { k = { t: +t.toFixed(2), pose: {} }; A.keys.push(k); A.keys.sort((a, b) => a.t - b.t); if (k.t > A.dur) { A.dur = k.t; durN.value = A.dur; time.max = A.dur; } drawKeys(); }
    return k;
  }
  const asKeys = () => A.keys.map(k => [k.t, k.pose]);
  // what she looks like at time t: the keys sampled, like the engine does
  function sampled(t) {
    const out = {}, keys = asKeys();
    for (const b of new Set(A.keys.flatMap(k => Object.keys(k.pose)))) { const v = sample(keys, b, t); if (v) out[b] = v; }
    return out;
  }
  function show() {
    for (const k of Object.keys(view)) delete view[k];
    Object.assign(view, sampled(st.t));
    for (const k of Object.keys(viewExpr)) delete viewExpr[k];
    for (const [f, v] of Object.entries(A.expr)) viewExpr[f] = sampleScalar(v, st.t);
    st.live?.refresh();
    showBone(); drawFace(); drawKeys(); drawText(); drawChips(); moveGizmo();
  }
  function showBone() {
    const v = view[key(st.bone)] || REST[st.bone] || [0, 0, 0, 0];   // untouched: where she rests
    ['x', 'y', 'z', 'twist'].forEach((ax, i) => { sliders[ax].r.value = sliders[ax].n.value = r2(v[i] || 0); });
  }
  function setBone(i, v) {
    remember();
    start();
    const k = keyAt(st.t, true), b = key(st.bone);
    const cur = (k.pose[b] || view[b] || REST[b] || [0, 0, 0]).slice();   // from rest, not a T-pose
    while (cur.length <= i) cur.push(0);
    cur[i] = r2(v);
    if (cur.length === 4 && !cur[3]) cur.pop();
    k.pose[b] = cur;
    if (mirror.checked && /^(left|right)/.test(st.bone))
      k.pose[mirrorName(b)] = cur.length > 3 ? [cur[0], -cur[1], -cur[2], cur[3]] : [cur[0], -cur[1], -cur[2]];
    show();
  }
  function resetBone() {
    remember();
    const k = keyAt(st.t, false), b = key(st.bone);
    if (k) { delete k.pose[b]; if (mirror.checked) delete k.pose[mirrorName(b)]; }
    show();
  }
  function setFace(f, v) {
    remember();
    start();
    keyAt(st.t, true);
    let track = A.expr[f];
    track = Array.isArray(track) ? track : track != null ? [[0, track]] : [];
    const at = track.findIndex(p => near(p[0], st.t));
    if (at >= 0) track[at][1] = v; else track.push([+st.t.toFixed(2), v]);
    track.sort((a, b) => a[0] - b[0]);
    A.expr[f] = track;
    show();
  }
  function drawFace() { for (const f of FACE) faceSliders[f].value = viewExpr[f] || 0; }
  const line = (b, v) => `${b.startsWith('+') ? `'${b}'` : b}: [${v.map(r2).join(', ')}],`;
  function drawText() {
    const k = keyAt(st.t, false);
    const pose = k ? k.pose : {};
    poseText.textContent = Object.keys(pose).length ? `{ ${Object.entries(pose).map(([b, v]) => line(b, v)).join('\n  ')} }`
                                                    : `(no key at ${st.t.toFixed(2)}s - pose and one is made)`;
  }
  const copy = s => (navigator.clipboard?.writeText(s).then(() => say('copied')) ?? Promise.resolve()).catch(() => say('copy failed - select the text instead'));
  function copyBone() { const b = key(st.bone); if (view[b]) copy(line(b, view[b])); }

  // -- picking a bone, and showing it on her ---------------------------------------
  function selectBone(b) { st.bone = b; pick.value = b; showBone(); drawChips(); moveGizmo(); }
  // The rings: one per slider, like a 3D program's rotate tool. Each sits the
  // way its slider really turns the bone (x, then y, then z, then twist: a
  // gimbal), the cone shows which way + goes, and they stay the same size on
  // screen however far the camera is. Drag a ring to turn the bone.
  let gizmo = null, outline = null, rings = [], hot = null, dragging = null, lastFrame = -1;
  const RING_AX = ['x', 'y', 'z', 'twist'];
  function makeRing(ax, radius) {
    const col = new THREE.Color(AXC[ax]);
    // the near half bright, the far half faint (clipped at the plane through her joint, facing you)
    const mat = new THREE.MeshBasicMaterial({ color: col, depthTest: false, transparent: true, opacity: 0.85, clippingPlanes: [nearSide] });
    const far = new THREE.MeshBasicMaterial({ color: col, depthTest: false, transparent: true, opacity: 0.18 });
    const g = new THREE.Group();
    const tube = ax === 'twist' ? 0.012 : 0.018;
    const torus = new THREE.TorusGeometry(radius, radius * tube, 6, 64);
    const ring = new THREE.Mesh(torus, mat), back = new THREE.Mesh(torus, far);
    // the cone at the ring's edge, pointing the way + turns (the ring's axis is its local z)
    const cone = new THREE.Mesh(new THREE.ConeGeometry(radius * 0.09, radius * 0.24, 10), mat);
    cone.position.set(radius, 0, 0);
    // a fat invisible ring, easier to grab than the thin one you see
    const grab = new THREE.Mesh(new THREE.TorusGeometry(radius, radius * 0.09, 6, 48), new THREE.MeshBasicMaterial({ visible: false }));
    grab.userData.ax = ax;
    g.add(back, ring, cone, grab);
    for (const o of [back, ring, cone]) { o.renderOrder = 999; o.onBeforeRender = place; o.frustumCulled = false; }   // never culled: they place themselves as they draw
    return { ax, g, mat, far, cone, grab };
  }
  const Q = () => new THREE.Quaternion(), V = (x, y, z) => new THREE.Vector3(x, y, z);
  const nearSide = new THREE.Plane();                        // moved every frame: through the joint, facing the camera
  const qTmp = Q(), qInv = Q(), qx = Q(), qy = Q(), qz = Q(), qt = Q(), pTmp = V();
  const X = V(1, 0, 0), Y = V(0, 1, 0), Z = V(0, 0, 1);
  // where each ring sits this frame, from the bone and the slider numbers
  function place(renderer) {
    const f = renderer.info.render.frame;
    if (f === lastFrame || !gizmo?.visible) return;
    lastFrame = f;
    const node = vrm.humanoid.getNormalizedBoneNode(st.bone);
    if (!node) return;
    node.updateWorldMatrix(true, false);
    node.getWorldPosition(gizmo.position);
    node.getWorldQuaternion(qTmp);                         // the bone as it is now
    const v = view[key(st.bone)] || REST[st.bone] || [0, 0, 0, 0];
    qx.setFromAxisAngle(X, fx * (v[0] || 0)); qy.setFromAxisAngle(Y, v[1] || 0);
    qz.setFromAxisAngle(Z, fx * (v[2] || 0)); qt.setFromAxisAngle(X, fx * (v[3] || 0));
    qInv.copy(qx).multiply(qy).multiply(qz).multiply(qt).invert();
    const base = qTmp.clone().multiply(qInv);              // the bone before its own turn
    const fx_ = base.clone().multiply(qx), fy_ = fx_.clone().multiply(qy), fz_ = fy_.clone().multiply(qz);
    // the ring's own z is the axis it turns about
    const toZ = { x: Q().setFromUnitVectors(Z, X), y: Q().setFromUnitVectors(Z, Y), z: Q() };
    const frames = { x: base.clone().multiply(toZ.x), y: fx_.clone().multiply(toZ.y), z: fy_.clone().multiply(toZ.z), twist: fz_.clone().multiply(toZ.x) };
    for (const r of rings) {
      r.g.quaternion.copy(frames[r.ax]);
      const sgn = r.ax === 'y' ? 1 : fx;                   // + on the slider turns this way about the ring's axis
      r.cone.rotation.set(0, 0, sgn > 0 ? 0 : Math.PI);
      const lit = !hot && !dragging ? 1 : (hot === r.ax || dragging?.ax === r.ax) ? 1.4 : 0.3;
      r.mat.opacity = Math.min(1, 0.85 * lit); r.far.opacity = Math.min(0.4, 0.18 * lit);
    }
    // same size on screen wherever the camera is
    const d = camera.position.distanceTo(gizmo.position);
    gizmo.scale.setScalar(d * Math.tan(THREE.MathUtils.degToRad(camera.fov / 2)) * 0.24);
    // the clip plane sits a touch behind the joint, so a ring facing you stays whole
    renderer.localClippingEnabled = true;
    pTmp.copy(camera.position).sub(gizmo.position).normalize();
    nearSide.setFromNormalAndCoplanarPoint(pTmp, gizmo.position).constant += 0.05 * gizmo.scale.x;
    outline.quaternion.copy(camera.quaternion);              // the outline and the ball always face you
    gizmo.updateMatrixWorld(true);
  }
  function moveGizmo() {
    if (!THREE || !camera) return;
    if (!gizmo) {
      gizmo = new THREE.Group();
      rings = [makeRing('x', 0.5), makeRing('y', 0.5), makeRing('z', 0.5), makeRing('twist', 0.36)];
      const dot = new THREE.Mesh(new THREE.SphereGeometry(0.035, 12, 8), new THREE.MeshBasicMaterial({ color: 0xff6ad5, depthTest: false, transparent: true }));
      dot.renderOrder = 1000; dot.onBeforeRender = place; dot.frustumCulled = false;
      // a soft ball and an outline round it all, so the rings read as one sphere
      outline = new THREE.Group();
      const ball = new THREE.Mesh(new THREE.CircleGeometry(0.5, 48), new THREE.MeshBasicMaterial({ color: 0xffffff, depthTest: false, transparent: true, opacity: 0.05 }));
      const edge = new THREE.Mesh(new THREE.RingGeometry(0.565, 0.575, 64), new THREE.MeshBasicMaterial({ color: 0xd9d4ec, depthTest: false, transparent: true, opacity: 0.35 }));
      for (const o of [ball, edge]) { o.renderOrder = 998; o.onBeforeRender = place; o.frustumCulled = false; }
      outline.add(ball, edge);
      gizmo.add(outline, dot, ...rings.map(r => r.g));
      let top = vrm.scene; while (top.parent) top = top.parent;   // the scene itself: the rings are placed in world space
      top.add(gizmo);
    }
    gizmo.visible = !!vrm.humanoid.getNormalizedBoneNode(st.bone) && showAxes.checked && !win.classList.contains('tucked');
  }
  new MutationObserver(() => moveGizmo()).observe(win, { attributes: true, attributeFilter: ['class'] });   // tucked away: no rings
  // grabbing and dragging a ring
  const ray = new THREE.Raycaster(), ndc = new THREE.Vector2();
  function ringAt(e) {
    if (!gizmo?.visible || !canvas) return null;
    const b = canvas.getBoundingClientRect();
    ndc.set(((e.clientX - b.left) / b.width) * 2 - 1, -((e.clientY - b.top) / b.height) * 2 + 1);
    ray.setFromCamera(ndc, camera);
    const hits = ray.intersectObjects(rings.map(r => r.grab), false);
    const hit = hits.find(h => nearSide.distanceToPoint(h.point) > -0.02 * gizmo.scale.x) || hits[0];   // the near half first
    return hit ? { ...rings.find(r => r.grab === hit.object), point: hit.point } : null;
  }
  function screenOf(p) {
    const b = canvas.getBoundingClientRect(), q = p.clone().project(camera);
    return { x: b.left + (q.x + 1) / 2 * b.width, y: b.top + (1 - q.y) / 2 * b.height };
  }
  const angleAt = (e, c) => Math.atan2(-(e.clientY - c.y), e.clientX - c.x);   // counter-clockwise is +
  if (canvas) {
    addEventListener('pointerdown', e => {
      if (e.button !== 0 || e.target !== canvas) return;
      const r = ringAt(e);
      if (!r) return;
      e.stopPropagation(); e.preventDefault();             // not an orbit, not a click on her
      const axis = V(0, 0, 1).applyQuaternion(r.g.getWorldQuaternion(Q()));
      const toward = axis.dot(pTmp.copy(gizmo.position).sub(camera.position)) < 0;   // the axis points at you
      const c = screenOf(gizmo.position);
      const i = RING_AX.indexOf(r.ax), sgn = r.ax === 'y' ? 1 : fx;
      dragging = { ax: r.ax, i, c, a: angleAt(e, c), from: +sliders[r.ax].n.value || 0, turn: 0, k: (toward ? 1 : -1) * sgn };
      // a ring seen edge-on: going round it makes no sense, so slide along it instead
      const facing = Math.abs(axis.dot(pTmp.copy(camera.position).sub(gizmo.position).normalize()));
      if (facing < 0.35) {
        const arm = r.point.clone().sub(gizmo.position), tan = axis.clone().cross(arm).normalize().multiplyScalar(arm.length() * 0.2);
        const s0 = screenOf(r.point), s1 = screenOf(r.point.clone().add(tan));
        const tx = s1.x - s0.x, ty = s1.y - s0.y, len = Math.hypot(tx, ty) || 1;
        dragging.slide = { x: e.clientX, y: e.clientY, tx: tx / len, ty: ty / len, px: Math.max(30, Math.hypot(s0.x - c.x, s0.y - c.y)), sgn };
      }
      canvas.setPointerCapture?.(e.pointerId);
      remember();                                          // the drag is one undo step (a burst)
    }, true);
    addEventListener('pointermove', e => {
      if (dragging) {
        e.stopPropagation();
        let v;
        if (dragging.slide) {                              // along the ring's edge: a ring's radius of travel is one radian
          const sl = dragging.slide;
          v = dragging.from + ((e.clientX - sl.x) * sl.tx + (e.clientY - sl.y) * sl.ty) / sl.px * sl.sgn;
        } else {
          const a = angleAt(e, dragging.c);
          let d = a - dragging.a; if (d > Math.PI) d -= 2 * Math.PI; if (d < -Math.PI) d += 2 * Math.PI;
          dragging.a = a; dragging.turn += d;
          v = dragging.from + dragging.turn * dragging.k;
        }
        if (e.shiftKey) v = Math.round(v / (Math.PI / 12)) * (Math.PI / 12);   // shift: 15° steps
        sliders[dragging.ax].set(v);
        return;
      }
      if (e.target !== canvas || !gizmo?.visible) { if (hot) hot = null; return; }
      const r = ringAt(e);
      hot = r ? r.ax : null;
      canvas.style.cursor = r ? 'pointer' : '';
    }, true);
    const end = e => { if (!dragging) return; e.stopPropagation(); dragging = null; lastMark = 0; canvas.style.cursor = ''; };
    addEventListener('pointerup', end, true);
    addEventListener('pointercancel', end, true);
  }
  function drawChips() {
    chips.textContent = '';
    const k = keyAt(st.t, false);
    const posed = k ? Object.keys(k.pose).map(b => b.replace(/^\+/, '')) : [];
    if (!posed.length) chips.append(el('span', { className: 'dim', textContent: 'nothing yet' }));
    for (const b of posed.filter(b => !/(Proximal|Intermediate|Distal)$/.test(b))) {
      const c = btn(nice(b).replace(' (+)', ''), () => selectBone(b));
      c.classList.toggle('on', b === st.bone);
      chips.append(c);
    }
    if (posed.some(b => /(Proximal|Intermediate|Distal)$/.test(b))) chips.append(el('span', { className: 'dim', textContent: ' + fingers' }));
  }
  function setHand(c) {
    remember();
    start();
    const k = keyAt(st.t, true);
    const sides = mirror.checked ? ['right', 'left'] : [handSide.value];
    for (const side of sides) Object.assign(k.pose, fingers(side, c));
    show();
  }

  // -- undo ------------------------------------------------------------------------
  const past = [], future = [];
  let lastMark = 0;
  function remember() {                    // one step per burst of changes (a slider drag is one)
    const now = performance.now();
    if (now - lastMark > 600) { past.push(JSON.stringify(A)); if (past.length > 100) past.shift(); future.length = 0; }
    lastMark = now;
  }
  function restore(json) { A = JSON.parse(json); aToForm(); seek(st.t); show(); }
  function undo() { if (!past.length) return say('nothing to undo'); future.push(JSON.stringify(A)); restore(past.pop()); lastMark = 0; say('undone', 1500); }
  function redo() { if (!future.length) return say('nothing to redo'); past.push(JSON.stringify(A)); restore(future.pop()); lastMark = 0; say('redone', 1500); }

  // -- the visual timeline ----------------------------------------------------------
  function drawTimeline(playhead) {
    const W = tl.clientWidth || 380, H = 58, dpr = devicePixelRatio || 1;
    if (tl.width !== W * dpr) { tl.width = W * dpr; tl.height = H * dpr; }
    const g = tl.getContext('2d');
    g.setTransform(dpr, 0, 0, dpr, 0, 0);
    g.clearRect(0, 0, W, H);
    const x = t => 8 + (W - 16) * (t / Math.max(0.2, A.dur));
    g.fillStyle = '#1a1328'; g.fillRect(0, 0, W, H);
    // seconds
    g.strokeStyle = '#3a2d55'; g.fillStyle = '#8880a8'; g.font = '10px system-ui'; g.lineWidth = 1;
    const step = A.dur > 12 ? 2 : A.dur > 5 ? 1 : 0.5;
    for (let t = 0; t <= A.dur + 1e-6; t += step) {
      g.beginPath(); g.moveTo(x(t) + 0.5, 0); g.lineTo(x(t) + 0.5, 10); g.stroke();
      g.fillText(t % 1 ? t.toFixed(1) : String(t), x(t) + 2, 9);
    }
    g.beginPath(); g.moveTo(8, 30.5); g.lineTo(W - 8, 30.5); g.strokeStyle = '#4a3a70'; g.stroke();
    // sound and emotes, under the line
    if (soundSel.value) {
      const from = 0, len = +soundLen.value || A.dur;
      g.fillStyle = '#6ba8ff55'; g.fillRect(x(from), 46, x(Math.min(A.dur, len)) - x(from), 6);
    }
    g.font = '11px system-ui';
    for (const e of A.emote) { g.fillStyle = '#e07ac8'; g.fillText({ hearts: '♥', sweat: '💧', anger: '💢', question: '?' }[e.name] || '•', x(e.at) - 4, 54); }
    // keys
    for (const k of A.keys) {
      const cx = x(k.t), on = near(k.t, st.t);
      g.save(); g.translate(cx, 30.5); g.rotate(Math.PI / 4);
      g.fillStyle = on ? '#ffffff' : '#e07ac8'; g.fillRect(-5, -5, 10, 10);
      g.restore();
    }
    // where you are
    const ph = playhead ?? st.t;
    g.strokeStyle = '#ffd36b'; g.lineWidth = 2;
    g.beginPath(); g.moveTo(x(ph), 12); g.lineTo(x(ph), 44); g.stroke();
  }
  {
    let drag = null;
    const tAt = e => { const r = tl.getBoundingClientRect(); return Math.max(0, Math.min(A.dur, ((e.clientX - r.left - 8) / (r.width - 16)) * A.dur)); };
    tl.addEventListener('pointerdown', e => {
      const t = tAt(e), r = tl.getBoundingClientRect(), px = (A.dur / Math.max(1, r.width - 16)) * 7;
      const k = A.keys.find(k => Math.abs(k.t - t) < px);
      tl.setPointerCapture(e.pointerId);
      if (k) { remember(); drag = k; seek(k.t); start(); } else { drag = null; seek(t); }
    });
    tl.addEventListener('pointermove', e => {
      if (!(e.buttons & 1)) return;
      const t = Math.round(tAt(e) / 0.05) * 0.05;
      if (!drag) return seek(t);
      if (A.keys.some(o => o !== drag && near(o.t, t))) return;
      for (const track of Object.values(A.expr)) if (Array.isArray(track)) for (const p of track) if (near(p[0], drag.t)) p[0] = r2(t);
      drag.t = r2(t); A.keys.sort((a, b) => a.t - b.t); seek(drag.t);
    });
    tl.addEventListener('pointerup', () => { drag = null; });
  }
  function stepKey(d) {
    const ts = A.keys.map(k => k.t);
    const next = d > 0 ? ts.find(t => t > st.t + 0.01) : ts.filter(t => t < st.t - 0.01).pop();
    if (next != null) { seek(next); start(); }
  }
  // keys, while the studio is up and you're not typing
  addEventListener('keydown', e => {
    if (!document.body.classList.contains('debug') || win.classList.contains('tucked') || /^(INPUT|SELECT|TEXTAREA)$/.test(e.target.tagName)) return;
    const k = e.key.toLowerCase();
    if ((e.ctrlKey || e.metaKey) && k === 'z') { e.preventDefault(); return e.shiftKey ? redo() : undo(); }
    if ((e.ctrlKey || e.metaKey) && k === 'y') { e.preventDefault(); return redo(); }
    if (e.ctrlKey || e.metaKey || e.altKey) return;
    if (k === ' ') { e.preventDefault(); st.playing ? stopPlay() : play(); }
    else if (k === 'arrowleft') { e.preventDefault(); stepKey(-1); }
    else if (k === 'arrowright') { e.preventDefault(); stepKey(1); }
    else if (k === 'k') { remember(); start(); keyAt(st.t, true); show(); }
    else if (k === 'delete') deleteKey();
  });

  // -- the timeline ------------------------------------------------------------------
  function seek(t) { st.t = r2(Math.max(0, Math.min(A.dur, t))); time.value = timeN.value = st.t; if (st.on) show(); else { drawKeys(); drawText(); drawChips(); } }
  function drawKeys() {
    drawTimeline();
    keyBox.textContent = '';
    if (!A.keys.length) keyBox.append(el('span', { className: 'dim', textContent: 'no keys yet' }));
    for (const k of A.keys) {
      const b = btn(`${k.t.toFixed(2)}s`, () => { seek(k.t); start(); });
      b.classList.toggle('on', near(k.t, st.t));
      keyBox.append(b);
    }
  }
  let clip = null;
  function copyKey() { const k = keyAt(st.t, false); if (k) { clip = JSON.parse(JSON.stringify(k.pose)); say(`key at ${k.t}s copied`); } }
  function pasteKey() { if (!clip) return say('copy a key first'); remember(); const k = keyAt(st.t, true); k.pose = JSON.parse(JSON.stringify(clip)); start(); show(); }
  function deleteKey() { const i = A.keys.findIndex(k => near(k.t, st.t)); if (i >= 0) { remember(); A.keys.splice(i, 1); show(); } }
  function nudgeKey(d) {
    const k = keyAt(st.t, false);
    if (!k) return say('go to a key first');
    const t = +Math.max(0, k.t + d).toFixed(2);
    if (A.keys.some(o => o !== k && near(o.t, t))) return say('there is a key there already');
    remember();
    for (const track of Object.values(A.expr)) if (Array.isArray(track)) for (const p of track) if (near(p[0], k.t)) p[0] = t;
    k.t = t; A.keys.sort((a, b) => a.t - b.t);
    if (t > A.dur) { A.dur = t; durN.value = t; time.max = t; }
    seek(t);
  }

  // -- playing it -----------------------------------------------------------------------
  function play() {
    if (!A.keys.length) return say('make a key first');
    st.live?.stop(); st.live = null; st.on = false; onOff.textContent = 'start posing'; posingDot.textContent = '';
    GESTURES.__studio = build(false);
    gesture('__studio');
    st.playing = true; playBtn.textContent = '■ stop';
    clearInterval(st.timer);
    st.timer = setInterval(() => {
      const a = moves.state().find(x => x.name === '__studio' && !x.out);
      if (a) { time.value = timeN.value = Math.min(A.dur, a.t).toFixed(2); drawTimeline(Math.min(A.dur, a.t)); return; }
      if (st.loop && st.playing) gesture('__studio'); else stopPlay();
    }, 100);
  }
  function stopPlay() {
    clearInterval(st.timer);
    if (st.playing) moves.stop();
    st.playing = false; playBtn.textContent = '▶ play';
  }
  function playChain() {
    if (!A.chain.length) return say('add gestures to the chain first');
    stop();
    GESTURES.__studio_chain = { chain: A.chain.slice(), ...extras() };
    gesture('__studio_chain');
  }

  // -- details <-> the form --------------------------------------------------------------
  function fillSounds() {
    const cur = soundSel.value || A.sound.name;
    soundSel.textContent = '';
    soundSel.add(new Option('no sound', ''));
    for (const s of sounds) soundSel.add(new Option(s, s));
    if (cur && !sounds.includes(cur)) soundSel.add(new Option(`${cur} (not found)`, cur));
    soundSel.value = cur || '';
  }
  function drawEmotes() {
    emoteBox.textContent = '';
    A.emote.forEach((e, i) => {
      const s = el('select');
      for (const n of EMOTES) s.add(new Option(n, n));
      s.value = e.name; s.onchange = () => { e.name = s.value; };
      const at = el('input', { type: 'number', step: 0.1, min: 0, value: e.at, style: 'width:62px' });
      at.onchange = () => { e.at = Math.max(0, +at.value || 0); };
      emoteBox.append(row('', s, el('span', { className: 'dim', textContent: ' at ' }), at, el('span', { className: 'dim', textContent: 's ' }),
                          btn('✕', () => { A.emote.splice(i, 1); drawEmotes(); })));
    });
  }
  function drawChain() {
    chainBox.textContent = '';
    if (!A.chain.length) chainBox.append(el('div', { className: 'dim', textContent: 'nothing linked yet' }));
    A.chain.forEach((n, i) => chainBox.append(el('div', { className: 'row' },
      el('span', { className: 'l', textContent: `${i + 1}. ` }), el('b', { textContent: n + ' ' }),
      btn('↑', () => { if (i) { [A.chain[i - 1], A.chain[i]] = [A.chain[i], A.chain[i - 1]]; drawChain(); } }),
      btn('↓', () => { if (i < A.chain.length - 1) { [A.chain[i + 1], A.chain[i]] = [A.chain[i], A.chain[i + 1]]; drawChain(); } }),
      btn('✕', () => { A.chain.splice(i, 1); drawChain(); }))));
  }
  function fillLists() {
    const names = Object.keys(GESTURES).filter(n => !n.startsWith('__') && !n.endsWith('_left')).sort();
    for (const s of [loadSel.el, linkSel]) {
      const cur = s.value;
      s.textContent = '';
      s.add(new Option(s === linkSel ? 'a gesture…' : 'open a gesture…', ''));
      for (const n of names) if (s !== linkSel || !GESTURES[n].chain) s.add(new Option(n + (GESTURES[n].chain ? ' ⛓' : ''), n));
      s.value = cur;
    }
  }
  function loadSel() { loadSel.el = el('select'); return loadSel.el; }
  function formToA() {
    A.name = nameIn.value.trim(); A.about = aboutIn.value.trim(); A.keywords = kwIn.value;
    A.fade = [Math.max(0, +fadeIn.value || 0), Math.max(0, +fadeOut.value || 0)];
    for (const f of Object.keys(flagBoxes)) A[f] = flagBoxes[f].checked;
    A.touch = ZONES.filter(z => zoneBoxes[z].checked);
    A.moods = [...BANDS.filter(b => bandBoxes[b].checked), ...moodIn.value.split(',').map(s => s.trim()).filter(Boolean)];
    A.sound = { name: soundSel.value, from: soundFrom.value.trim(), len: soundLen.value };
    A.tail = tailSel.value; A.tailLevel = +tailLvl.value;
  }
  function aToForm() {
    nameIn.value = A.name; aboutIn.value = A.about; kwIn.value = A.keywords;
    fadeIn.value = A.fade[0]; fadeOut.value = A.fade[1];
    for (const f of Object.keys(flagBoxes)) flagBoxes[f].checked = !!A[f];
    for (const z of ZONES) zoneBoxes[z].checked = A.touch.includes(z);
    for (const b of BANDS) bandBoxes[b].checked = A.moods.includes(b);
    moodIn.value = A.moods.filter(m => !BANDS.includes(m)).join(', ');
    fillSounds(); soundSel.value = A.sound.name || ''; soundFrom.value = A.sound.from ?? ''; soundLen.value = A.sound.len ?? '';
    tailSel.value = A.tail; tailLvl.value = A.tailLevel;
    durN.value = A.dur; time.max = A.dur;
    drawEmotes(); drawChain(); drawPropUse();
  }
  function refreshAll() { aToForm(); seek(0); show(); }

  // what goes in the file besides the motion
  function extras() {
    formToA();
    const g = {};
    if (A.about) g.about = A.about;
    const kw = A.keywords.split(',').map(s => s.trim()).filter(Boolean);
    if (kw.length) g.keywords = kw;
    for (const f of ['private', 'lewd', 'full', 'idle']) if (A[f]) g[f] = true;
    if (A.touch.length) g.touch = A.touch;
    if (A.moods.length) g.moods = A.moods;
    if (A.sound.name) {
      const s = { name: A.sound.name };
      if (A.sound.from) s.from = A.sound.from === 'random' ? 'random' : +A.sound.from || 0;
      if (+A.sound.len) s.len = +A.sound.len;
      g.sound = s;
    }
    if (A.emote.length) g.emote = A.emote.map(e => ({ name: e.name, at: e.at }));
    if (A.tail === 'wag') g.wag = A.tailLevel;
    if (A.tail === 'tail_up') g.tail_up = A.tailLevel;
    return { ...A.extra, ...g };
  }
  function build(chain) {
    const g = extras();
    if (chain) return { ...g, chain: A.chain.slice() };
    const expr = {};
    for (const [f, v] of Object.entries(A.expr)) if (!Array.isArray(v) || v.length) expr[f] = v;
    return { ...g, dur: A.dur, fade: A.fade, keys: asKeys(), expr };
  }

  // -- open an existing gesture ------------------------------------------------------------
  function load() {
    const n = loadSel.el.value, g = GESTURES[n];
    if (!g) return;
    stop();
    A = fresh();
    A.name = n; A.about = g.about || ''; A.keywords = (g.keywords || []).join(', ');
    A.fade = (g.fade || [0.4, 0.5]).slice();
    for (const f of ['private', 'lewd', 'full', 'idle']) A[f] = !!g[f];
    A.touch = (g.touch || []).slice(); A.moods = (g.moods || []).slice();
    const s = typeof g.sound === 'string' ? { name: g.sound } : g.sound || {};
    A.sound = { name: s.name || '', from: s.from ?? '', len: s.len ?? '' };
    A.emote = [].concat(g.emote || []).map(e => (typeof e === 'string' ? { name: e, at: 0 } : { name: e.name, at: +e.at || 0 }));
    if (g.tail_up) { A.tail = 'tail_up'; A.tailLevel = g.tail_up; } else if (g.wag) { A.tail = 'wag'; A.tailLevel = g.wag; }
    for (const k of ['then', 'left', 'osc', 'add', 'prop', 'prop_at', 'hold']) if (g[k] != null) A.extra[k] = g[k];
    if (g.prop && propSel) { propSel.value = g.prop; fillProps().then(pickProp); }
    if (g.chain) {
      A.chain = g.chain.slice();
      tabsRow.children[3].click();
    } else if (Array.isArray(g.keys)) {
      A.dur = +g.dur || 3;
      A.keys = g.keys.map(([t, p]) => ({ t: +t, pose: JSON.parse(JSON.stringify(p)) }));
      for (const [f, v] of Object.entries(g.expr || {})) A.expr[f] = Array.isArray(v) ? v.map(p => p.slice()) : v;
      tabsRow.children[1].click();
    } else return say(`${n} isn't a pose animation (a turn or a clip) - nothing to edit`);
    if (g.sob) say('note: this one sobs (shoulder hitches) - that part isn\'t kept on save', 8000);
    refreshAll();
    say(`opened ${n}`);
  }

  // -- save ------------------------------------------------------------------------------------
  async function saveIt(asNew, chain = false) {
    formToA();
    let name = A.name;
    if (asNew || !name) {
      name = (prompt('Save as (lower-case letters, numbers and _):', name || '') || '').trim().toLowerCase();
      if (!name) return;
      nameIn.value = A.name = name;
    }
    if (!chain && !A.keys.length) return say('nothing to save - make a key first');
    if (chain && !A.chain.length) return say('nothing to save - link some gestures first');
    const body = { name, ...build(chain) };
    const post = overwrite => fetch('gestures/save', { method: 'POST', headers: { 'Content-Type': 'application/json' },
                                                        body: JSON.stringify({ ...body, overwrite }) });
    try {
      let r = await post(false), j = await r.json();
      if (r.status === 409 && confirm(`${name} already exists. Replace it? (the old one is kept in gestures/backup/)`)) { r = await post(true); j = await r.json(); }
      if (!j.ok) return say(j.error || 'not saved', 8000);
      GESTURES[name] = (await import(`./gestures/${name}.js?v=${Date.now()}`)).default;   // playable now; in every menu after a reload
      fillLists();
      say(`saved gestures/${name}.js`, 8000);
    } catch (e) {
      say(`couldn't save: ${e.message || e}`, 8000);
    }
  }

  fillLists(); fillSounds(); refreshAll();
  // a reload (another model, the hologram, ...) keeps what you were making
  const DRAFT = 'luna.studio.draft';
  addEventListener('pagehide', () => {
    try {
      formToA();
      const tab = [...tabsRow.children].findIndex(b => b.classList.contains('on'));
      sessionStorage.setItem(DRAFT, JSON.stringify({ A, t: st.t, bone: st.bone, on: st.on, tab, mirror: mirror.checked }));
    } catch (_) {}
  });
  try {
    const d = JSON.parse(sessionStorage.getItem(DRAFT) || 'null');
    if (d?.A) {
      A = { ...fresh(), ...d.A };
      refreshAll(); seek(d.t || 0);
      if (bones.includes(d.bone)) selectBone(d.bone);
      mirror.checked = !!d.mirror;
      tabsRow.children[d.tab]?.click();
      if (d.on) start();
      if (A.keys.length || A.chain.length) say('picked up where you were', 3000);
    }
  } catch (_) {}
  return {
    get active() { return st.on; },
    show: () => winCtl.show(),
    pick(bone) {
      if (!bone || !bones.includes(bone)) return;
      selectBone(bone);
      tabsRow.children[0].click();
    },
  };
}
