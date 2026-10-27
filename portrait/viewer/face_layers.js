// Luna's portrait: the layers drawn on her face that VRoid doesn't have as
// shapes - blush, tears and drool, and the brows.
//
// Split out of portrait.js; it reaches back for what it needs through ctx.

import { THREE } from './vendor/luna-three.js';

// What this borrows from portrait.js, read live (see bindFaceLayers there).
let ctx = null;
export function bindFaceLayers(c) { ctx = c; }

// Blush. VRoid paints the cheeks into the face texture, so there's no
// expression to turn up; instead a second copy of the face skin, sharing
// its skeleton and shape keys, carries a pink glow painted in the face's
// own texture layout and fades in over the cheeks. It moves with every
// expression because it is the same face. A model with its own "blush"
// expression uses that instead.
//
// What raises it: a gesture that asks (hug, kiss, shy), a big jump in
// warmth (flustered, then fading), and a little while warmth stays high.
// luna.json, "vrm": {"blush": {"left": [u, v], "right": [u, v], "size": 0.075,
//                               "color": "#ff5f86", "strength": 0.65}}
// (u, v from the top-left of the face texture; the default is VRoid's.)
export const blush = { now: 0, gesture: 0, fluster: 0, mood: 0, layer: null, tried: false, test: null };
function blushLayer() {
  if (blush.tried) return blush.layer;
  blush.tried = true;
  const o = ctx.cfg.vrm?.blush || {};
  let skin = null;
  ctx.vrm.scene.traverse(m => {
    if (!skin && m.isSkinnedMesh && !m.userData.overlay && [].concat(m.material).some(x => /face.*skin|skin.*face/i.test(x.name || ''))) skin = m;
  });
  if (!skin || o.enabled === false) return null;
  const S = 512, cv = document.createElement('canvas');
  cv.width = cv.height = S;
  const g = cv.getContext('2d');
  const col = new THREE.Color(o.color || '#ff5f86'), [r, gg, b] = [col.r, col.g, col.b].map(x => Math.round(x * 255));
  for (const [u, v] of [o.left || [0.33, 0.61], o.right || [0.67, 0.61]]) {
    const rad = (o.size || 0.075) * S;
    const grad = g.createRadialGradient(u * S, v * S, 0, u * S, v * S, rad);
    grad.addColorStop(0, `rgba(${r},${gg},${b},0.75)`);
    grad.addColorStop(0.45, `rgba(${r},${gg},${b},0.38)`);
    grad.addColorStop(1, `rgba(${r},${gg},${b},0)`);
    g.fillStyle = grad;
    g.beginPath(); g.ellipse(u * S, v * S, rad * 1.25, rad, 0, 0, Math.PI * 2); g.fill();
  }
  const tex = new THREE.CanvasTexture(cv);
  tex.flipY = false;                       // glTF texture layout
  tex.colorSpace = THREE.SRGBColorSpace;
  const mat = new THREE.MeshBasicMaterial({ map: tex, transparent: true, opacity: 0, depthWrite: false,
                                            polygonOffset: true, polygonOffsetFactor: -2, polygonOffsetUnits: -4 });
  const layer = new THREE.SkinnedMesh(skin.geometry, mat);
  layer.userData.overlay = true;
  layer.bind(skin.skeleton, skin.bindMatrix);
  layer.morphTargetInfluences = skin.morphTargetInfluences;      // same array: same expression, always
  layer.morphTargetDictionary = skin.morphTargetDictionary;
  layer.frustumCulled = false;
  layer.renderOrder = (skin.renderOrder || 0) + 1;
  skin.parent.add(layer);
  layer.position.copy(skin.position); layer.quaternion.copy(skin.quaternion); layer.scale.copy(skin.scale);
  blush.layer = { mesh: layer, mat, strength: o.strength ?? 0.65 };
  return blush.layer;
}
export function updateBlush(dt) {
  blush.fluster = Math.max(0, blush.fluster - dt / 7);                 // flustered fades over ~7 s
  const warm = Math.max(0, (ctx.mind.warmth - 0.6) * 0.9);
  const target = blush.test ?? Math.min(1, Math.max(blush.gesture, blush.fluster, blush.mood, warm));
  blush.now = ctx.damp(blush.now, target, target > blush.now ? 2.5 : 0.8, dt);   // rises quicker than it fades
  if (ctx.has.has('blush')) { ctx.vrm.expressionManager.setValue('blush', blush.now); return; }
  const l = blushLayer();
  if (l) { l.mat.opacity = blush.now * l.strength; l.mesh.visible = blush.now > 0.01; }
}

// Tears. The same trick as the blush: a copy of the face skin that moves
// with every expression, carrying a texture painted in the face's own
// layout - here redrawn as she cries: a wet shine on the lower lids, then
// streaks that grow down her cheeks with drops running along them.
// What brings them: the cry gesture, or staying deeply sad for a while.
// luna.json, "vrm": {"tears": {"left": [u, v], "right": [u, v], "length": 0.3}}
// (where each tear starts, below the eye; the default is VRoid's layout).
// The same layer carries drool: a gesture's "drool" channel (0..1) draws a
// glossy strand from the corner of her mouth, "vrm": {"drool": {"start":
// [u, v], "length": 0.07}} (default: VRoid's left mouth corner).
export const tears = { now: 0, gesture: 0, sadFor: 0, layer: null, tried: false, test: null, drops: [] };
export const drool = { now: 0, gesture: 0, test: null };
function tearLayer() {
  if (tears.tried) return tears.layer;
  tears.tried = true;
  let skin = null;
  ctx.vrm.scene.traverse(m => {
    if (!skin && m.isSkinnedMesh && m.renderOrder !== 1000 && !m.userData.overlay
        && [].concat(m.material).some(x => /face.*skin|skin.*face/i.test(x.name || ''))) skin = m;
  });
  if (!skin) return null;
  const cv = document.createElement('canvas');
  cv.width = cv.height = 512;
  const tex = new THREE.CanvasTexture(cv);
  tex.flipY = false;
  tex.colorSpace = THREE.SRGBColorSpace;
  const mat = new THREE.MeshBasicMaterial({ map: tex, transparent: true, opacity: 1, depthWrite: false,
                                            polygonOffset: true, polygonOffsetFactor: -3, polygonOffsetUnits: -6 });
  const layer = new THREE.SkinnedMesh(skin.geometry, mat);
  layer.userData.overlay = true;
  layer.bind(skin.skeleton, skin.bindMatrix);
  layer.morphTargetInfluences = skin.morphTargetInfluences;
  layer.morphTargetDictionary = skin.morphTargetDictionary;
  layer.frustumCulled = false;
  layer.renderOrder = (skin.renderOrder || 0) + 2;
  skin.parent.add(layer);
  layer.position.copy(skin.position); layer.quaternion.copy(skin.quaternion); layer.scale.copy(skin.scale);
  const o = ctx.cfg.vrm?.tears || {};
  tears.layer = { mesh: layer, tex, g: cv.getContext('2d'),
                  starts: [o.left || [0.335, 0.565], o.right || [0.665, 0.565]], length: o.length || 0.3 };
  return tears.layer;
}
export function updateTears(dt, now) {
  // deeply sad for ~6 s brings tears on its own
  tears.sadFor = ctx.moodNow.sad > 0.55 ? tears.sadFor + dt : Math.max(0, tears.sadFor - dt * 2);
  const target = tears.test ?? Math.min(1, Math.max(tears.gesture, tears.sadFor > 6 ? Math.min(1, (tears.sadFor - 6) / 4) : 0));
  tears.now = ctx.damp(tears.now, target, target > tears.now ? 0.9 : 0.35, dt);    // well up slowly, dry slower
  const dTarget = drool.test ?? drool.gesture;
  drool.now = ctx.damp(drool.now, dTarget, dTarget > drool.now ? 4 : 1.5, dt);
  const exprTears = ctx.has.has('tears');
  if (exprTears) ctx.vrm.expressionManager.setValue('tears', tears.now);
  const showTears = !exprTears && ctx.cfg.vrm?.tears?.enabled !== false && tears.now > 0.01;
  const showDrool = ctx.cfg.vrm?.drool?.enabled !== false && drool.now > 0.01;
  if (!showTears) tears.drops.length = 0;
  const l = showTears || showDrool ? tearLayer() : tears.layer;
  if (!l) return;
  l.mesh.visible = showTears || showDrool;
  if (!l.mesh.visible) return;
  const g = l.g, S = 512, k = tears.now;
  g.clearRect(0, 0, S, S);
  if (showDrool) drawDrool(g, S, drool.now);
  if (!showTears) { l.tex.needsUpdate = true; return; }
  // drops: born at the lid every so often, sliding down and slowing
  if (k > 0.35 && Math.random() < dt * 1.4 * k) {
    const side = Math.random() < 0.5 ? 0 : 1;
    tears.drops.push({ side, y: 0, v: 0.05 + Math.random() * 0.04, wob: Math.random() * 6 });
  }
  for (const [i, [u, v]] of l.starts.entries()) {
    const x = u * S, y0 = v * S, len = l.length * S * Math.min(1, k * 1.3), dir = i === 0 ? 1 : -1;
    // wet lower lid: a soft, bright line
    const lid = g.createRadialGradient(x, y0, 0, x, y0, 30);
    lid.addColorStop(0, `rgba(150,200,255,${0.6 * k})`);
    lid.addColorStop(1, 'rgba(225,240,255,0)');
    g.fillStyle = lid;
    g.beginPath(); g.ellipse(x, y0, 30, 7, 0, 0, Math.PI * 2); g.fill();
    // the streak: thin, glossy, curving slightly outward as it runs down
    if (k > 0.25) {
      const path = t => [x + dir * -Math.sin(t * 1.4) * 6, y0 + t * len];
      const grad = g.createLinearGradient(x, y0, x, y0 + len);
      grad.addColorStop(0, `rgba(120,175,250,${0.85 * k})`);
      grad.addColorStop(0.85, `rgba(120,175,250,${0.6 * k})`);
      grad.addColorStop(1, 'rgba(120,175,250,0)');
      g.strokeStyle = grad; g.lineWidth = 7; g.lineCap = 'round';
      g.beginPath();
      for (let t = 0; t <= 1.001; t += 0.05) { const [px, py] = path(t); t ? g.lineTo(px, py) : g.moveTo(px, py); }
      g.stroke();
      g.strokeStyle = `rgba(255,255,255,${0.6 * k})`; g.lineWidth = 2;    // highlight down its middle
      g.beginPath();
      for (let t = 0; t <= 0.9; t += 0.05) { const [px, py] = path(t); t ? g.lineTo(px - dir, py) : g.moveTo(px - dir, py); }
      g.stroke();
      for (const d of tears.drops) {
        if (d.side !== i) continue;
        const [px, py] = path(Math.min(1.15, d.y));
        g.fillStyle = `rgba(110,170,250,${0.9 * k * Math.max(0, 1 - Math.max(0, d.y - 0.9) * 4)})`;
        g.beginPath(); g.ellipse(px, py, 5.5, 8, 0, 0, Math.PI * 2); g.fill();
        g.fillStyle = `rgba(255,255,255,${0.9 * k})`;
        g.beginPath(); g.arc(px - 1.3, py - 2, 1.4, 0, Math.PI * 2); g.fill();
      }
    }
  }
  for (const d of tears.drops) { d.y += d.v * dt * 6 * (1 - Math.min(0.6, d.y * 0.5)); }
  tears.drops = tears.drops.filter(d => d.y < 1.3);
  l.tex.needsUpdate = true;
}

// A strand from the corner of her mouth: grows down as the channel rises,
// thin and glossy, with a bead gathering at its end.
function drawDrool(g, S, k) {
  const o = ctx.cfg.vrm?.drool || {}, [u, v] = o.start || [0.552, 0.762];
  const x = u * S, y0 = v * S, len = (o.length || 0.07) * S * Math.min(1, k * 1.2);
  const path = t => [x + Math.sin(t * 2.2) * 2.5 + t * 3, y0 + t * len];
  const line = (w, style, to = 1.001, dx = 0) => {
    g.strokeStyle = style; g.lineWidth = w; g.lineCap = 'round'; g.beginPath();
    for (let t = 0; t <= to; t += 0.05) { const [px, py] = path(t); t ? g.lineTo(px + dx, py) : g.moveTo(px + dx, py); }
    g.stroke();
  };
  line(6, `rgba(150,165,215,${0.35 * k})`);                               // a faint edge, so it reads on pale skin
  const strand = g.createLinearGradient(x, y0, x, y0 + len);
  strand.addColorStop(0, `rgba(235,242,255,${0.9 * k})`);
  strand.addColorStop(1, `rgba(220,232,255,${0.75 * k})`);
  line(4, strand);
  line(1.4, `rgba(255,255,255,${0.95 * k})`, 0.85, -0.9);                  // the shine down it
  const [bx, by] = path(1), r = 3 + 3 * k;                                 // the bead
  g.fillStyle = `rgba(150,165,215,${0.35 * k})`;
  g.beginPath(); g.ellipse(bx, by + r * 0.4, r * 0.85 + 1.2, r + 1.2, 0, 0, Math.PI * 2); g.fill();
  g.fillStyle = `rgba(225,236,255,${0.9 * k})`;
  g.beginPath(); g.ellipse(bx, by + r * 0.4, r * 0.85, r, 0, 0, Math.PI * 2); g.fill();
  g.fillStyle = `rgba(255,255,255,${0.95 * k})`;
  g.beginPath(); g.arc(bx - r * 0.3, by, r * 0.3, 0, Math.PI * 2); g.fill();
}

// Brows through the bangs, the anime way: a copy of the brows drawn over
// the hair, sharing the face's skeleton and shape keys. Faint normally,
// stronger when she's cross or sad, so her brows can actually say it.
// "vrm": {"brows_over_hair": 0..1} in luna.json sets the resting strength (0 = off).
const brows = { layer: null, tried: false };
function browLayer() {
  if (brows.tried) return brows.layer;
  brows.tried = true;
  let src = null;
  ctx.vrm.scene.traverse(m => { if (!src && m.isSkinnedMesh && /facebrow/i.test([].concat(m.material)[0]?.name || '')) src = m; });
  if (!src || (ctx.cfg.vrm?.brows_over_hair ?? 0.35) <= 0 && ctx.cfg.vrm?.brows_over_hair !== undefined) return null;
  const from = [].concat(src.material)[0];
  const mat = new THREE.MeshBasicMaterial({ map: from.map, color: 0x6e3550, transparent: true, opacity: 0,
                                            depthTest: false, depthWrite: false, alphaTest: 0.05 });
  const layer = new THREE.SkinnedMesh(src.geometry, mat);
  layer.bind(src.skeleton, src.bindMatrix);
  layer.morphTargetInfluences = src.morphTargetInfluences;
  layer.morphTargetDictionary = src.morphTargetDictionary;
  layer.frustumCulled = false;
  layer.renderOrder = 1000;          // after the hair (VRM sets its own orders in the teens)
  src.parent.add(layer);
  layer.position.copy(src.position); layer.quaternion.copy(src.quaternion); layer.scale.copy(src.scale);
  brows.layer = { mesh: layer, mat };
  return brows.layer;
}
const _hf = new THREE.Vector3(), _hc = new THREE.Vector3(), _hp = new THREE.Vector3();
export function updateBrows() {
  const l = browLayer();
  if (!l) return;
  const rest = ctx.cfg.vrm?.brows_over_hair ?? 0.35;
  // only from the front: from behind they'd show through her head
  const head = ctx.vrm.humanoid.getNormalizedBoneNode('head');
  head.getWorldPosition(_hp);
  _hf.set(0, 0, ctx.fx).applyQuaternion(head.getWorldQuaternion(new THREE.Quaternion()));
  _hc.copy(ctx.camera.position).sub(_hp).normalize();
  const facing = Math.max(0, Math.min(1, (_hf.dot(_hc) - 0.2) * 2.5));
  l.mat.opacity = Math.min(1, rest + ctx.moodNow.angry * 0.9 + ctx.moodNow.sad * 0.6) * facing;
  l.mesh.visible = l.mat.opacity > 0.01;
}

