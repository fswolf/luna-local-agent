// Touching her: a click on the portrait finds the spot on her body it
// landed on and names the zone - head, nose, mouth, chest, tummy, groin,
// legs, and neck, arms, back, butt and tail (nothing set for those yet). What she
// does about it is portrait.js's business, and portrait/touch.json's;
// this file only answers "where".
//
// A ray goes from the camera through the cursor and stops at the first
// piece of her it meets. That spot on her skin is weighted to bones (it's
// how the mesh follows her skeleton), and the bone it follows most says
// what it is: a hair strand belongs to her head, a breast to her chest,
// her tail to her tail. So the zones follow her wherever she moves -
// leaning, jumping, mid-gesture, any framing, any screen - and a part
// that's out of frame simply can't be touched. A mesh without skin
// weights (a rigid accessory) falls back to the nearest bone.
//
// Bones are the standard VRM humanoid ones, so this works on any VRM. The
// face is split using her eyes (VRoid has eye bones; without them they're
// guessed a little above the head bone), measured in her head's own frame
// so it still works with her head turned.

// humanoid bone -> part of her
const PART = {
  head: 'head', leftEye: 'head', rightEye: 'head', jaw: 'head', neck: 'neck',
  upperChest: 'chest', chest: 'chest', spine: 'tummy', hips: 'hips',
  leftUpperLeg: 'leg', rightUpperLeg: 'leg', leftLowerLeg: 'leg', rightLowerLeg: 'leg',
  leftFoot: 'leg', rightFoot: 'leg', leftToes: 'leg', rightToes: 'leg',
};
const ARM = /Shoulder|Arm|Hand|Thumb|Index|Middle|Ring|Little/;

// for the fallback: [bone, the bone its segment runs to]
const SEGMENTS = [
  ['hips', 'spine'], ['spine', 'chest'], ['chest', 'upperChest'], ['upperChest', 'neck'], ['neck', 'head'],
  ['head', null], ['leftUpperLeg', 'leftLowerLeg'], ['rightUpperLeg', 'rightLowerLeg'],
  ['leftLowerLeg', 'leftFoot'], ['rightLowerLeg', 'rightFoot'], ['leftUpperArm', 'leftLowerArm'],
  ['rightUpperArm', 'rightLowerArm'], ['leftLowerArm', 'leftHand'], ['rightLowerArm', 'rightHand'],
];

export function createTouch(THREE, camera, canvas) {
  const ray = new THREE.Raycaster();
  const ndc = new THREE.Vector2();
  const v = Array.from({ length: 8 }, () => new THREE.Vector3());
  const q = new THREE.Quaternion();
  let cache = null;          // per model: its meshes, and raw bone -> humanoid name

  function prepare(vrm) {
    if (cache?.vrm === vrm) return cache;
    const names = new Map();
    for (const [name, hb] of Object.entries(vrm.humanoid.humanBones || {})) if (hb?.node) names.set(hb.node, name);
    const meshes = [];
    // her meshes, not the blush/tear overlays (the emotes aren't in her scene)
    vrm.scene.traverse(m => { if (m.isMesh && !m.userData.overlay) meshes.push(m); });
    return (cache = { vrm, names, meshes, fx: vrm.meta?.metaVersion === '0' ? -1 : 1 });
  }

  // p in a bone's own frame: the normalized bones point the way the world
  // does at rest, so +y is up her body and +z out of her front however
  // she's turned (VRM 0.x models face -z in their own space: fx)
  function local(vrm, name, p, out) {
    const b = vrm.humanoid.getNormalizedBoneNode(name);
    if (!b) return null;
    b.getWorldPosition(out);
    out.subVectors(p, out).applyQuaternion(b.getWorldQuaternion(q).invert());
    if (cache.fx < 0) { out.x = -out.x; out.z = -out.z; }
    return out;
  }

  // The bone the hit spot follows most, walked up to the humanoid bone it
  // hangs from; tail bones are named for what they are.
  function skinBone(hit) {
    const m = hit.object, g = m.geometry, si = g?.attributes?.skinIndex, sw = g?.attributes?.skinWeight;
    if (!m.isSkinnedMesh || !si || !sw || !hit.face) return null;
    const weight = new Map();
    for (const i of [hit.face.a, hit.face.b, hit.face.c])
      for (let k = 0; k < 4; k++) {
        const w = sw.getComponent(i, k);
        if (w > 0) weight.set(si.getComponent(i, k), (weight.get(si.getComponent(i, k)) || 0) + w);
      }
    let top = -1, best = 0;
    for (const [idx, w] of weight) if (w > best) { best = w; top = idx; }
    let node = m.skeleton.bones[top];
    for (let n = node; n; n = n.parent) {
      if (/tail/i.test(n.name)) return 'tail';
      if (cache.names.has(n)) return cache.names.get(n);
    }
    return null;
  }

  // Without skin weights: the humanoid bone whose segment is nearest
  function nearestBone(vrm, p) {
    let best = null, bestD = Infinity;
    const pos = (n, out) => vrm.humanoid.getRawBoneNode(n)?.getWorldPosition(out);
    for (const [from, to] of SEGMENTS) {
      const a = pos(from, v[0]);
      if (!a) continue;
      const b = (to && pos(to, v[1])) || (to === 'upperChest' && pos('neck', v[1]))
                || v[1].copy(a).add(v[2].set(0, 0.16, 0));          // the head: up to its crown
      const ab = v[2].copy(b).sub(a), t = Math.max(0, Math.min(1, v[3].copy(p).sub(a).dot(ab) / Math.max(ab.lengthSq(), 1e-8)));
      const d = v[4].copy(a).addScaledVector(ab, t).distanceTo(p);
      if (d < bestD) { bestD = d; best = from; }
    }
    return best;
  }

  function zoneOf(vrm, bone, p) {
    if (bone === 'tail') return 'tail';
    if (ARM.test(bone)) return 'arms';
    const part = PART[bone];
    if (part === 'head') return faceZone(vrm, p);
    if (part === 'neck') {                    // her chin can follow the neck bone more than the head's
      const h = local(vrm, 'head', p, v[5]);
      return h && h.y > -0.012 && h.z > 0.02 ? 'mouth' : 'neck';
    }
    if (part === 'hips' || part === 'leg') {
      const h = local(vrm, 'hips', p, v[5]);
      if (!h) return part === 'leg' ? 'legs' : 'tummy';
      if (h.z < -0.01 && h.y > -0.16 && h.y < 0.05) return 'butt';
      if (part === 'leg') return h.y > -0.12 && Math.abs(h.x) < 0.06 ? 'groin' : 'legs';
      return h.y < 0.01 ? 'groin' : 'tummy';
    }
    if (part === 'chest' || part === 'tummy') {
      // skin weights blend across her middle, so the line between them is
      // a height, just above the chest bone; her back is the back half
      const h = local(vrm, vrm.humanoid.getNormalizedBoneNode('chest') ? 'chest' : 'spine', p, v[5]);
      if (!h) return part;
      const up = h.y > 0.04 && local(vrm, 'upperChest', p, v[6]);   // front and back up there: her upper chest's frame
      if ((up && up.y > 0 ? up.z : h.z) < -0.005) return 'back';
      return h.y < 0.04 ? 'tummy' : 'chest';
    }
    return part || null;
  }

  // Head: the top, sides and back are a head pat; the middle of her face
  // is her nose, and below it her mouth.
  function faceZone(vrm, p) {
    const h = local(vrm, 'head', p, v[5]);
    if (!h) return 'head';
    const eye = vrm.humanoid.getRawBoneNode('leftEye');
    const eyeY = eye ? local(vrm, 'head', eye.getWorldPosition(v[6]), v[7]).y : 0.065;
    const span = Math.max(0.03, eyeY);             // eyes above the head bone: her face's own scale
    if (h.z < 0.02 || Math.abs(h.x) > span * 0.55 || h.y > eyeY - span * 0.25) return 'head';
    return h.y > eyeY - span * 0.7 ? 'nose' : 'mouth';
  }

  // The zone under a point on the canvas (client pixels): { zone, point,
  // side } (side: 'left' or 'right', hers, for one-sided gestures), or null.
  // fresh: recompute her bounds first - for a click, not every hover.
  function at(vrm, clientX, clientY, fresh = false) {
    if (!vrm) return null;
    const c = prepare(vrm);
    if (fresh) for (const m of c.meshes) if (m.isSkinnedMesh) { m.boundingSphere = null; m.boundingBox = null; }
    const box = canvas.getBoundingClientRect();
    ndc.set(((clientX - box.left) / box.width) * 2 - 1, -((clientY - box.top) / box.height) * 2 + 1);
    ray.setFromCamera(ndc, camera);
    const hit = ray.intersectObjects(c.meshes.filter(m => m.visible), false)[0];
    if (!hit) return null;
    const bone = skinBone(hit) || nearestBone(vrm, hit.point);
    const zone = bone && zoneOf(vrm, bone, hit.point);
    if (!zone) return null;
    const hx = local(vrm, 'hips', hit.point, v[7])?.x || 0;
    const side = /^left/.test(bone) ? 'left' : /^right/.test(bone) ? 'right' : hx > 0 ? 'left' : 'right';
    return { zone, point: hit.point.clone(), side, bone };
  }

  return { at };
}
