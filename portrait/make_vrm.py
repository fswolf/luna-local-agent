"""Turn the Blender export (portrait/models/luna.glb) into luna.vrm.

    python portrait/make_vrm.py [in.glb] [out.vrm]

A .vrm is a .glb with a VRMC_vrm extension saying what everything is.
This adds it, from names:

  bones       nodes named after VRM humanoid bones (hips, head, leftEye...)
              - build_luna.py names them that way
  expressions shape keys: blinkLeft/blinkRight/happyEyes on the lids,
              happyLower on the lower lids, aa ih ou ee oh smile frown
              gasp on the mouth, combined into VRM's presets
  look-at     "expression" type: looking around slides the Eye material's
              texture (the iris is painted in it), so the eyes stay a
              single surface that can never poke through the lids
  shading     every material becomes MToon - flat anime light with soft
              violet shadows and a magenta rim, like the wallpaper
  hair        bone chains named hair_<chain>_1.. become spring bones, so
              the hair swings when she moves; skinned meshes keep their skins

It also drops anything the export dragged along from other scenes.
"""
import json
import os
import struct
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
SRC = os.path.join(HERE, "models", "luna.glb")
DST = os.path.join(HERE, "models", "luna.vrm")

HUMAN = ["hips", "spine", "chest", "upperChest", "neck", "head", "leftEye", "rightEye",
         "leftShoulder", "leftUpperArm", "leftLowerArm", "leftHand",
         "rightShoulder", "rightUpperArm", "rightLowerArm", "rightHand",
         "leftUpperLeg", "leftLowerLeg", "leftFoot", "rightUpperLeg", "rightLowerLeg", "rightFoot"]

# preset -> [(shape key, weight)], plus what it overrides
EXPRESSIONS = {
    "blink": ([("blinkLeft", 1), ("blinkRight", 1)], {}),
    "blinkLeft": ([("blinkLeft", 1)], {}),
    "blinkRight": ([("blinkRight", 1)], {}),
    "aa": ([("aa", 1)], {}), "ih": ([("ih", 1)], {}), "ou": ([("ou", 1)], {}),
    "ee": ([("ee", 1)], {}), "oh": ([("oh", 1)], {}),
    "happy": ([("happyEyes", 1), ("happyLower", 1), ("smile", 1)], {"overrideBlink": "block"}),
    "relaxed": ([("happyEyes", 0.3), ("smile", 0.6)], {"overrideBlink": "blend"}),
    "sad": ([("frown", 1), ("blinkLeft", 0.15), ("blinkRight", 0.15)], {}),
    "angry": ([("frown", 0.7), ("blinkLeft", 0.3), ("blinkRight", 0.3)], {}),
    "surprised": ([("gasp", 1)], {"overrideBlink": "block"}),
}

# How far the iris texture slides for a full look in each direction (UV units)
LOOK = {"lookLeft": (-0.24, 0.0), "lookRight": (0.24, 0.0), "lookUp": (0.0, 0.14), "lookDown": (0.0, -0.14)}

# MToon: (shade colour as a multiplier of the lit colour, toony, shift)
SHADE = {
    "Luna_Skin": ([0.93, 0.70, 0.78], 0.85, -0.05),
    "Luna_Body": ([0.80, 0.66, 0.80], 0.85, -0.05),
    "Luna_Hair": ([0.55, 0.45, 0.78], 0.90, 0.0),
    "Luna_Ears": ([0.62, 0.52, 0.80], 0.90, 0.0),
    "Luna_Eye": ([0.92, 0.88, 0.94], 0.95, -0.6),
    "Luna_FaceParts": ([0.90, 0.80, 0.86], 0.95, -0.4),
    "Luna_Blush": ([1.0, 1.0, 1.0], 0.95, -1.0),
    "Luna_Top": ([0.75, 0.68, 0.85], 0.9, -0.05),
}


def read_glb(path):
    data = open(path, "rb").read()
    magic, _version, _length = struct.unpack("<III", data[:12])
    assert magic == 0x46546C67, "not a .glb"
    jlen = struct.unpack("<I", data[12:16])[0]
    gltf = json.loads(data[20:20 + jlen])
    blen = struct.unpack("<I", data[20 + jlen:24 + jlen])[0]
    binary = data[28 + jlen:28 + jlen + blen]
    return gltf, binary


def write_glb(path, gltf, binary):
    js = json.dumps(gltf, separators=(",", ":")).encode()
    js += b" " * (-len(js) % 4)
    binary += b"\0" * (-len(binary) % 4)
    with open(path, "wb") as f:
        f.write(struct.pack("<III", 0x46546C67, 2, 28 + len(js) + len(binary)))
        f.write(struct.pack("<II", len(js), 0x4E4F534A) + js)
        f.write(struct.pack("<II", len(binary), 0x004E4942) + binary)


def prune(g, binary):
    """Keep only what the Luna scene uses, and re-pack the binary."""
    scene = next((i for i, s in enumerate(g["scenes"])
                  if any(g["nodes"][n].get("name") == "Luna_Armature" for n in s.get("nodes", []))), g.get("scene", 0))
    keep_nodes, stack = [], list(g["scenes"][scene]["nodes"])
    while stack:
        n = stack.pop()
        if n not in keep_nodes:
            keep_nodes.append(n)
            stack += g["nodes"][n].get("children", [])
    keep_nodes.sort()
    nmap = {o: i for i, o in enumerate(keep_nodes)}
    meshes = sorted({g["nodes"][n]["mesh"] for n in keep_nodes if "mesh" in g["nodes"][n]})
    mmap = {o: i for i, o in enumerate(meshes)}
    mats, accs = set(), set()
    for m in meshes:
        for p in g["meshes"][m]["primitives"]:
            if "material" in p:
                mats.add(p["material"])
            accs.update(p["attributes"].values())
            if "indices" in p:
                accs.add(p["indices"])
            for t in p.get("targets", []):
                accs.update(t.values())
    skins = sorted({g["nodes"][n]["skin"] for n in keep_nodes if "skin" in g["nodes"][n]})
    skmap = {o: i for i, o in enumerate(skins)}
    for sk in skins:
        if "inverseBindMatrices" in g["skins"][sk]:
            accs.add(g["skins"][sk]["inverseBindMatrices"])
    mats = sorted(mats)
    matmap = {o: i for i, o in enumerate(mats)}
    texs = set()

    def walk_tex(obj):
        if isinstance(obj, dict):
            for k, v in obj.items():
                if k.endswith("Texture") and isinstance(v, dict) and "index" in v:
                    texs.add(v["index"])
                walk_tex(v)
        elif isinstance(obj, list):
            for v in obj:
                walk_tex(v)

    for m in mats:
        walk_tex(g["materials"][m])
    texs = sorted(texs)
    tmap = {o: i for i, o in enumerate(texs)}
    imgs = sorted({g["textures"][t]["source"] for t in texs})
    imap = {o: i for i, o in enumerate(imgs)}
    smps = sorted({g["textures"][t]["sampler"] for t in texs if "sampler" in g["textures"][t]})
    smap = {o: i for i, o in enumerate(smps)}
    views = sorted({g["accessors"][a]["bufferView"] for a in accs if "bufferView" in g["accessors"][a]}
                   | {g["images"][i]["bufferView"] for i in imgs if "bufferView" in g["images"][i]})
    accs = sorted(accs)
    amap = {o: i for i, o in enumerate(accs)}

    out = bytearray()
    vmap, new_views = {}, []
    for v in views:
        bv = dict(g["bufferViews"][v])
        out += b"\0" * (-len(out) % 4)
        chunk = binary[bv.get("byteOffset", 0):bv.get("byteOffset", 0) + bv["byteLength"]]
        bv["byteOffset"] = len(out)
        out += chunk
        vmap[v] = len(new_views)
        new_views.append(bv)

    def remap_tex(obj):
        if isinstance(obj, dict):
            out_ = {k: remap_tex(v) for k, v in obj.items()}
            for k, v in obj.items():
                if k.endswith("Texture") and isinstance(v, dict) and v.get("index") in tmap:
                    out_[k] = dict(remap_tex(v), index=tmap[v["index"]])
            return out_
        if isinstance(obj, list):
            return [remap_tex(v) for v in obj]
        return obj

    nodes = []
    for o in keep_nodes:
        n = dict(g["nodes"][o])
        if "children" in n:
            n["children"] = [nmap[c] for c in n["children"] if c in nmap]
        if "mesh" in n:
            n["mesh"] = mmap[n["mesh"]]
        if "skin" in n:
            n["skin"] = skmap[n["skin"]]
        nodes.append(n)
    new_skins = []
    for sk in skins:
        skin = dict(g["skins"][sk])
        skin["joints"] = [nmap[j] for j in skin["joints"]]
        if "skeleton" in skin:
            skin["skeleton"] = nmap.get(skin["skeleton"], skin["joints"][0])
        if "inverseBindMatrices" in skin:
            skin["inverseBindMatrices"] = amap[skin["inverseBindMatrices"]]
        new_skins.append(skin)
    new_meshes = []
    for m in meshes:
        mesh = json.loads(json.dumps(g["meshes"][m]))
        for p in mesh["primitives"]:
            p["attributes"] = {k: amap[v] for k, v in p["attributes"].items()}
            if "indices" in p:
                p["indices"] = amap[p["indices"]]
            if "material" in p:
                p["material"] = matmap[p["material"]]
            for t in p.get("targets", []):
                for k in t:
                    t[k] = amap[t[k]]
        new_meshes.append(mesh)
    new_accs = []
    for a in accs:
        acc = dict(g["accessors"][a])
        if "bufferView" in acc:
            acc["bufferView"] = vmap[acc["bufferView"]]
        new_accs.append(acc)
    new_imgs = []
    for i in imgs:
        img = dict(g["images"][i])
        if "bufferView" in img:
            img["bufferView"] = vmap[img["bufferView"]]
        new_imgs.append(img)
    new_texs = []
    for t in texs:
        tx = dict(g["textures"][t])
        tx["source"] = imap[tx["source"]]
        if "sampler" in tx:
            tx["sampler"] = smap[tx["sampler"]]
        new_texs.append(tx)

    root = [nmap[n] for n in g["scenes"][scene]["nodes"]]
    g2 = {"asset": g["asset"], "scene": 0, "scenes": [{"name": "Luna", "nodes": root}],
          "nodes": nodes, "meshes": new_meshes, "materials": [remap_tex(g["materials"][m]) for m in mats],
          "accessors": new_accs, "bufferViews": new_views, "buffers": [{"byteLength": len(out)}]}
    if new_texs:
        g2.update(textures=new_texs, images=new_imgs, samplers=[g["samplers"][s] for s in smps] or [{}])
    if new_skins:
        g2["skins"] = new_skins
    for k in ("extensionsUsed", "extensionsRequired"):
        if k in g:
            g2[k] = list(g[k])
    return g2, bytes(out)


# Hair that swings: build_luna.py makes bone chains named hair_<chain>_1..3
# with a hair_<chain>_end tail. (stiffness, gravity, drag) per chain.
SPRING = {"bangs": (2.2, 0.08, 0.6), "side": (1.1, 0.15, 0.5), "back": (0.9, 0.18, 0.45)}


def spring_bones(g, names):
    """VRMC_springBone: one spring per hair chain, kept off the head, neck
    and shoulders by sphere colliders."""
    chains = sorted({n[5:].rsplit("_", 1)[0] for n in names if n.startswith("hair_") and n.endswith("_end")})
    if not chains:
        return None
    colliders = []
    for bone, offset, radius in (("head", [0, 0.085, 0], 0.094), ("neck", [0, 0.04, 0], 0.036),
                                 ("upperChest", [0, 0.02, 0], 0.095),
                                 ("leftShoulder", [0, 0.06, 0], 0.045), ("rightShoulder", [0, 0.06, 0], 0.045)):
        if bone in names:
            colliders.append({"node": names[bone], "shape": {"sphere": {"offset": offset, "radius": radius}}})
    springs = []
    for chain in chains:
        joints = [n for n in (f"hair_{chain}_{i}" for i in range(1, 10)) if n in names] + [f"hair_{chain}_end"]
        stiff, grav, drag = SPRING.get(chain.split("_")[0], (1.0, 0.15, 0.5))
        springs.append({"name": f"hair {chain}", "colliderGroups": [0],
                        "joints": [{"node": names[j], "hitRadius": 0.012, "stiffness": stiff, "gravityPower": grav,
                                    "gravityDir": [0, -1, 0], "dragForce": drag} for j in joints]})
    return {"specVersion": "1.0", "colliders": colliders,
            "colliderGroups": [{"name": "body", "colliders": list(range(len(colliders)))}], "springs": springs}


def main(src=SRC, dst=DST):
    g, binary = read_glb(src)
    g, binary = prune(g, binary)
    names = {n.get("name"): i for i, n in enumerate(g["nodes"])}

    missing = [b for b in HUMAN if b not in names]
    if missing:
        sys.exit(f"no node for humanoid bones: {', '.join(missing)}")

    keys = {}   # shape key name -> (node, index)
    for i, n in enumerate(g["nodes"]):
        if "mesh" in n:
            for k, name in enumerate(g["meshes"][n["mesh"]].get("extras", {}).get("targetNames", [])):
                keys[name] = (i, k)

    expressions = {}
    for preset, (binds, override) in EXPRESSIONS.items():
        mb = [{"node": keys[k][0], "index": keys[k][1], "weight": float(w)} for k, w in binds if k in keys]
        if mb:
            expressions[preset] = {"morphTargetBinds": mb, "isBinary": False, "overrideBlink": "none",
                                   "overrideLookAt": "none", "overrideMouth": "none", **override}

    eye_mat = next((i for i, m in enumerate(g["materials"]) if m.get("name") == "Luna_Eye"), None)
    if eye_mat is not None:
        for preset, (du, dv) in LOOK.items():
            expressions[preset] = {"textureTransformBinds": [{"material": eye_mat, "scale": [1.0, 1.0],
                                                              "offset": [du, dv]}],
                                   "isBinary": False, "overrideBlink": "none", "overrideLookAt": "none",
                                   "overrideMouth": "none"}
        # the iris must stop at its edge, not tile
        for t in g.get("textures", []):
            if "sampler" in t:
                g["samplers"][t["sampler"]].update(wrapS=33071, wrapT=33071)

    for m in g["materials"]:
        shade, toony, shift = SHADE.get(m.get("name"), ([0.8, 0.72, 0.85], 0.9, -0.05))
        base = m.get("pbrMetallicRoughness", {}).get("baseColorFactor", [1, 1, 1, 1])
        tex = m.get("pbrMetallicRoughness", {}).get("baseColorTexture")
        mtoon = {
            "specVersion": "1.0", "transparentWithZWrite": False, "renderQueueOffsetNumber": 0,
            "shadeColorFactor": [base[i] * shade[i] for i in range(3)],
            "shadingShiftFactor": shift, "shadingToonyFactor": toony, "giEqualizationFactor": 0.9,
            "matcapFactor": [0, 0, 0],
            "parametricRimColorFactor": [0.55, 0.22, 0.6], "parametricRimFresnelPowerFactor": 4.0,
            "parametricRimLiftFactor": 0.05, "rimLightingMixFactor": 1.0,
            "outlineWidthMode": "none", "outlineWidthFactor": 0, "outlineColorFactor": [0, 0, 0],
            "outlineLightingMixFactor": 1.0,
        }
        if tex:
            mtoon["shadeMultiplyTexture"] = {"index": tex["index"]}
        if m.get("alphaMode") == "BLEND":
            mtoon["renderQueueOffsetNumber"] = 1
        m.setdefault("extensions", {})["VRMC_materials_mtoon"] = mtoon

    rng = {"inputMaxValue": 20.0, "outputScale": 1.0}
    g.setdefault("extensions", {})["VRMC_vrm"] = {
        "specVersion": "1.0",
        "meta": {"name": "Luna", "version": "1", "authors": ["luna-local-agent"],
                 "licenseUrl": "https://vrm.dev/licenses/1.0/", "avatarPermission": "onlyAuthor",
                 "allowExcessivelyViolentUsage": False, "allowExcessivelySexualUsage": False,
                 "commercialUsage": "personalNonProfit", "allowPoliticalOrReligiousUsage": False,
                 "allowAntisocialOrHateUsage": False, "creditNotation": "required",
                 "allowRedistribution": False, "modification": "prohibited"},
        "humanoid": {"humanBones": {b: {"node": names[b]} for b in HUMAN}},
        "lookAt": {"type": "expression", "offsetFromHeadBone": [0.0, 0.06, 0.07],
                   "rangeMapHorizontalInner": rng, "rangeMapHorizontalOuter": rng,
                   "rangeMapVerticalDown": rng, "rangeMapVerticalUp": rng},
        "expressions": {"preset": expressions},
    }
    springs = spring_bones(g, names)
    if springs:
        g["extensions"]["VRMC_springBone"] = springs
    used = set(g.get("extensionsUsed", [])) | {"VRMC_vrm", "VRMC_materials_mtoon"} | (
        {"VRMC_springBone"} if springs else set())
    g["extensionsUsed"] = sorted(used)
    write_glb(dst, g, binary)
    print(f"wrote {dst}: {len(g['nodes'])} nodes, {len(g['meshes'])} meshes, "
          f"{len(expressions)} expressions ({', '.join(sorted(expressions))}), {os.path.getsize(dst) // 1024} KB")


if __name__ == "__main__":
    main(*(sys.argv[1:3]))
