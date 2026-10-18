// Touching her: a click on the portrait finds the spot on her body it
// landed on and names the zone: head, nose, mouth, chest, tummy, groin
// or legs (and neck, arms: nothing set for them yet). What she does about it is portrait.js's business (and
// portrait/touch.json's); this file only answers "where".
//
// A ray goes from the camera through the cursor into the scene and stops
// at the first piece of her it meets. The nearest bone to that point
// says which part of her it is, so the zones follow her wherever she
// moves - leaning, jumping, mid-gesture, any framing, any screen - and a
// part that's out of frame simply can't be touched.
//
// Bones are the standard VRM humanoid ones, so this works on any VRM.
// The face is split using her eyes (VRoid has eye bones; without them
// the eyes are guessed a little above the head bone).

// [bone, the bone its segment runs to, which part of her]
const SEGMENTS = [
  ['hips', 'spine', 'torso'], ['spine', 'chest', 'torso'], ['chest', 'upperChest', 'torso'],
  ['upperChest', 'neck', 'torso'], ['neck', 'head', 'neck'], ['head', null, 'head'],
  ['leftUpperLeg', 'leftLowerLeg', 'leg'], ['rightUpperLeg', 'rightLowerLeg', 'leg'],
  ['leftLowerLeg', 'leftFoot', 'leg'], ['rightLowerLeg', 'rightFoot', 'leg'],
  ['leftUpperArm', 'leftLowerArm', 'arm'], ['rightUpperArm', 'rightLowerArm', 'arm'],
  ['leftLowerArm', 'leftHand', 'arm'], ['rightLowerArm', 'rightHand', 'arm'],
  ['leftHand', null, 'arm'], ['rightHand', null, 'arm'],
];

export function createTouch(THREE, camera, canvas) {
  const ray = new THREE.Raycaster();
  const ndc = new THREE.Vector2();
  const v = (n => Array.from({ length: n }, () => new THREE.Vector3()))(8);

  function pos(vrm, name, out) {
    const b = vrm.humanoid.getRawBoneNode(name);
    return b ? b.getWorldPosition(out) : null;
  }

  // distance from p to the segment a-b
  function toSegment(p, a, b) {
    const ab = v[5].copy(b).sub(a), ap = v[6].copy(p).sub(a);
    const t = Math.max(0, Math.min(1, ap.dot(ab) / Math.max(ab.lengthSq(), 1e-8)));
    return v[7].copy(a).addScaledVector(ab, t).distanceTo(p);
  }

  // her meshes, not the blush/tear overlays or the emotes beside her
  function meshes(vrm) {
    const out = [];
    vrm.scene.traverse(m => { if (m.isMesh && m.visible && !m.userData.overlay) out.push(m); });
    return out;
  }

  // The zone at a point on her
  function zoneAt(vrm, p) {
    let best = null, bestD = Infinity;
    for (const [from, to, part] of SEGMENTS) {
      const a = pos(vrm, from, v[0]);
      if (!a) continue;
      let b = to && pos(vrm, to, v[1]);
      if (!b && to === 'upperChest') b = pos(vrm, 'neck', v[1]);     // no upper chest bone
      if (!b && from === 'head') b = v[1].copy(a).add(v[2].set(0, 0.16, 0));
      if (!b && part === 'arm') {                                     // a hand: out past the wrist
        const elbow = pos(vrm, from.replace('Hand', 'LowerArm'), v[2]);
        b = elbow ? v[1].copy(a).sub(elbow).multiplyScalar(0.6).add(a) : v[1].copy(a);
      }
      if (!b) continue;
      const d = toSegment(p, a, b);
      if (d < bestD) { bestD = d; best = part; }
    }

    const hips = pos(vrm, 'hips', v[3]);
    if (best === 'head') return faceZone(vrm, p);
    if (best === 'neck') {                        // her chin sits nearer the neck bone than the head's
      const head = pos(vrm, 'head', v[2]);
      return head && p.y > head.y - 0.012 && p.z - head.z > 0.02 ? 'mouth' : 'neck';
    }
    if (best === 'arm') return 'arms';
    if (best === 'torso' || best === 'leg') {
      const hipY = hips ? hips.y : 0;
      const chest = pos(vrm, 'chest', v[4]);
      const centre = hips ? Math.abs(p.x - hips.x) : 0;
      if (best === 'leg') return p.y > hipY - 0.12 && centre < 0.06 ? 'groin' : 'legs';
      if (p.y < hipY + 0.01) return 'groin';
      return chest && p.y < chest.y + 0.04 ? 'tummy' : 'chest';
    }
    return null;
  }

  // Head: the top and sides are a head pat; the middle of her face is her
  // nose, and below it her mouth.
  function faceZone(vrm, p) {
    const head = pos(vrm, 'head', v[2]);
    const l = pos(vrm, 'leftEye', v[3]), r = pos(vrm, 'rightEye', v[4]);
    const eyes = l && r ? v[3].add(r).multiplyScalar(0.5) : v[3].copy(head).add(v[4].set(0, 0.065, 0));
    const span = Math.max(0.03, eyes.y - head.y);       // eyes to the head bone: her face's own scale
    const across = Math.abs(p.x - eyes.x);
    const front = p.z - head.z > 0.02;                 // she faces +z (VRM 0.x is turned round on load)
    if (!front || across > span * 0.55 || p.y > eyes.y - span * 0.25) return 'head';
    return p.y > eyes.y - span * 0.7 ? 'nose' : 'mouth';
  }

  // The zone under a point on the canvas (client pixels), with the spot
  function at(vrm, clientX, clientY) {
    if (!vrm) return null;
    const box = canvas.getBoundingClientRect();
    ndc.set(((clientX - box.left) / box.width) * 2 - 1, -((clientY - box.top) / box.height) * 2 + 1);
    ray.setFromCamera(ndc, camera);
    const hit = ray.intersectObjects(meshes(vrm), false)[0];
    if (!hit) return null;
    const zone = zoneAt(vrm, hit.point);
    return zone ? { zone, point: hit.point.clone() } : null;
  }

  return { at };
}
