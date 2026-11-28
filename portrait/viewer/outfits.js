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
// label), for anything the guess gets wrong. A part named there is clothing
// whatever its material is called, so a model that isn't VRoid's, with
// materials like "Jacket" and "Skirt", works from that file alone.
//
//   pieces()          [{ id, label, on, under }]
//   set(id, on)       one piece on or off (by id or label)
//   wear(name)        'dressed' (everything on), 'underwear' (everything but
//                     the underwear off) or 'bare' (everything off)
//   state()           'dressed', 'underwear', 'bare' or 'partly'
//   onChange(fn)      called after any change, with state()
//   sets()            the underwear sets: the model's own first, then outfits.json "sets"
//   wearSet(name)     put one on (its pictures on those pieces); wearing: which one is on
//
// Underwear is a piece labelled bra or panties (<model>.outfits.json names
// them: a VRoid export paints underwear on the skin, so a model only has
// these when they were made as parts of their own). A model without them
// works as it always did: 'underwear' takes every piece off, and so does 'bare'.

// Material names that are clothing. Skin, face, eyes and hair never are.
const CLOTHING = /(_CLOTH|Tops?_|Bottoms?_|Onepiece|Shoes_|Socks_|Accessory_)/i;
// ...and cat ears, a tail, horns or wings are part of her, even when VRoid files them as accessories.
// Those by their capital (CatEar, Tail): "ear" in any case was in "underwear" too.
const NOT = /_SKIN|_FACE|_EYE|_HAIR/i, HERS = /Ear|Tail|Horn|Wing/;
const base = n => String(n || '').replace(/\s*\(Instance\)$/, '');
// a piece that's underwear, by its label ("bra", "panties", "bra 2")
export const UNDER = /^(?:bra|panties)(?: \d+)?$/;

export async function createOutfits({ THREE, vrm, url = '' }) {
  // The model's own names (<model>.outfits.json), read first: a part it names
  // is clothing whatever its material is called, so a model that isn't
  // VRoid's ("Jacket", "Skirt_mat") works too, not only VRoid's _CLOTH names.
  let named = {}, file = {};
  if (url) {
    try {
      const r = await fetch(url.replace(/\.vrm$/i, '') + '.outfits.json', { cache: 'no-store' });
      if (r.ok) file = (await r.json()) || {};
      if (!file || typeof file !== 'object' || Array.isArray(file)) file = {};
      named = file.pieces || {};
      if (!named || typeof named !== 'object' || Array.isArray(named)) named = {};
    } catch (e) { named = {}; file = {}; /* no file, or not JSON: the guesses stand */ }
  }
  // a part as a whole word of the name: "Bra" is in "Underwear_Bra_CLOTH",
  // not in "Hair_Braid" or "Cobra"; "CLOTH_02" is in "..._CLOTH_02 (Instance)"
  const esc = x => x.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
  const parts = Object.entries(named).filter(([part]) => part)
    .map(([part, label]) => [new RegExp(`(?<![A-Za-z])${esc(part)}(?![a-z0-9])`), label]);
  const namedAs = name => parts.find(([re]) => re.test(name));
  const groups = new Map();                       // id -> { id, label, objects: [], tris }
  vrm.scene.traverse(o => {
    if (!o.isMesh) return;
    const name = base([].concat(o.material)[0]?.name);
    if (!namedAs(name) && (!CLOTHING.test(name) || NOT.test(name) || HERS.test(name))) return;
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
  for (const g of groups.values()) {
    const hit = namedAs(g.id);
    if (hit) g.label = String(hit[1]);
  }

  // two pieces guessed the same ("top", "top"): number them so both show
  const seen = {};
  for (const g of groups.values()) seen[g.label] = (seen[g.label] || 0) + 1;
  const count = {};
  for (const g of groups.values())
    if (seen[g.label] > 1) g.label = `${g.label} ${(count[g.label] = (count[g.label] || 0) + 1)}`;

  const listeners = [];
  const kind = label => String(label).replace(/ \d+$/, '');
  const isOn = g => g.objects.some(o => o.visible);
  const isUnder = g => UNDER.test(g.label);
  function state() {
    const all = [...groups.values()], under = all.filter(isUnder);
    if (!all.length || all.every(isOn)) return 'dressed';
    if (all.every(g => !isOn(g))) return under.length ? 'bare' : 'underwear';
    if (under.length && under.every(isOn) && all.every(g => isUnder(g) || !isOn(g))) return 'underwear';
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
    if (!['dressed', 'underwear', 'bare'].includes(name)) return false;
    let any = false;
    for (const g of groups.values()) {
      const on = name === 'dressed' || (name === 'underwear' && isUnder(g));
      for (const o of g.objects) if (o.visible !== on) { o.visible = on; any = true; }
    }
    if (any) changed();
    return true;
  }
  const pieces = () => [...groups.values()].map(g => ({ id: g.id, label: g.label, on: isOn(g), under: isUnder(g) }));

  // -- sets: the same pieces in other textures (outfits.json "sets") ----------
  // {"sets": {"mint": {"bra": "sets/mint-bra.png", "panties": "sets/mint-panties.png"}},
  //  "default_name": "white"}: by piece label, a picture next to the model. The
  // model's own textures are the default set. Only the picture changes: the
  // pieces stay where they are, on or off.
  const SAFE = /^[A-Za-z0-9][A-Za-z0-9_./-]*\.(png|jpe?g|webp)$/i;
  const dir = url.replace(/[^/]*$/, '');
  const defaultName = String(file.default_name || 'default');
  const sets = {};
  for (const [name, parts] of Object.entries(file.sets || {})) {
    if (!/^[a-z0-9][a-z0-9_-]{0,23}$/.test(name) || name === defaultName || !parts || typeof parts !== 'object') continue;
    const ok = Object.entries(parts).filter(([, f]) => typeof f === 'string' && SAFE.test(f) && !f.includes('..'));
    if (ok.length) sets[name] = Object.fromEntries(ok);
  }
  const originals = new Map();                     // material -> { map, shade }, the model's own
  const textures = new Map();                      // file -> Promise<Texture>
  const setListeners = [];
  let wearing = defaultName, asked = 0;
  const materialsOf = label => [...groups.values()].filter(g => kind(g.label) === label)
    .flatMap(g => g.objects.flatMap(o => [].concat(o.material)));
  const load = f => {
    if (!textures.has(f))   // a failed load is forgotten, so picking the set again tries again
      textures.set(f, new THREE.TextureLoader().loadAsync(dir + f).catch(e => { textures.delete(f); throw e; }));
    return textures.get(f);
  };
  async function wearSet(name) {
    name = String(name || defaultName);
    if (name !== defaultName && !sets[name]) return false;
    const mine = ++asked;                          // a quicker pick after this one wins
    const pick = sets[name] || {};
    const labels = new Set(Object.values(sets).flatMap(p => Object.keys(p)));
    const want = [];
    for (const label of labels) for (const m of materialsOf(label)) {
      if (!m || !m.map) continue;
      if (!originals.has(m)) originals.set(m, { map: m.map, shade: m.shadeMultiplyTexture });
      want.push([m, pick[label] ? load(pick[label]) : null]);
    }
    let pics;
    try { pics = await Promise.all(want.map(([, p]) => p)); }
    catch (e) { console.error('outfit set', name, e); return false; }
    if (mine !== asked) return false;
    want.forEach(([m], i) => {
      const own = originals.get(m), t = pics[i];
      if (t) {                                     // as the model's own was read: VRM textures aren't flipped
        t.flipY = own.map.flipY; t.colorSpace = own.map.colorSpace;
        t.wrapS = own.map.wrapS; t.wrapT = own.map.wrapT; t.needsUpdate = true;
      }
      m.map = t || own.map;
      if ('shadeMultiplyTexture' in m && own.shade) m.shadeMultiplyTexture = t || own.shade;
      m.needsUpdate = true;
    });
    wearing = name;
    // the other sets' pictures leave the GPU (2048² each); picked again, they go back up
    const inUse = new Set(pics.filter(Boolean));
    for (const p of textures.values()) p.then(t => { if (!inUse.has(t) && mine === asked) t.dispose(); }, () => {});
    for (const fn of setListeners) { try { fn(name); } catch (e) { console.error(e); } }
    return true;
  }
  const setNames = () => [defaultName, ...Object.keys(sets)];

  return { pieces, set, wear, state, onChange: fn => listeners.push(fn), get has() { return groups.size > 0; },
           sets: setNames, wearSet, get wearing() { return wearing; }, defaultSet: defaultName,
           onSet: fn => setListeners.push(fn) };
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
