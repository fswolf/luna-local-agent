// Props: things she holds, a 3D model in her hand that moves with it.
//
// A prop is a .glb in portrait/props/ (real size, metres), parented to a
// hand bone so every gesture carries it along for free. Its place in the
// hand is written once here, in the hand's own frame as it is in the
// T-pose (fingers out along -X for her right hand, palm down, thumb
// forward), so it fits any VRM: the normalized bones all share that frame.
//
//   props.show('mug')          in her right hand ('left' for the other)
//   props.hide('mug')
//   props.held('mug')          -> true while it's in a hand
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
};

export function createProps({ THREE, GLTFLoader, vrm, fx }) {
  const models = {};      // name -> Promise<Object3D>
  const live = {};        // name -> { obj, scale, target }
  const loader = new GLTFLoader();
  // where you put them in the pose studio, over the defaults above
  const json = url => fetch(url, { cache: 'no-store' }).then(r => (r.ok ? r.json() : null)).catch(() => null);
  const fresh = n => ({ file: `props/${n}.glb`, hand: 'right', at: [-0.05, -0.05, -0.05], turn: [0, 0, 0], scale: 1 });
  const ready = Promise.all([json('props/index.json'), json('props/props.json')]).then(([list, saved]) => {
    for (const n of list || []) if (!PROPS[n]) PROPS[n] = fresh(n);        // a .glb dropped in portrait/props/
    for (const [n, v] of Object.entries(saved || {})) PROPS[n] = { ...(PROPS[n] || fresh(n)), ...v };
  });

  function model(name) {
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

  return {
    PROPS,
    ready,
    async show(name, side) {
      await ready;
      const p = PROPS[name];
      if (!p) return false;
      side = side || p.hand || 'right';
      const hand = vrm.humanoid.getNormalizedBoneNode(side + 'Hand');
      if (!hand) return false;
      let one = live[name];
      if (!one) {
        const obj = (await model(name)).clone(true);
        one = live[name] = { obj, scale: 0, target: 1 };
      }
      place(one.obj, p, side);
      hand.add(one.obj);
      one.side = side;
      one.target = 1;
      return true;
    },
    // the pose studio: change where a prop sits and see it at once
    set(name, fields) {
      const p = PROPS[name];
      if (!p) return;
      Object.assign(p, fields);
      const one = live[name];
      if (one) {
        if (fields.hand && fields.hand !== one.side) { this.show(name, fields.hand); return; }
        place(one.obj, p, one.side);
      }
    },
    hide(name) { if (live[name]) live[name].target = 0; },
    held(name) { return !!live[name] && live[name].target > 0; },
    object(name) { return live[name]?.obj || null; },
    side(name) { return live[name]?.side || PROPS[name]?.hand || 'right'; },
    // every frame: grow in, shrink out, and let go of it once it's gone
    update(dt) {
      for (const [name, one] of Object.entries(live)) {
        one.scale += Math.sign(one.target - one.scale) * Math.min(Math.abs(one.target - one.scale), dt * 6);
        one.obj.scale.setScalar(Math.max(0.001, one.scale) * (PROPS[name]?.scale || 1));
        one.obj.visible = one.scale > 0.01;
        if (!one.target && one.scale <= 0.001) { one.obj.parent?.remove(one.obj); delete live[name]; }
      }
    },
    names() { return Object.keys(PROPS); },
  };
}
