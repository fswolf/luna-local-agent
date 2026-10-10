"""Export Luna (the "Luna" collection) to portrait/models/luna.glb.

Run inside Blender after build_luna.py. Then, in the repo:

    python portrait/make_vrm.py        # luna.glb -> luna.vrm

Before exporting, the vertex colours build_luna.py paints with (hair
gradient, ears, face parts) are baked into one texture per part, saved
as portrait/textures/luna_<part>.png. The portrait's toon shader lights
and shades a texture properly, where it ignores vertex colours, and it's
where hand-made textures go later: paint over those PNGs (same UVs) and
export again with LUNA_KEEP_TEXTURES=1 so they aren't baked over.

The .glb is plain glTF: meshes, the bone hierarchy, shape keys and
textures. Everything VRM-specific - which bone is the head, which
shape key is a blink, the toon shading - is added by make_vrm.py.
"""
import os

import bpy

REPO = os.environ.get("LUNA_REPO") or os.path.expanduser("~/ai-voice")
OUT = os.path.join(REPO, "portrait", "models", "luna.glb")
TEXTURES = os.path.join(REPO, "portrait", "textures")
KEEP = os.environ.get("LUNA_KEEP_TEXTURES") == "1"
SIZES = {"Luna_HairBack": 1024, "Luna_HairBangs": 1024, "Luna_HairSides": 512, "Luna_HairCap": 1024,
         "Luna_Lids": 512, "Luna_Mouth": 256, "Luna_Details": 512}


def export_uv_layouts(coll):
    """A UV layout picture per textured part (portrait/textures/uv/), the
    template for painting or generating that part's texture."""
    out = os.path.join(TEXTURES, "uv")
    os.makedirs(out, exist_ok=True)
    for ob in coll.objects:
        if ob.type != "MESH" or not ob.data.uv_layers or ob.name in ("Luna_Eyes",):
            continue
        for o in bpy.context.selected_objects:
            o.select_set(False)
        ob.select_set(True)
        bpy.context.view_layer.objects.active = ob
        size = SIZES.get(ob.name, 512)
        bpy.ops.object.mode_set(mode="EDIT")
        bpy.ops.mesh.select_all(action="SELECT")
        try:
            bpy.ops.uv.export_layout(filepath=os.path.join(out, ob.name.lower() + "_uv.png"),
                                     size=(size, size), opacity=0.0, export_all=True)
        except Exception as e:
            print("uv layout failed for", ob.name, e)
        bpy.ops.object.mode_set(mode="OBJECT")


def lin(h):
    h = h.lstrip("#")
    return [((int(h[i:i + 2], 16) / 255 + 0.055) / 1.055) ** 2.4 for i in (0, 2, 4)]


def hair_texture(path, w=512, h=1024):
    """The one texture every hair piece shares. Down (v): near-black indigo
    at the roots to magenta ends. Left half the normal hair, right half the
    violet streak. Fine strand lines and a shine band, so it reads as hair.
    Replace luna_hair.png with a nicer one (same layout) any time."""
    import numpy as np
    stops = [(0.0, "#17112d"), (0.42, "#33275f"), (0.66, "#5b46a8"), (0.9, "#d65ec6"), (1.0, "#f08ad6")]
    streak = [(0.0, "#5b46a8"), (0.35, "#5b46a8"), (1.0, "#8f5cf0")]

    def ramp(st, v):
        out = np.zeros(v.shape + (3,))
        for (a, ca), (b, cb) in zip(st, st[1:]):
            m = (v >= a) & (v <= b)
            k = ((v[m] - a) / (b - a))[:, None]
            out[m] = np.array(lin(ca)) * (1 - k) + np.array(lin(cb)) * k
        return out

    v = (np.arange(h) + 0.5) / h
    x = np.arange(w)
    img = np.zeros((h, w, 4))
    left = ramp(stops, v)[:, None, :].repeat(w // 2, 1)
    right = ramp(streak, v)[:, None, :].repeat(w - w // 2, 1)
    img[:, :w // 2, :3] = left
    img[:, w // 2:, :3] = right
    rng = np.random.default_rng(7)
    lines = 0.88 + 0.12 * np.sin(x * 0.9 + rng.normal(0, 0.6, w).cumsum() * 0.3)
    img[:, :, :3] *= lines[None, :, None]
    shine = 0.55 * np.exp(-((v - 0.24) / 0.035) ** 2)
    img[:, :, :3] += shine[:, None, None] * np.array(lin("#7f6ad0"))[None, None, :]
    img[:, :, 3] = 1
    im = bpy.data.images.get("luna_hair") or bpy.data.images.new("luna_hair", w, h, float_buffer=True)
    if tuple(im.size) != (w, h):
        im.scale(w, h)
    im.pixels.foreach_set(img.astype("float32").ravel())
    im.filepath_raw = path
    im.file_format = "PNG"
    im.save()
    return im


def blush_texture(path, size=256):
    """A pink radial fade: strongest in the middle, nothing at the edge."""
    import numpy as np
    y, x = np.mgrid[0:size, 0:size]
    r = np.hypot((x + 0.5) / size - 0.5, (y + 0.5) / size - 0.5) * 2
    img = np.zeros((size, size, 4))
    img[..., :3] = lin("#ff6f9e")
    img[..., 3] = np.clip(1 - r * r, 0, 1) ** 1.5 * 0.75
    im = bpy.data.images.get("luna_blush_fade") or bpy.data.images.new("luna_blush_fade", size, size, alpha=True,
                                                                       float_buffer=True)
    im.pixels.foreach_set(img.astype("float32").ravel())
    im.filepath_raw = path
    im.file_format = "PNG"
    im.save()
    return im


def textured_material(old, img, name):
    mat = old.copy()
    mat.name = name
    nt = mat.node_tree
    bsdf = next(n for n in nt.nodes if n.type == "BSDF_PRINCIPLED")
    for n in [n for n in nt.nodes if n.type in ("VERTEX_COLOR", "TEX_IMAGE")]:
        nt.nodes.remove(n)
    tex = nt.nodes.new("ShaderNodeTexImage")
    tex.image = img
    nt.links.new(tex.outputs["Color"], bsdf.inputs["Base Color"])
    return mat


def bake_textures(coll):
    """Vertex colours -> a texture per part, and the part's material uses it."""
    sc = bpy.context.scene
    engine = sc.render.engine
    sc.render.engine = "CYCLES"
    sc.cycles.samples = 1
    sc.render.bake.margin = 6
    hair_mat = None
    for ob in coll.objects:
        if ob.type != "MESH":
            continue
        kind = ob.get("luna_tex")
        if kind == "hair":       # one shared hair texture, not a bake
            path = os.path.join(TEXTURES, "luna_hair.png")
            if hair_mat is None:
                img = (bpy.data.images.load(path, check_existing=True) if KEEP and os.path.exists(path)
                       else hair_texture(path))
                hair_mat = textured_material(ob.active_material, img, "Luna_Hair_Tex")
            ob.data.materials[0] = hair_mat
            print("textured", ob.name, "-> luna_hair.png")
            continue
        if kind == "blush":
            path = os.path.join(TEXTURES, "luna_blush.png")
            img = (bpy.data.images.load(path, check_existing=True) if KEEP and os.path.exists(path)
                   else blush_texture(path))
            mat = textured_material(ob.active_material, img, "Luna_Blush_Tex")
            nt = mat.node_tree
            bsdf = next(n for n in nt.nodes if n.type == "BSDF_PRINCIPLED")
            tex = next(n for n in nt.nodes if n.type == "TEX_IMAGE")
            nt.links.new(tex.outputs["Alpha"], bsdf.inputs["Alpha"])
            for attr, value in (("surface_render_method", "BLENDED"), ("blend_method", "BLEND")):
                try:
                    setattr(mat, attr, value)
                except (AttributeError, TypeError):
                    pass
            ob.data.materials[0] = mat
            print("textured", ob.name, "-> luna_blush.png")
            continue
        if kind == "face" or "Col" not in ob.data.color_attributes:
            # no vertex colours to bake: use a hand-made texture if there is one
            path = os.path.join(TEXTURES, ob.name.replace("Luna_", "luna_").lower() + ".png")
            if os.path.exists(path) and ob.data.uv_layers and ob.active_material:
                ob.data.materials[0] = textured_material(
                    ob.active_material, bpy.data.images.load(path, check_existing=True),
                    ob.active_material.name + "_Tex")
                print("textured", ob.name, "->", os.path.basename(path))
            continue
        if not ob.data.uv_layers:
            continue
        old = ob.active_material
        if old is None:
            continue
        name = ob.name.replace("Luna_", "luna_").lower()
        path = os.path.join(TEXTURES, f"{name}.png")
        img = bpy.data.images.get(name)
        if KEEP and os.path.exists(path):
            img = bpy.data.images.load(path, check_existing=True)
        else:
            size = SIZES.get(ob.name, 512)
            if img is None or tuple(img.size) != (size, size):
                if img:
                    bpy.data.images.remove(img)
                img = bpy.data.images.new(name, size, size, alpha=True)
            # bake: emission straight from the vertex colour
            bake = old.copy()
            bake.name = old.name + "_bake"
            nt = bake.node_tree
            nt.nodes.clear()
            out = nt.nodes.new("ShaderNodeOutputMaterial")
            vc = nt.nodes.new("ShaderNodeVertexColor")
            vc.layer_name = "Col"
            em = nt.nodes.new("ShaderNodeEmission")
            tex = nt.nodes.new("ShaderNodeTexImage")
            tex.image = img
            nt.links.new(vc.outputs["Color"], em.inputs["Color"])
            nt.links.new(em.outputs[0], out.inputs[0])
            nt.nodes.active = tex
            ob.data.materials[0] = bake
            for o in bpy.context.selected_objects:
                o.select_set(False)
            ob.select_set(True)
            bpy.context.view_layer.objects.active = ob
            bpy.ops.object.bake(type="EMIT", margin=6)
            img.filepath_raw = path
            img.file_format = "PNG"
            img.save()
            bpy.data.materials.remove(bake)
        # the part's own material: the old one, with the texture as its colour
        mat = old.copy()
        mat.name = old.name + "_" + ob.name.split("_", 1)[1]
        nt = mat.node_tree
        bsdf = next(n for n in nt.nodes if n.type == "BSDF_PRINCIPLED")
        for n in [n for n in nt.nodes if n.type == "VERTEX_COLOR"]:
            nt.nodes.remove(n)
        tex = nt.nodes.new("ShaderNodeTexImage")
        tex.image = img
        nt.links.new(tex.outputs["Color"], bsdf.inputs["Base Color"])
        if old.name == "Luna_Blush":     # see-through: alpha from the texture too
            nt.links.new(tex.outputs["Alpha"], bsdf.inputs["Alpha"])
        ob.data.materials[0] = mat
        print("textured", ob.name, "->", os.path.basename(path))
    sc.render.engine = engine


def main():
    sc = bpy.data.scenes["Luna VRM"]
    bpy.context.window.scene = sc
    coll = bpy.data.collections["Luna"]
    if bpy.context.object and bpy.context.object.mode != "OBJECT":
        bpy.ops.object.mode_set(mode="OBJECT")
    for o in sc.objects:
        o.select_set(False)
    for o in coll.objects:
        o.hide_set(False)
        o.select_set(True)
    bake_textures(coll)
    if os.environ.get("LUNA_UV_LAYOUTS", "1") == "1":
        export_uv_layouts(coll)
    for o in sc.objects:
        o.select_set(False)
    for o in coll.objects:
        o.select_set(True)
    bpy.context.view_layer.objects.active = coll.objects["Luna_Armature"]
    os.makedirs(os.path.dirname(OUT), exist_ok=True)

    kwargs = dict(filepath=OUT, export_format="GLB", use_selection=True, export_apply=True,
                  export_morph=True, export_morph_normal=False, export_yup=True,
                  export_texcoords=True, export_normals=True, export_materials="EXPORT",
                  export_cameras=False, export_lights=False, export_animations=False)
    # vertex colours: the option's name and values moved between Blender versions
    for extra in ({"export_vertex_color": "ACTIVE"}, {"export_colors": True}, {}):
        try:
            bpy.ops.export_scene.gltf(**kwargs, **extra)
            break
        except TypeError:
            continue
    print("exported", OUT, os.path.getsize(OUT) // 1024, "KB")


main()
