// Pose studio (debug viewer only): pose her with sliders and copy the numbers
// into a gesture file. Click a part of her to pick that bone, or pick from the
// list; drag x / y / z / twist; Copy gives the line to paste. Start from any
// gesture at any moment of it. The pose plays through the gesture engine
// (moves.studio), so what you see is exactly what a gesture file would do.
//
// Torso and head bones are '+' (added on top of her breathing and posture,
// the way gesture files write them); arms, legs, hands and fingers are set
// outright. Mirror poses the other side to match (left = right with y and z
// flipped).
import { mirrorName } from './gestures/_pose.js';

const ADDED = new Set(['hips', 'spine', 'chest', 'upperChest', 'neck', 'head']);
const FACE = ['blush', 'happy', 'relaxed', 'sad', 'angry', 'surprised', 'aa', 'ou', 'blink'];
const r3 = v => Math.round(v * 100) / 100;

export function createStudio({ vrm, moves, GESTURES, box }) {
  const bones = Object.keys(vrm.humanoid.humanBones)
    .filter(n => vrm.humanoid.getNormalizedBoneNode(n) && !/Eye|jaw/.test(n));
  const key = b => (ADDED.has(b) ? '+' + b : b);           // 'spine' -> '+spine'
  const st = { on: false, pose: {}, expr: {}, live: null, bone: 'rightUpperArm', mirror: false };

  // -- the panel ------------------------------------------------------------
  const el = (tag, props = {}, ...kids) => { const n = Object.assign(document.createElement(tag), props); n.append(...kids); return n; };
  const h = el('h4', { textContent: 'pose studio' });
  const wrap = el('div');
  box.after(h, wrap);

  const toggle = el('button', { textContent: 'start posing' });
  const from = el('select'), at = el('input', { type: 'range', min: 0, max: 1, step: 0.01, value: 0, style: 'width:90px' });
  const grab = el('button', { textContent: 'start from it' });
  from.add(new Option('start from a gesture…', ''));
  for (const n of Object.keys(GESTURES).filter(n => Array.isArray(GESTURES[n].keys) && !n.endsWith('_left')).sort()) from.add(new Option(n, n));
  const atLabel = el('span', { className: 'dim' });
  const pick = el('select');
  for (const b of bones) pick.add(new Option(ADDED.has(b) ? `${b} (+)` : b, b));
  pick.value = st.bone;
  const mirror = el('label', {}, el('input', { type: 'checkbox' }), ' mirror');
  const sliders = {};
  const rows = el('div');
  for (const [i, ax] of ['x', 'y', 'z', 'twist'].entries()) {
    const r = el('input', { type: 'range', min: -3.14, max: 3.14, step: 0.01, value: 0, style: 'width:170px' });
    const n = el('input', { type: 'number', step: 0.01, value: 0, style: 'width:58px' });
    r.oninput = () => { n.value = r.value; set(i, +r.value); };
    n.onchange = () => { r.value = n.value; set(i, +n.value); };
    sliders[ax] = { r, n };
    rows.append(el('div', {}, el('span', { textContent: ax.padEnd(6), style: 'display:inline-block;width:42px' }), r, n));
  }
  const face = el('details', {}, el('summary', { textContent: 'face' }));
  for (const f of FACE) {
    const r = el('input', { type: 'range', min: 0, max: 1, step: 0.05, value: 0, style: 'width:150px' });
    r.oninput = () => { if (+r.value) st.expr[f] = +r.value; else delete st.expr[f]; out(); };
    face.append(el('div', {}, el('span', { textContent: f, style: 'display:inline-block;width:70px' }), r));
  }
  const copyBone = el('button', { textContent: 'copy bone' }), copyAll = el('button', { textContent: 'copy pose' });
  const resetBone = el('button', { textContent: 'reset bone' }), clear = el('button', { textContent: 'clear all' });
  const text = el('pre', { style: 'user-select:text' });
  wrap.append(
    el('div', { className: 'dim', textContent: 'click a part of her, or pick a bone · drag to pose · copy into a gesture file' }),
    el('div', {}, toggle),
    el('div', {}, from, at, atLabel, grab),
    el('div', {}, pick, mirror), rows, face,
    el('div', {}, copyBone, copyAll, resetBone, clear), text);

  // -- doing it -------------------------------------------------------------
  function start() {
    if (st.on) return;
    st.on = true; toggle.textContent = 'stop posing';
    st.live = moves.studio(st.pose, st.expr);
  }
  function stop() {
    st.on = false; toggle.textContent = 'start posing';
    st.live?.stop(); st.live = null;
  }
  toggle.onclick = () => (st.on ? stop() : start());

  function show() {                                     // sliders follow the picked bone
    const v = st.pose[key(st.bone)] || [0, 0, 0, 0];
    ['x', 'y', 'z', 'twist'].forEach((ax, i) => { sliders[ax].r.value = sliders[ax].n.value = r3(v[i] || 0); });
    out();
  }
  function set(i, v) {
    start();
    const k = key(st.bone);
    const cur = (st.pose[k] || [0, 0, 0]).slice();
    while (cur.length <= i) cur.push(0);
    cur[i] = v;
    if (cur.length === 4 && !cur[3]) cur.pop();         // no twist: three numbers, like the files
    st.pose[k] = cur;
    if (mirror.firstChild.checked && /^(left|right)/.test(st.bone)) {
      st.pose[mirrorName(k)] = cur.length > 3 ? [cur[0], -cur[1], -cur[2], cur[3]] : [cur[0], -cur[1], -cur[2]];
    }
    st.live?.refresh();
    out();
  }
  function line(k) { return `${/^[+]/.test(k) ? `'${k}'` : k}: [${st.pose[k].map(r3).join(', ')}],`; }
  function out() {
    const ks = Object.keys(st.pose);
    const face = Object.entries(st.expr).map(([f, v]) => `${f}: ${v}`).join(', ');
    text.textContent = (ks.length ? `{ ${ks.map(line).join('\n  ')} }` : '(nothing posed yet)') + (face ? `\nexpr: { ${face} }` : '');
  }
  const copy = s => navigator.clipboard?.writeText(s).catch(() => {});

  pick.onchange = () => { st.bone = pick.value; show(); };
  mirror.firstChild.onchange = () => { st.mirror = mirror.firstChild.checked; };
  copyBone.onclick = () => { const k = key(st.bone); if (st.pose[k]) copy(line(k)); };
  copyAll.onclick = () => copy(text.textContent);
  resetBone.onclick = () => { delete st.pose[key(st.bone)]; if (st.mirror) delete st.pose[mirrorName(key(st.bone))]; st.live?.refresh(); show(); };
  clear.onclick = () => { for (const k of Object.keys(st.pose)) delete st.pose[k]; for (const k of Object.keys(st.expr)) delete st.expr[k];
                          face.querySelectorAll('input').forEach(i => { i.value = 0; }); st.live?.refresh(); show(); };
  const dur = () => +(GESTURES[from.value]?.dur) || 1;
  at.oninput = () => { atLabel.textContent = from.value ? ` ${(at.value * dur()).toFixed(1)}s ` : ''; };
  from.onchange = at.oninput;
  grab.onclick = () => {
    if (!from.value) return;
    for (const k of Object.keys(st.pose)) delete st.pose[k];
    Object.assign(st.pose, moves.poseAt(from.value, at.value * dur()));
    start(); st.live?.refresh(); show();
  };
  show();

  return {
    get active() { return st.on; },
    pick(bone) {                                        // a click on her picks the bone under it
      if (!bone || !bones.includes(bone)) return;
      st.bone = bone; pick.value = bone; show();
    },
  };
}
