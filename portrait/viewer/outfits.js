// Her clothes, piece by piece (VRM models whose clothes are their own parts).
//
// A VRoid export keeps each piece of clothing as its own part of the body
// mesh, with a material named like N00_010_01_Onepiece_00_CLOTH_02. three.js
// makes each of those its own object, so a piece comes off by hiding it, and
// the body underneath is whole. Nothing is reloaded or swapped.
//
// Which piece is which (top, tie, bottoms...) is guessed from where it sits
// on her: the numbers after CLOTH change from one export to the next, the
// shape doesn't. A model can name its pieces itself in <model>.outfits.json
// next to it, {"pieces": {"CLOTH_02": "top"}} (part of the material name ->
// label), for anything the guess gets wrong or a model that isn't VRoid's.
//
//   pieces()          [{ id, label, on }]
//   set(id, on)       one piece on or off (by id or label)
//   wear(name)        'dressed' (everything on) or 'underwear' (everything off)
//   state()           'dressed', 'underwear' or 'partly'
//   onChange(fn)      called after any change, with state()

// Material names that are clothing. Skin, face, eyes and hair never are.
const CLOTHING = /(_CLOTH|Tops?_|Bottoms?_|Onepiece|Shoes_|Socks_|Accessory_)/i;
// ...and cat ears, a tail, horns or wings are part of her, even when VRoid files them as accessories
const NOT = /(_SKIN|_FACE|_EYE|_HAIR|Ear|Tail|Horn|Wing)/i;
const base = n => String(n || '').replace(/\s*\(Instance\)$/, '');

export async function createOutfits({ THREE, vrm, url = '' }) {
  const groups = new Map();                       // id -> { id, label, objects: [], tris }
  vrm.scene.traverse(o => {
    if (!o.isMesh) return;
    const name = base([].concat(o.material)[0]?.name);
    if (!CLOTHING.test(name) || NOT.test(name)) return;
    const tris = o.geometry.index ? o.geometry.index.count / 3 : (o.geometry.attributes.position?.count || 0) / 3;
    if (!groups.has(name)) groups.set(name, { id: name, label: '', objects: [], tris: 0 });
    const g = groups.get(name);
    g.objects.push(o);
    g.tris += tris;
  });
  // VRoid leaves an empty two-triangle placeholder in every outfit: not a piece
  for (const [id, g] of groups) if (g.tris <= 4) groups.delete(id);

  guessLabels(THREE, vrm, [...groups.values()]);

  // the model's own names win over the guess
  if (url) {
    try {
      const r = await fetch(url.replace(/\.vrm$/i, '') + '.outfits.json', { cache: 'no-store' });
      if (r.ok) {
        const map = (await r.json())?.pieces || {};
        for (const g of groups.values())
          for (const [part, label] of Object.entries(map)) if (g.id.includes(part)) g.label = String(label);
      }
    } catch (e) { /* no file, or not JSON: the guesses stand */ }
  }

  // two pieces guessed the same ("top", "top"): number them so both show
  const seen = {};
  for (const g of groups.values()) seen[g.label] = (seen[g.label] || 0) + 1;
  const count = {};
  for (const g of groups.values())
    if (seen[g.label] > 1) g.label = `${g.label} ${(count[g.label] = (count[g.label] || 0) + 1)}`;

  const listeners = [];
  const isOn = g => g.objects.some(o => o.visible);
  function state() {
    const all = [...groups.values()];
    if (!all.length || all.every(isOn)) return 'dressed';
    if (all.every(g => !isOn(g))) return 'underwear';
    return 'partly';
  }
  const changed = () => { const s = state(); for (const fn of listeners) { try { fn(s); } catch (e) { console.error(e); } } };

  // listeners hear about real changes only: tame mode re-sends "dressed" with
  // every mood update, and that shouldn't post anything
  // id, a label, or a numbered label's name: "top" is "top 1" and "top 2" both
  function set(id, on) {
    let gs = groups.has(id) ? [groups.get(id)] : [...groups.values()].filter(x => x.label === id);
    if (!gs.length) gs = [...groups.values()].filter(x => x.label.startsWith(id + ' ') && /^\d+$/.test(x.label.slice(id.length + 1)));
    if (!gs.length) return false;
    let any = false;
    for (const g of gs) for (const o of g.objects) if (o.visible !== !!on) { o.visible = !!on; any = true; }
    if (any) changed();
    return true;
  }
  function wear(name) {
    if (name !== 'dressed' && name !== 'underwear') return false;
    const on = name === 'dressed';
    let any = false;
    for (const g of groups.values()) for (const o of g.objects) if (o.visible !== on) { o.visible = on; any = true; }
    if (any) changed();
    return true;
  }
  const pieces = () => [...groups.values()].map(g => ({ id: g.id, label: g.label, on: isOn(g) }));

  return { pieces, set, wear, state, onChange: fn => listeners.push(fn), get has() { return groups.size > 0; } };
}

// Where each piece sits on her, from its vertices in the rest pose: a piece
// much narrower than the rest, up at the collar, is a tie (lower down, a
// ribbon); above the hips a top, around and below them bottoms, at the feet
// shoes. Heights are taken against her own hips and feet,
// so it doesn't matter how tall the model is.
function guessLabels(THREE, vrm, list) {
  const h = vrm.humanoid;
  const y = name => { const n = h?.getNormalizedBoneNode?.(name); if (!n) return null; const v = new THREE.Vector3(); n.getWorldPosition(v); return v.y; };
  const hips = y('hips') ?? 0.9, feet = Math.min(y('leftFoot') ?? 0.08, y('rightFoot') ?? 0.08), chest = y('upperChest') ?? y('chest') ?? hips + 0.3;
  const v = new THREE.Vector3();
  const seen = [];
  for (const g of list) {
    let sy = 0, n = 0, minX = Infinity, maxX = -Infinity;
    for (const o of g.objects) {
      const pos = o.geometry.attributes.position;
      if (!pos) continue;
      o.updateWorldMatrix(true, false);
      const step = Math.max(1, Math.floor(pos.count / 2000));     // a sample is plenty
      for (let i = 0; i < pos.count; i += step) {
        v.fromBufferAttribute(pos, i).applyMatrix4(o.matrixWorld);
        sy += v.y; n++;
        if (v.x < minX) minX = v.x;
        if (v.x > maxX) maxX = v.x;
      }
    }
    seen.push({ g, cy: n ? sy / n : hips, width: maxX - minX });
  }
  // narrow next to the rest: a tie (with its collar) is about half a top's width
  const widest = Math.max(0.01, ...seen.map(s => s.width));
  for (const { g, cy, width } of seen) {
    if (cy < feet + 0.12) g.label = 'shoes';
    else if (width < 0.6 * widest && cy > hips + 0.1) g.label = cy > chest - 0.05 ? 'tie' : 'ribbon';
    else if (cy >= hips + 0.05) g.label = 'top';
    else if (cy > feet + 0.35) g.label = 'bottoms';
    else g.label = 'socks';
  }
}
