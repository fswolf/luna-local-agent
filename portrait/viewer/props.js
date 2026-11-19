// Props: things she holds, a 3D model in her hand that moves with it.
//
// A prop is a .glb in portrait/props/ (real size, metres), parented to a
// hand bone so every gesture carries it along for free. Its place in the
// hand is written once here, in the hand's own frame as it is in the
// T-pose (fingers out along -X for her right hand, palm down, thumb
// forward), so it fits any VRM: the normalized bones all share that frame.
//
// A worn prop (wear: true, the blanket) is different: a rigged .glb whose
// bones carry the standard humanoid names (chest, leftUpperArm...). It's bound
// to the same bones of whatever model she's in, so it moves with her body,
// and it's scaled to her shoulders. Its bind pose is written below (`bind`):
// the arms-down pose it was shaped in, as normalized bone turns.
//
//   props.show('mug')          in her right hand ('left' for the other)
//   props.hide('mug')
//   props.held('mug')          -> true while it's in a hand
//   props.worn('blanket')      -> true while she has it on
//
// The pose studio's prop tab moves and turns a prop in her hand and saves
// where it sits to portrait/props/props.json, which is read over these
// defaults (a .glb dropped in portrait/props/ and saved there is a new prop).
//
// Showing and hiding grow and shrink it over a moment, so a prop never
// pops in; the gesture that picks it up hides that moment off screen.

export const PROPS = {
  mug: {
    file: 'props/mug.glb',
    hand: 'right',
    // where the mug sits in the right hand (metres) and how it's turned
    // (radians, x/y/z): in the fist, upright when the forearm is, handle out
    at: [-0.05, -0.05, -0.048],
    turn: [Math.PI / 2, Math.PI, 0],
    scale: 0.74,                 // the model is a big mug; this is her size
    pickup: 'coffee_pickup',     // the gestures that pick it up and put it down
    putdown: 'coffee_putdown',   // (their prop_at: when in it the mug appears / goes)
  },
  plush: {
    file: 'props/plush.glb',     // her moon-cat plush (portrait/source/props/plush/plush.blend)
    hand: 'right',
    at: [-0.036, 0.007, 0.004],  // upright in front of her chest, on her crossed arms
    turn: [-2.098, -0.537, 2.718],
    scale: 1,
    pickup: 'plush_pickup',
    putdown: 'plush_putdown',
  },
  // the rave set (portrait/source/props/rave/rave.blend): a pacifier in her
  // mouth, a glow stick in each hand. Showing the pink stick shows its pair.
  pacifier: {
    file: 'props/pacifier.glb',
    bone: 'head',                // on her head, not in a hand (doesn't count as holding something)
    at: [0, -0.004, 0.089],      // over her lips, the shield just clear of her cheeks
    turn: [0, 0, 0],
    scale: 1,
  },
  glowstick_pink: {
    file: 'props/glowstick_pink.glb',
    hand: 'right',
    pair: 'glowstick_blue',      // the other hand's one comes and goes with it
    free: true,                  // any gesture may swing it about (dances): portrait.js busyHands
    glow: '#ff4fb8',             // a soft halo, a little pink light on her, and light trails as it moves (addGlow)
    at: [-0.055, -0.022, 0],     // through her fist, along the way her thumb points
    turn: [Math.PI / 2, 0, 0],
    scale: 1,
  },
  glowstick_blue: {
    file: 'props/glowstick_blue.glb',
    hand: 'left',
    free: true,
    glow: '#3fd8ff',
    at: [-0.055, -0.022, 0],     // through her fist, along the way her thumb points
    turn: [Math.PI / 2, 0, 0],
    scale: 1,
  },
  note: {
    make: 'note',                // a sticky note made in code, the reminder's words on it (noteText)
    hand: 'right',
    at: [-0.086, 0.002, 0.011],  // pinched at its bottom edge, held up facing you (note_show)
    turn: [1.985, -0.259, 1.497],
    scale: 1,
  },
  blanket: {
    file: 'props/blanket.glb',   // made on her human model in Blender (blanket.blend holds her model too, so it stays out of git)
    wear: true,
    // the pose it was shaped in: upper arms 70 degrees down from the T-pose, forearms a touch forward
    bind: { leftUpperArm: [0, 0, -70], rightUpperArm: [0, 0, 70], leftLowerArm: [0, -12, 0], rightLowerArm: [0, 12, 0] },
    shoulders: 0.17,             // her upper arms' distance apart, and their height, in that model
    shoulderY: 0.962,
  },
};

export function createProps({ THREE, GLTFLoader, vrm, fx }) {
  const models = {};      // name -> Promise<Object3D>
  const live = {};        // name -> { obj, scale, target }
  const making = {};      // name -> Promise while its copy is being made
  const loader = new GLTFLoader();
  // where you put them in the pose studio, over the defaults above
  const json = url => fetch(url, { cache: 'no-store' }).then(r => (r.ok ? r.json() : null)).catch(() => null);
  const fresh = n => ({ file: `props/${n}.glb`, hand: 'right', at: [-0.05, -0.05, -0.05], turn: [0, 0, 0], scale: 1 });
  const ready = Promise.all([json('props/index.json'), json('props/props.json')]).then(([list, saved]) => {
    for (const n of list || []) if (!PROPS[n]) PROPS[n] = fresh(n);        // a .glb dropped in portrait/props/
    for (const [n, v] of Object.entries(saved || {})) PROPS[n] = { ...(PROPS[n] || fresh(n)), ...v };
  });

  // The sticky note: a small square of yellow paper, its bottom corner curling
  // up a little, with a canvas for its words (noteText draws on it).
  const note = { canvas: document.createElement('canvas'), tex: null, text: '' };
  note.canvas.width = note.canvas.height = 256;
  function makeNote() {
    const S = 0.072, geo = new THREE.PlaneGeometry(S, S, 8, 8), pos = geo.attributes.position;
    for (let i = 0; i < pos.count; i++) {                      // the curl: lower right corner lifts
      const x = pos.getX(i) / S + 0.5, y = pos.getY(i) / S + 0.5;
      pos.setZ(i, 0.012 * Math.max(0, x - y - 0.35) ** 2 + 0.003 * Math.sin(y * Math.PI));
    }
    geo.computeVertexNormals();
    note.tex = new THREE.CanvasTexture(note.canvas);
    note.tex.colorSpace = THREE.SRGBColorSpace;
    noteText(note.text);
    const mesh = new THREE.Mesh(geo, new THREE.MeshStandardMaterial({ map: note.tex, emissiveMap: note.tex, emissive: 0x666666,
      side: THREE.DoubleSide, roughness: 0.9 }));
    const g = new THREE.Group();
    g.add(mesh);
    return g;
  }
  function noteText(text) {
    note.text = String(text || '');
    const c = note.canvas, g = c.getContext('2d'), W = c.width;
    g.fillStyle = '#ffe27a'; g.fillRect(0, 0, W, W);
    g.fillStyle = 'rgba(160,120,0,0.12)'; g.fillRect(0, 0, W, W * 0.16);        // the sticky strip
    g.fillStyle = '#3d2f63'; g.textAlign = 'center'; g.textBaseline = 'middle';
    const words = String(text || '').trim().split(/\s+/).filter(Boolean);
    let size = 44, lines = [];
    for (; size >= 20; size -= 3) {                                                // shrink until it fits
      g.font = `600 ${size}px "Segoe Print", "Bradley Hand", "Comic Sans MS", "Comic Neue", cursive`;
      lines = []; let line = '';
      for (const w of words) {
        const t = line ? line + ' ' + w : w;
        if (g.measureText(t).width > W * 0.84 && line) { lines.push(line); line = w; } else line = t;
      }
      if (line) lines.push(line);
      if (lines.length * size * 1.15 <= W * 0.66) break;
    }
    lines.forEach((l, i) => g.fillText(l, W / 2, W * 0.55 + (i - (lines.length - 1) / 2) * size * 1.15));
    g.font = '28px sans-serif'; g.fillStyle = '#e8577f'; g.fillText('\u2665', W * 0.86, W * 0.86);   // a little heart
    if (note.tex) note.tex.needsUpdate = true;
  }

  // Glow (a prop with glow: '#colour', the glow sticks): a soft halo that
  // always faces the camera, a small coloured light so she's lit by it, and a
  // trail: a ribbon through where its two ends were over the last moment,
  // fading out, drawn additively so swings leave streaks of light.
  const TRAIL = 24, TRAIL_S = 0.28;                  // at most this many samples, none older than TRAIL_S seconds
  const beat = { bpm: 0, at: 0 };                    // the music's beat (setBeat): the sticks pulse on it
  function pulse() {
    if (!beat.bpm || !beat.at) return 0;
    const p = 60 / beat.bpm, x = (((Date.now() / 1000 - beat.at) / p) % 1 + 1) % 1;
    return Math.exp(-x * 7);                         // a flash on the beat, fading before the next
  }
  const LIGHT = 0.025;                               // her MToon shading takes a point light strongly: keep it a tint
  let haloTex = null;
  function halo() {
    if (haloTex) return haloTex;
    const c = document.createElement('canvas'); c.width = c.height = 64;
    const g = c.getContext('2d'), r = g.createRadialGradient(32, 32, 0, 32, 32, 32);
    r.addColorStop(0, 'rgba(255,255,255,1)'); r.addColorStop(0.25, 'rgba(255,255,255,0.45)'); r.addColorStop(1, 'rgba(255,255,255,0)');
    g.fillStyle = r; g.fillRect(0, 0, 64, 64);
    return (haloTex = new THREE.CanvasTexture(c));
  }
  function addGlow(one, colour) {
    const col = new THREE.Color(colour), halos = [];
    for (const y of [-0.045, 0, 0.045]) {             // three soft blobs along the stick
      const s = new THREE.Sprite(new THREE.SpriteMaterial({ map: halo(), color: col, blending: THREE.AdditiveBlending,
        transparent: true, depthWrite: false, opacity: 0.55 }));
      s.position.y = y; s.scale.setScalar(0.07); s.renderOrder = 6;
      one.obj.add(s); halos.push(s);
    }
    const light = new THREE.PointLight(col, LIGHT, 0.22, 2);
    one.obj.add(light);
    const N = TRAIL * 2, geo = new THREE.BufferGeometry();
    geo.setAttribute('position', new THREE.BufferAttribute(new Float32Array(N * 3), 3));
    geo.setAttribute('color', new THREE.BufferAttribute(new Float32Array(N * 3), 3));
    const idx = [];
    for (let i = 0; i < TRAIL - 1; i++) { const a = i * 2; idx.push(a, a + 1, a + 2, a + 1, a + 3, a + 2); }
    geo.setIndex(idx);
    const ribbon = new THREE.Mesh(geo, new THREE.MeshBasicMaterial({ vertexColors: true, blending: THREE.AdditiveBlending,
      transparent: true, depthWrite: false, side: THREE.DoubleSide }));
    ribbon.frustumCulled = false; ribbon.renderOrder = 6;
    (vrm.scene.parent || vrm.scene).add(ribbon);
    one.glow = { col, light, ribbon, halos, pts: [], a: new THREE.Vector3(), b: new THREE.Vector3() };
  }
  function trail(one, on) {
    const g = one.glow;
    if (!on) { g.pts.length = 0; g.ribbon.visible = false; return; }
    one.obj.updateWorldMatrix(true, false);
    const now = performance.now() / 1000;
    g.pts.unshift([g.a.set(0, 0.075, 0).applyMatrix4(one.obj.matrixWorld).toArray(), g.b.set(0, -0.075, 0).applyMatrix4(one.obj.matrixWorld).toArray(), now]);
    while (g.pts.length > 1 && (g.pts.length > TRAIL || now - g.pts[g.pts.length - 1][2] > TRAIL_S)) g.pts.pop();
    const pos = g.ribbon.geometry.attributes.position, col = g.ribbon.geometry.attributes.color;
    for (let i = 0; i < TRAIL; i++) {
      const p = g.pts[Math.min(i, g.pts.length - 1)], age = (now - p[2]) / TRAIL_S;
      const f = i < g.pts.length ? Math.max(0, 1 - age) ** 2 * 0.45 : 0;
      for (let k = 0; k < 2; k++) {
        pos.setXYZ(i * 2 + k, ...p[k]);
        col.setXYZ(i * 2 + k, g.col.r * f, g.col.g * f, g.col.b * f);
      }
    }
    pos.needsUpdate = col.needsUpdate = true;
    g.ribbon.visible = g.pts.length > 1;
  }

  function model(name) {
    if (PROPS[name]?.make === 'note') { models[name] = models[name] || Promise.resolve(makeNote()); return models[name]; }
    if (!models[name]) {
      models[name] = loader.loadAsync(PROPS[name].file).then(g => {
        g.scene.traverse(o => { if (o.isMesh) { o.castShadow = false; o.frustumCulled = false; } });
        return g.scene;
      });
    }
    return models[name];
  }

  // The left hand is the right one mirrored across her middle.
  function place(obj, p, side) {
    const m = side === 'left' ? -1 : 1;
    obj.position.set(m * p.at[0], p.at[1], p.at[2]);
    obj.rotation.set(p.turn[0], m * p.turn[1], m * p.turn[2]);
    // VRM 0.x models face the other way in their own space (see gestures.js fx)
    if (fx === -1) { obj.position.x *= -1; obj.position.z *= -1; obj.rotation.y += Math.PI; }
  }

  // A worn prop: its own skinned mesh, rebound to her bones of the same names.
  // Her bones are put in the prop's bind pose for one moment (no frame is drawn
  // in between), the skeleton is made from that, and her pose is put back.
  async function wear(name, p) {
    const src = await model(name);
    const obj = src.clone(true);
    let mesh = null;
    obj.traverse(o => { if (o.isSkinnedMesh && !mesh) mesh = o; });
    if (!mesh) return null;
    const h = vrm.humanoid, names = mesh.skeleton.bones.map(b => b.name);
    const raw = names.map(n => h.getRawBoneNode(n));
    if (raw.some(b => !b)) { console.warn('[props]', name, 'needs bones this model lacks:', names.filter((n, i) => !raw[i])); return null; }
    // sized to her shoulders, at their height (measured in her T-pose, before anything turns)
    const saved = {};
    for (const n of Object.keys(h.humanBones)) { const b = h.getNormalizedBoneNode(n); if (b) { saved[n] = b.quaternion.clone(); b.quaternion.identity(); } }
    h.update(); vrm.scene.updateMatrixWorld(true);
    const at = n => new THREE.Vector3().setFromMatrixPosition(h.getRawBoneNode(n).matrixWorld).applyMatrix4(new THREE.Matrix4().copy(vrm.scene.matrixWorld).invert());
    const l = at('leftUpperArm'), r = at('rightUpperArm');
    const scale = p.shoulders ? l.distanceTo(r) / p.shoulders : 1;
    // her pose as it was when the prop was shaped
    const e = new THREE.Euler();
    for (const [n, deg] of Object.entries(p.bind || {})) {
      const b = h.getNormalizedBoneNode(n);
      if (!b) continue;
      const fz = n.endsWith('UpperArm') ? fx : 1;     // a VRM 0.x model's arms point the other way
      b.quaternion.setFromEuler(e.set(deg[0] * Math.PI / 180, deg[1] * Math.PI / 180, fz * deg[2] * Math.PI / 180));
    }
    h.update(); vrm.scene.updateMatrixWorld(true);
    mesh.removeFromParent();
    vrm.scene.add(mesh);
    mesh.position.set(0, p.shoulderY ? (l.y + r.y) / 2 - p.shoulderY * scale : 0, 0);
    mesh.scale.setScalar(scale);
    if (fx === -1) mesh.rotation.y = Math.PI;            // it was made facing +Z, a VRM 0.x model faces -Z
    mesh.updateMatrixWorld(true);
    mesh.bind(new THREE.Skeleton(raw), mesh.matrixWorld); // inverses from her bones as they are now
    for (const [n, q] of Object.entries(saved)) h.getNormalizedBoneNode(n).quaternion.copy(q);
    h.update();
    mesh.frustumCulled = false;
    const mats = [].concat(mesh.material);
    mats.forEach(m => { m.transparent = true; m.opacity = 0; m.side = THREE.DoubleSide; });
    return { obj: mesh, mats, scale: 0, target: 1, worn: true };
  }

  return {
    PROPS,
    ready,
    async show(name, side) {
      await ready;
      const p = PROPS[name];
      if (!p) return false;
      if (p.wear) {
        if (!live[name]) {
          making[name] = making[name] || wear(name, p).then(w => { if (w) live[name] = live[name] || w; });
          await making[name];
          delete making[name];
        }
        if (live[name]) live[name].target = 1;
        return !!live[name];
      }
      side = side || p.hand || 'right';
      const hand = vrm.humanoid.getNormalizedBoneNode(p.bone || side + 'Hand');
      if (!hand) return false;
      // two shows at once (a refresh, the coffee routine and the studio) must make one
      // prop, not two: the second waits for the first's copy instead of cloning its own
      if (!live[name]) {
        making[name] = making[name] || model(name).then(m => {
          if (live[name]) return;
          live[name] = { obj: m.clone(true), scale: 0, target: 1 };
          if (p.glow) addGlow(live[name], p.glow);
        });
        await making[name];
        delete making[name];
      }
      const one = live[name];
      if (!one) return false;
      place(one.obj, p, side);
      hand.add(one.obj);
      one.side = side;
      one.target = 1;
      return true;
    },
    // the pose studio: change where a prop sits and see it at once
    set(name, fields) {
      const p = PROPS[name];
      if (!p || p.wear) return;          // a worn prop sits on her body, not in a hand
      Object.assign(p, fields);
      const one = live[name];
      if (one) {
        if (fields.hand && fields.hand !== one.side) { this.show(name, fields.hand); return; }
        place(one.obj, p, one.side);
      }
    },
    hide(name) { if (live[name]) live[name].target = 0; },
    held(name) { return !!live[name] && live[name].target > 0 && !live[name].worn && !PROPS[name]?.bone; },   // in a hand (not worn)
    worn(name) { return !!live[name] && live[name].target > 0 && !!live[name].worn; },
    object(name) { return live[name]?.obj || null; },
    side(name) { return live[name]?.side || PROPS[name]?.hand || 'right'; },
    // every frame: grow in, shrink out, and let go of it once it's gone
    update(dt) {
      for (const [name, one] of Object.entries(live)) {
        if (one.worn) {          // worn: fades in and out where it is (growing from her feet would look odd)
          one.scale += Math.sign(one.target - one.scale) * Math.min(Math.abs(one.target - one.scale), dt * 2);
          const solid = one.scale > 0.999;     // drawn as see-through only while it fades
          one.mats.forEach(m => {
            m.opacity = one.scale; m.depthWrite = solid;
            if (m.transparent === solid) { m.transparent = !solid; m.needsUpdate = true; }
          });
          one.obj.visible = one.scale > 0.01;
          if (!one.target && one.scale <= 0.001) { one.obj.removeFromParent(); delete live[name]; }
          continue;
        }
        one.scale += Math.sign(one.target - one.scale) * Math.min(Math.abs(one.target - one.scale), dt * 6);
        one.obj.scale.setScalar(Math.max(0.001, one.scale) * (PROPS[name]?.scale || 1));
        one.obj.visible = one.scale > 0.01;
        if (one.glow) {
          const k = pulse();
          one.glow.light.intensity = LIGHT * one.scale * (1 + 1.5 * k);
          for (const s of one.glow.halos) { s.material.opacity = 0.45 + 0.4 * k; s.scale.setScalar(0.07 * (1 + 0.35 * k)); }
          trail(one, one.obj.visible && one.scale > 0.5);
        }
        if (!one.target && one.scale <= 0.001) {
          one.obj.parent?.remove(one.obj);
          if (one.glow) { one.glow.ribbon.removeFromParent(); one.glow.ribbon.geometry.dispose(); one.glow.ribbon.material.dispose(); }
          delete live[name];
        }
      }
    },
    names() { return Object.keys(PROPS); },
    setBeat(bpm, at) { beat.bpm = +bpm || 0; beat.at = +at || 0; },
    noteText,
  };
}
