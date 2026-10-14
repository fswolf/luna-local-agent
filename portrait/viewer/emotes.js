// Emotes: little things that pop up beside her head - hearts when she's
// touched, a sweat drop when she's embarrassed, an anger mark when she's
// cross, a question mark when she's curious or puzzled. They're overlays,
// never part of the model, and always drawn in front of her.
//
// Each emote is drawn in code unless there's a sprite sheet for it:
// portrait/emotes/<name>.png, frames side by side in one row, square
// unless portrait/emotes/<name>.json says otherwise:
//   {"frames": 8, "fps": 12, "size": 0.05, "count": 3, "motion": "float"}
// size: metres beside her head. count: how many in one burst.
// motion: float (drift up and fade), slide (slip down), throb (pulse in
// place), bob (pop up and bob). A new name defaults to float.

// Where they sit (x out from the head, y up, metres as the camera sees
// her) and how they move. Sprite sheets use the same, by motion.
const MOTION = {
  float: { x: 0.14, y: 0.09, life: 3.8, count: 3 },   // hearts
  slide: { x: 0.075, y: 0.075, life: 2.4, count: 1 }, // sweat drop, on her temple
  throb: { x: 0.08, y: 0.14, life: 2.4, count: 1 },   // anger mark, at the top of her head
  bob:   { x: 0.12, y: 0.19, life: 2.8, count: 1 },   // question mark, above her ear
};

const outline = (g, s, path, fill) => {
  g.lineJoin = 'round';
  g.lineWidth = s * 0.07;
  g.strokeStyle = '#fff4f8';
  g.stroke(path);
  g.fillStyle = fill;
  g.fill(path);
};

const DRAWN = {
  hearts: { motion: 'float', size: 0.045, draw(g, s) {
    const p = new Path2D();
    p.moveTo(s * 0.5, s * 0.86);
    p.bezierCurveTo(s * 0.12, s * 0.6, s * 0.04, s * 0.36, s * 0.16, s * 0.22);
    p.bezierCurveTo(s * 0.28, s * 0.08, s * 0.46, s * 0.12, s * 0.5, s * 0.3);
    p.bezierCurveTo(s * 0.54, s * 0.12, s * 0.72, s * 0.08, s * 0.84, s * 0.22);
    p.bezierCurveTo(s * 0.96, s * 0.36, s * 0.88, s * 0.6, s * 0.5, s * 0.86);
    const fill = g.createLinearGradient(0, s * 0.1, 0, s * 0.86);
    fill.addColorStop(0, '#ff7fa8');
    fill.addColorStop(1, '#e8346a');
    outline(g, s, p, fill);
    g.fillStyle = 'rgba(255,255,255,0.75)';
    g.beginPath();
    g.ellipse(s * 0.3, s * 0.3, s * 0.07, s * 0.045, -0.7, 0, Math.PI * 2);
    g.fill();
  } },

  // the big anime sweat drop
  sweat: { motion: 'slide', size: 0.05, draw(g, s) {
    const p = new Path2D();
    p.moveTo(s * 0.5, s * 0.08);
    p.bezierCurveTo(s * 0.62, s * 0.34, s * 0.8, s * 0.5, s * 0.8, s * 0.66);
    p.bezierCurveTo(s * 0.8, s * 0.84, s * 0.66, s * 0.94, s * 0.5, s * 0.94);
    p.bezierCurveTo(s * 0.34, s * 0.94, s * 0.2, s * 0.84, s * 0.2, s * 0.66);
    p.bezierCurveTo(s * 0.2, s * 0.5, s * 0.38, s * 0.34, s * 0.5, s * 0.08);
    const fill = g.createLinearGradient(0, s * 0.1, 0, s * 0.94);
    fill.addColorStop(0, '#d8f2ff');
    fill.addColorStop(1, '#6cc4f0');
    outline(g, s, p, fill);
    g.fillStyle = 'rgba(255,255,255,0.85)';
    g.beginPath();
    g.ellipse(s * 0.38, s * 0.66, s * 0.05, s * 0.1, 0.3, 0, Math.PI * 2);
    g.fill();
  } },

  // the "popping vein": four bent strokes around a gap
  anger: { motion: 'throb', size: 0.05, draw(g, s) {
    g.lineCap = 'round';
    const arm = (rot, color, w) => {
      g.save();
      g.translate(s / 2, s / 2);
      g.rotate(rot);
      g.beginPath();
      g.moveTo(s * 0.08, -s * 0.36);
      g.quadraticCurveTo(s * 0.1, -s * 0.1, s * 0.36, -s * 0.08);
      g.strokeStyle = color;
      g.lineWidth = w;
      g.stroke();
      g.restore();
    };
    for (let i = 0; i < 4; i++) arm(i * Math.PI / 2, '#fff4f8', s * 0.2);
    for (let i = 0; i < 4; i++) arm(i * Math.PI / 2, '#e8243c', s * 0.11);
  } },

  question: { motion: 'bob', size: 0.065, draw(g, s) {
    g.font = `900 ${Math.round(s * 0.9)}px system-ui, sans-serif`;
    g.textAlign = 'center';
    g.textBaseline = 'middle';
    g.lineJoin = 'round';
    g.lineWidth = s * 0.1;
    g.strokeStyle = '#fff4f8';
    g.strokeText('?', s / 2, s * 0.54);
    const fill = g.createLinearGradient(0, s * 0.1, 0, s * 0.9);
    fill.addColorStop(0, '#c58cff');
    fill.addColorStop(1, '#8a4fe0');
    g.fillStyle = fill;
    g.fillText('?', s / 2, s * 0.54);
  } },
};

export function createEmotes(THREE, scene) {
  const kinds = {};          // name -> { tex, frames, fps, size, count, motion } once loaded
  const live = [];           // one per sprite on screen
  const _p = new THREE.Vector3(), _r = new THREE.Vector3(), _u = new THREE.Vector3();

  function drawn(name) {
    const d = DRAWN[name];
    if (!d) return null;
    const S = 128, cv = document.createElement('canvas');
    cv.width = cv.height = S;
    d.draw(cv.getContext('2d'), S);
    const tex = new THREE.CanvasTexture(cv);
    tex.colorSpace = THREE.SRGBColorSpace;
    return { tex, frames: 1, fps: 1, size: d.size, motion: d.motion };
  }

  // A sprite sheet if there is one, else the drawn one. Resolved once per name.
  function kind(name) {
    if (name in kinds) return Promise.resolve(kinds[name]);
    kinds[name] = null;     // while loading: a second burst waits for the first
    const opts = fetch(`emotes/${name}.json`).then(r => (r.ok ? r.json() : {})).catch(() => ({}));
    const img = new Promise(ok => {
      const i = new Image();
      i.onload = () => ok(i);
      i.onerror = () => ok(null);
      i.src = `emotes/${name}.png`;
    });
    return Promise.all([opts, img]).then(([o, i]) => {
      let k = null;
      if (i) {
        const tex = new THREE.Texture(i);
        tex.colorSpace = THREE.SRGBColorSpace;
        tex.needsUpdate = true;
        const frames = Math.max(1, +o.frames || Math.round(i.width / i.height) || 1);
        tex.repeat.set(1 / frames, 1);
        k = { tex, frames, fps: +o.fps || 12, size: 0.05, motion: DRAWN[name]?.motion || 'float', sheet: true };
      } else {
        k = drawn(name);
      }
      if (k) {
        if (MOTION[o.motion]) k.motion = o.motion;
        if (+o.size) k.size = +o.size;
        k.count = +o.count || MOTION[k.motion].count;
      }
      kinds[name] = k;
      return k;
    });
  }

  // A burst on one side of her head: hearts a few at a time, the rest one.
  async function show(name) {
    const k = await kind(name);
    if (!k) return false;
    const m = MOTION[k.motion], side = Math.random() < 0.65 ? 1 : -1;
    for (let i = 0; i < k.count; i++) {
      const tex = k.sheet ? k.tex.clone() : k.tex;
      if (k.sheet) tex.needsUpdate = true;
      const mat = new THREE.SpriteMaterial({ map: tex, transparent: true, depthWrite: false, depthTest: false, opacity: 0 });
      const sprite = new THREE.Sprite(mat);
      sprite.renderOrder = 10;
      sprite.visible = false;
      scene.add(sprite);
      const many = k.count > 1;
      live.push({
        sprite, kind: k, motion: k.motion, age: -i * 0.35,
        life: m.life + Math.random() * (many ? 0.8 : 0.3),
        x: side * (m.x + (many ? Math.random() * 0.03 + (i - 1) * 0.02 : 0)),
        y: m.y + (many ? Math.random() * 0.04 : 0),
        rise: 0.15 + Math.random() * 0.06, sway: 0.012 + Math.random() * 0.01, phase: Math.random() * 6,
        scale: k.size * (many ? 0.75 + Math.random() * 0.45 : 1),
        side,
      });
    }
    return true;
  }

  // How each motion moves: offset (dx, dy), size factor, tilt, opacity.
  function move(e) {
    const a = e.age, t = a / e.life;
    const pop = Math.min(1, a / 0.22);
    const grow = pop < 1 ? pop * 1.15 : 1 + 0.15 * Math.max(0, 1 - (a - 0.22) / 0.2);
    const fade = (e.life - a) / 0.6;
    switch (e.motion) {
      case 'slide':   // fades in on her temple and slips down a little
        return { dx: 0, dy: -0.03 * t * t, size: 1, rot: e.side * -0.25, op: Math.min(1, a / 0.3, fade) };
      case 'throb':   // pops, then pulses like a vein: three beats, slower
        return { dx: 0, dy: 0, size: grow * (1 + 0.12 * Math.max(0, Math.sin(a * 9))), rot: 0, op: Math.min(1, a / 0.1, fade) };
      case 'bob':     // pops up, then bobs and tilts in place
        return { dx: 0, dy: 0.02 * Math.min(1, a / 0.3) + Math.sin(a * 3.2) * 0.006, size: grow,
                 rot: Math.sin(a * 2.4 + e.phase) * 0.15, op: Math.min(1, a / 0.12, fade) };
      default:        // float: up and away, swaying
        return { dx: Math.sin(a * 3 + e.phase) * e.sway, dy: e.rise * t, size: grow,
                 rot: Math.sin(a * 2.2 + e.phase) * 0.18, op: Math.min(1, a / 0.15, (e.life - a) / 0.9) };
    }
  }

  // Every frame: placed beside the head as the camera sees it, so they sit
  // to her side on screen whichever way she's turned.
  function update(dt, head, camera) {
    if (!live.length) return;
    if (head) head.getWorldPosition(_p);
    _r.set(1, 0, 0).applyQuaternion(camera.quaternion);
    _u.set(0, 1, 0).applyQuaternion(camera.quaternion);
    for (let i = live.length - 1; i >= 0; i--) {
      const e = live[i];
      e.age += dt;
      if (e.age < 0) continue;
      if (e.age > e.life) {
        scene.remove(e.sprite);
        e.sprite.material.dispose();
        if (e.kind.sheet) e.sprite.material.map.dispose();
        live.splice(i, 1);
        continue;
      }
      const m = move(e);
      e.sprite.visible = true;
      e.sprite.material.opacity = Math.max(0, m.op);
      e.sprite.scale.setScalar(e.scale * m.size);
      e.sprite.material.rotation = m.rot;
      e.sprite.position.copy(_p).addScaledVector(_r, e.x + m.dx).addScaledVector(_u, e.y + m.dy);
      if (e.kind.sheet && e.kind.frames > 1)
        e.sprite.material.map.offset.x = (Math.floor(e.age * e.kind.fps) % e.kind.frames) / e.kind.frames;
    }
  }

  return { show, update, busy: () => live.length > 0, names: Object.keys(DRAWN) };
}
