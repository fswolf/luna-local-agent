"""Build Luna's model in Blender, ready to export for the portrait window.

Run inside Blender (Scripting tab -> Open -> Run, or blender --python).
It (re)builds everything in a scene called "Luna VRM", in real-world
metres, facing -Y the way Blender characters do:

  Luna_Face       head, smooth (subdivision applied on export)
  Luna_Eyes       both eyes, one textured surface - the iris is in the
                  texture (portrait/textures/iris.png), and looking around
                  slides the texture, which is how many anime VRMs do it
  Luna_Lids       upper lids + lashes   shape keys: blinkLeft, blinkRight, happyEyes
  Luna_LowerLids  lower lids            shape key:  happyLower
  Luna_Mouth      lips, mouth, fang, teeth, tongue
                  shape keys: aa ih ou ee oh smile frown gasp
  Luna_Details    brows, lower lashes, nose shadow, blush lines
  Luna_Blush      soft cheek blush (see-through)
  Luna_Hair*      cap, bangs, side locks, long back hair - purple to magenta
  Luna_Ear_L/R    cat ears, each on its own bone so it can twitch
  Luna_Body       neck, shoulders, top, choker
  Luna_Armature   VRM humanoid bone names, so the converter can map them

Then portrait/blender/export_luna.py writes portrait/models/luna.glb and
portrait/make_vrm.py turns that into luna.vrm.

Everything is generated from the numbers below; change a number, run it
again, and the scene is rebuilt from scratch. Nothing outside the
"Luna VRM" scene is touched.
"""
import math
import os

import bmesh
import bpy
from mathutils import Matrix, Vector
from mathutils.bvhtree import BVHTree

REPO = os.environ.get("LUNA_REPO") or os.path.expanduser("~/ai-voice")
TEXTURES = os.path.join(REPO, "portrait", "textures")
SCENE = "Luna VRM"
COLL = "Luna"
# "bob" (short, like most of her pictures) or "long" (the first wallpaper)
HAIR_STYLE = os.environ.get("LUNA_HAIR", "bob")


def hexc(h, a=1.0):
    h = h.lstrip("#")
    c = [int(h[i:i + 2], 16) / 255 for i in (0, 2, 4)]
    # vertex colours are linear in Blender; the palette is written in sRGB
    return tuple(((x + 0.055) / 1.055) ** 2.4 if x > 0.04045 else x / 12.92 for x in c) + (a,)


PAL = {
    "skin": hexc("#f7e3e9"), "skin_shade": hexc("#e9c0cd"), "blush": hexc("#ff6f9e", 0.26),
    "blush_line": hexc("#f0819f"),
    "hair_top": hexc("#17112d"), "hair_mid": hexc("#33275f"), "hair_violet": hexc("#5b46a8"),
    "hair_tip": hexc("#d65ec6"), "hair_tip2": hexc("#f08ad6"), "hair_streak": hexc("#8f5cf0"),
    "ear_out": hexc("#1f1838"), "ear_in": hexc("#e8869f"), "fur": hexc("#fbf2f7"),
    "lash": hexc("#120c19"), "lower_lash": hexc("#7a3550"), "brow": hexc("#2a2050"),
    "lip": hexc("#4d1426"), "mouth": hexc("#7c2239"), "tongue": hexc("#e8708f"), "tooth": hexc("#fffafc"),
    "top": hexc("#151019"), "choker": hexc("#100c14"), "metal": hexc("#cfc8dc"),
}

HC = Vector((0.0, 0.0, 1.47))         # head centre
HR = Vector((0.087, 0.090, 0.097))    # half sizes: x, depth (y), height

EYE_X, EYE_Z = 0.0335, 1.452
EYE_W, EYE_H = 0.0205, 0.0245
MOUTH_Z, MOUTH_W = 1.394, 0.0118


# ---------------------------------------------------------------------------
# Scene
# ---------------------------------------------------------------------------
def scene():
    sc = bpy.data.scenes.get(SCENE) or bpy.data.scenes.new(SCENE)
    bpy.context.window.scene = sc
    coll = bpy.data.collections.get(COLL)
    if coll:
        for o in list(coll.objects):
            bpy.data.objects.remove(o, do_unlink=True)
    else:
        coll = bpy.data.collections.new(COLL)
    if coll.name not in sc.collection.children:
        sc.collection.children.link(coll)
    # any older parts in this scene stay, but out of the way
    for c in sc.collection.children:
        if c != coll:
            lc = bpy.context.view_layer.layer_collection.children.get(c.name)
            if lc:
                lc.exclude = True
    for m in list(bpy.data.meshes):
        if m.users == 0:
            bpy.data.meshes.remove(m)
    return sc, coll


def material(name, color=(1, 1, 1, 1), vc=False, image=None, blend=False, rough=0.75):
    m = bpy.data.materials.get(name) or bpy.data.materials.new(name)
    m.use_nodes = True
    nt = m.node_tree
    nt.nodes.clear()
    out = nt.nodes.new("ShaderNodeOutputMaterial")
    bsdf = nt.nodes.new("ShaderNodeBsdfPrincipled")
    bsdf.inputs["Base Color"].default_value = color
    bsdf.inputs["Roughness"].default_value = rough
    nt.links.new(bsdf.outputs[0], out.inputs[0])
    if vc:
        attr = nt.nodes.new("ShaderNodeVertexColor")
        attr.layer_name = "Col"
        nt.links.new(attr.outputs["Color"], bsdf.inputs["Base Color"])
        if blend:
            nt.links.new(attr.outputs["Alpha"], bsdf.inputs["Alpha"])
    if image:
        tex = nt.nodes.new("ShaderNodeTexImage")
        tex.image = bpy.data.images.load(image, check_existing=True)
        tex.extension = "EXTEND"
        nt.links.new(tex.outputs["Color"], bsdf.inputs["Base Color"])
    if blend:
        for attr, value in (("surface_render_method", "BLENDED"), ("blend_method", "BLEND")):
            try:
                setattr(m, attr, value)
            except (AttributeError, TypeError):
                pass
    m.diffuse_color = color
    return m


def make_obj(coll, name, verts, faces, colors=None, mat=None, uvs=None, smooth=True, subsurf=0):
    me = bpy.data.meshes.new(name)
    me.from_pydata([tuple(v) for v in verts], [], faces)
    me.update()
    if colors is not None:
        attr = me.color_attributes.new("Col", "FLOAT_COLOR", "POINT")
        for i, c in enumerate(colors):
            attr.data[i].color = c
    if uvs is not None:
        uv = me.uv_layers.new(name="UVMap")
        for poly in me.polygons:
            for li in poly.loop_indices:
                uv.data[li].uv = uvs[me.loops[li].vertex_index]
    for p in me.polygons:
        p.use_smooth = smooth
    if mat:
        me.materials.append(mat)
    ob = bpy.data.objects.new(name, me)
    coll.objects.link(ob)
    if subsurf:
        mod = ob.modifiers.new("Subdivision", "SUBSURF")
        mod.levels = subsurf
        mod.render_levels = subsurf
    return ob


def face_normals(ob, face):
    """Give a decal mesh (lids, mouth, brows...) the normals of the face
    under it: lit like the skin, it can't show as a lighter patch."""
    bpy.context.view_layer.update()
    bvh = BVHTree.FromObject(face, bpy.context.evaluated_depsgraph_get())
    normals = []
    for v in ob.data.vertices:
        loc, n, _i, _d = bvh.find_nearest(v.co)
        normals.append(n if n is not None else Vector((0, -1, 0)))
    ob.data.normals_split_custom_set_from_vertices(normals)


def push_out(ob, solid, margin=0.0035):
    """Move any vertex of ob that's inside (or touching) solid's surface out
    to `margin` above it - hair through the face or the skull is the most
    visible mistake a hair mesh can make."""
    bpy.context.view_layer.update()
    bvh = BVHTree.FromObject(solid, bpy.context.evaluated_depsgraph_get())
    moved = 0
    for v in ob.data.vertices:
        hit, n, _i, _d = bvh.find_nearest(v.co)
        if hit is None:
            continue
        if (v.co - hit).dot(n) < margin:
            v.co = hit + n * margin
            moved += 1
    ob.data.update()
    return moved


def outward(ob):
    """Point every face outwards (the generators don't promise a winding)."""
    bm = bmesh.new()
    bm.from_mesh(ob.data)
    bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
    bm.to_mesh(ob.data)
    bm.free()


def add_keys(ob, keys):
    """keys: {name: [Vector per vertex]} absolute positions."""
    ob.shape_key_add(name="Basis", from_mix=False)
    for name, pos in keys.items():
        k = ob.shape_key_add(name=name, from_mix=False)
        for i, p in enumerate(pos):
            k.data[i].co = p
        k.value = 0.0      # Blender 5 starts new keys at 1


# ---------------------------------------------------------------------------
# Head
# ---------------------------------------------------------------------------
def head_point(u, v, grow=0.0):
    """u: around the head, 0 = the face; v: up/down. Anime proportions: a
    round cranium, a flat-ish face, a narrow jaw to a small pointed chin."""
    x = math.cos(v) * math.sin(u)
    y = -math.cos(v) * math.cos(u)
    z = math.sin(v)
    r = HR + Vector((grow, grow, grow))
    p = Vector((x * r.x, y * r.y, z * r.z))
    front = max(0.0, math.cos(u))
    if z < 0:
        t = min(1.0, -z)
        p.x *= 1 - 0.34 * t ** 1.4
        p.y *= 1 - 0.18 * t
        p.z *= 1 - 0.02 * t ** 1.5
        p.y -= 0.010 * t ** 2.2 * front ** 2
    if y < 0:   # the face: flatter, cheeks a touch fuller under the eyes
        p.y *= 1 - 0.13 * front * (1 - abs(z) ** 1.5)
        p.x *= 1 + 0.035 * front * max(0.0, 1 - abs(z + 0.25) * 2.2)
    else:       # the back of the skull: rounder
        p.y *= 1.04
    if front > 0.5 and grow == 0.0:
        p += face_detail(p) * min(1.0, (front - 0.5) * 4)
    return HC + p


def gauss(d, w):
    return math.exp(-(d / w) ** 2)


def face_detail(q):
    """Small anime features, as offsets on the face (q is relative to HC).
    Kept subtle: an anime face is mostly flat planes and a tiny nose."""
    x, z = q.x, q.z
    d = Vector((0, 0, 0))
    # the nose: a soft bridge that rises to a small tip, then tucks under
    if -0.054 < z < -0.022:
        ramp = max(0.0, min(1.0, (-0.022 - z) / 0.026)) ** 1.6
        under = gauss(z + 0.050, 0.004)
        d.y -= (0.0036 * ramp + 0.0010 * under) * gauss(x, 0.0050 + 0.0015 * ramp)
    # cheeks: fuller under the eyes, rounding into the jaw
    for sx in (1, -1):
        d.y -= 0.0032 * gauss(x - sx * 0.046, 0.016) * gauss(z + 0.048, 0.018)
        # eye sockets: a whisper of depth, so the eyes sit in the face
        d.y += 0.0016 * gauss(x - sx * 0.034, 0.014) * gauss(z + 0.019, 0.010)
        # brow ridge
        d.y -= 0.0012 * gauss(x - sx * 0.030, 0.020) * gauss(z - 0.014, 0.006)
    # lips and chin
    d.y -= 0.0010 * gauss(x, 0.011) * gauss(z + 0.074, 0.004)
    d.y -= 0.0018 * gauss(x, 0.014) * gauss(z + 0.093, 0.007)
    return d


def build_head(coll, mats):
    U, V = 128, 80
    verts, faces = [], []
    for j in range(V + 1):
        v = -math.pi / 2 + math.pi * j / V
        for i in range(U):
            u = 2 * math.pi * i / U
            verts.append(head_point(u, v))
    for j in range(V):
        for i in range(U):
            a = j * U + i
            b = j * U + (i + 1) % U
            faces.append((a, b, b + U, a + U))
    # UVs: a straight projection from the front, so a face texture is simply
    # a front view of her face (the back of the head is under the hair)
    uvs = [((v.x - HC.x) / 0.20 + 0.5, (v.z - 1.355) / 0.22) for v in verts]
    ob = make_obj(coll, "Luna_Face", verts, faces, mat=mats["skin"], uvs=uvs, subsurf=1)
    ob["luna_tex"] = "face"
    me = ob.data
    bm = bmesh.new()
    bm.from_mesh(me)
    bmesh.ops.remove_doubles(bm, verts=bm.verts, dist=1e-6)
    bm.to_mesh(me)
    bm.free()
    return ob


class Surface:
    """Rays at the face from the front, for laying features onto it."""

    def __init__(self, ob):
        dg = bpy.context.evaluated_depsgraph_get()
        self.bvh = BVHTree.FromObject(ob, dg)

    def at(self, x, z, lift=0.0):
        hit, n, _i, _d = self.bvh.ray_cast(Vector((x, -0.5, z)), Vector((0, 1, 0)))
        if hit is None:
            return Vector((x, HC.y - 0.02, z))
        return hit + n * lift


# ---------------------------------------------------------------------------
# Eyes, lids, mouth
# ---------------------------------------------------------------------------
def eye_top(t):
    """Upper lid line, t from -1 (inner corner) to 1 (outer): a flattened
    arch that lifts towards the outer corner."""
    t = max(-1.0, min(1.0, t))
    return EYE_Z + EYE_H * 0.64 * max(0.0, 1 - t * t) ** 0.5 + 0.005 * t + 0.0015


def eye_bottom(t):
    t = max(-1.0, min(1.0, t))
    return EYE_Z - EYE_H * 0.50 * max(0.0, 1 - t * t) ** 0.8 + 0.0028 * t


def ex(side, t):
    return side * (EYE_X + t * EYE_W)


def build_eyes(coll, mats, S):
    """One textured surface per eye, filling the opening (and a little
    under the lids). UVs centre the iris texture on the eye."""
    verts, faces, uvs = [], [], []
    IRX, IRZ = 0.0125, 0.0172   # the iris in the texture spans this
    cols, rows = 26, 12
    for side in (1, -1):
        start = len(verts)
        for i in range(cols + 1):
            t = -1.04 + 2.08 * i / cols
            top, bot = eye_top(t) + 0.002, eye_bottom(t) - 0.0016
            for j in range(rows + 1):
                z = bot + (top - bot) * j / rows
                x = ex(side, t)
                verts.append(S.at(x, z, 0.0005))
                uvs.append(((x - side * EYE_X) / (2 * IRX) + 0.5,
                            (z - (EYE_Z + 0.001)) / (2 * IRZ) + 0.5))
        for i in range(cols):
            for j in range(rows):
                a = start + i * (rows + 1) + j
                f = (a, a + rows + 1, a + rows + 2, a + 1)
                faces.append(f if side < 0 else f[::-1])
    return make_obj(coll, "Luna_Eyes", verts, faces, mat=mats["eye"], uvs=uvs)


def build_lids(coll, mats, S):
    verts, colors, faces = [], [], []
    open_pos, closed, happy = [], [], []
    cols = 22

    def put(p_open, p_closed, p_happy, c):
        verts.append(p_open)
        closed.append(p_closed)
        happy.append(p_happy)
        colors.append(c)
        return len(verts) - 1

    for side in (1, -1):
        rows = [[], [], [], []]
        for i in range(cols + 1):
            t = -1.08 + 2.5 * i / cols           # past the outer corner: the wing
            tt = max(-1.0, min(1.0, t))
            wing = max(0.0, t - 1.0)
            lash = 0.0026 + 0.0016 * max(0.0, tt) + (-0.0026 * wing / 1.42 if wing else 0)
            top = eye_top(tt) + wing * 0.007
            x = ex(side, t)
            closed_line = EYE_Z - 0.0035 - 0.0035 * math.sin(math.pi * (tt + 1) / 2) + 0.0015 * tt
            happy_line = EYE_Z - 0.002 + 0.0075 * math.sin(math.pi * (tt + 1) / 2)
            open_z = [top + lash + 0.0022, top + lash, top + lash, top]
            shut_z = [top + lash + 0.0022, closed_line + lash * 0.8, closed_line + lash * 0.8, closed_line]
            happy_z = [top + lash + 0.0022, happy_line + lash * 0.8, happy_line + lash * 0.8, happy_line]
            if wing:   # the wing keeps its flick when shut
                shut_z = [z - (top - closed_line) * 0.9 for z in open_z]
                happy_z = [z - (top - happy_line) * 0.9 for z in open_z]
            for r in range(4):
                lift = 0.0012 + 0.0003 * r
                c = PAL["skin"] if r < 2 else PAL["lash"]
                rows[r].append(put(S.at(x, open_z[r], lift), S.at(x, shut_z[r], lift),
                                   S.at(x, happy_z[r], lift), c))
        for i in range(cols):
            for r in (0, 2):
                f = (rows[r][i], rows[r][i + 1], rows[r + 1][i + 1], rows[r + 1][i])
                faces.append(f if side > 0 else f[::-1])
        # lash flicks at the outer corner, riding with the lash line
        for k, (t0, up, out) in enumerate(((0.55, 0.0045, 0.002), (0.82, 0.0055, 0.0032), (1.08, 0.006, 0.0042))):
            i = min(cols, int((t0 + 1.08) / 2.5 * cols))
            base = rows[2][i]
            tip_open = verts[base] + Vector((side * out, 0, up))
            d_closed = closed[base] - verts[base]
            d_happy = happy[base] - verts[base]
            a = put(verts[base] + Vector((-side * 0.0012, 0, -0.0004)), closed[base] + Vector((-side * 0.0012, 0, -0.0004)),
                    happy[base] + Vector((-side * 0.0012, 0, -0.0004)), PAL["lash"])
            b = put(verts[base] + Vector((side * 0.0012, 0, -0.0004)), closed[base] + Vector((side * 0.0012, 0, -0.0004)),
                    happy[base] + Vector((side * 0.0012, 0, -0.0004)), PAL["lash"])
            c = put(tip_open, tip_open + d_closed + Vector((0, 0, -up * 1.6)), tip_open + d_happy, PAL["lash"])
            faces.append((a, b, c) if side > 0 else (b, a, c))

    ob = make_obj(coll, "Luna_Lids", verts, faces, colors, mats["face_vc"])
    left = [v if (verts[i].x > 0) else verts[i] for i, v in enumerate(closed)]
    right = [v if (verts[i].x < 0) else verts[i] for i, v in enumerate(closed)]
    add_keys(ob, {"blinkLeft": left, "blinkRight": right, "happyEyes": happy})
    return ob


def build_lower_lids(coll, mats, S):
    verts, colors, faces, happy = [], [], [], []
    cols = 18
    for side in (1, -1):
        rows = [[], []]
        for i in range(cols + 1):
            t = -1.04 + 2.08 * i / cols
            x = ex(side, t)
            b = eye_bottom(t)
            happy_line = EYE_Z - 0.002 + 0.0075 * math.sin(math.pi * (max(-1, min(1, t)) + 1) / 2) - 0.0012
            for r, (zo, zh) in enumerate(((b - 0.0022, b - 0.0022), (b - 0.0016, happy_line))):
                verts.append(S.at(x, zo, 0.0010))
                happy.append(S.at(x, zh, 0.0010))
                colors.append(PAL["skin"])
                rows[r].append(len(verts) - 1)
        for i in range(cols):
            f = (rows[0][i], rows[0][i + 1], rows[1][i + 1], rows[1][i])
            faces.append(f if side < 0 else f[::-1])
    ob = make_obj(coll, "Luna_LowerLids", verts, faces, colors, mats["face_vc"])
    add_keys(ob, {"happyLower": happy})
    return ob


def build_mouth(coll, mats, S):
    """A decal on the face: the lip line closed, a mouth when open. The
    fang and the upper teeth ride the upper lip; the tongue sits low."""
    verts, colors, faces = [], [], []
    rings = (0.0, 0.42, 0.78, 1.0)
    n = 36
    base_h = 0.0005

    def shape(r, a, sx, top, bottom, smile=0.0, frown=0.0, round_=0.0):
        c, s = math.cos(a), math.sin(a)
        x = MOUTH_W * sx * (1 - 0.42 * round_) * c * r
        h = top if s > 0 else bottom
        z = (h * abs(s) ** (0.85 - 0.3 * round_) * (1 if s > 0 else -1) + base_h * s) * r
        z += (smile * 0.0058 - frown * 0.0034) * (c * c) * r ** 2 - smile * 0.0012 * r
        return x, MOUTH_Z + z

    SHAPES = {
        "Basis": dict(sx=1.0, top=0.0, bottom=0.0, smile=0.25),
        "aa": dict(sx=0.86, top=0.0035, bottom=0.0115, smile=0.25),
        "ih": dict(sx=1.06, top=0.0018, bottom=0.0042, smile=0.35),
        "ou": dict(sx=0.56, top=0.0028, bottom=0.0060, round_=1.0),
        "ee": dict(sx=1.16, top=0.0022, bottom=0.0050, smile=0.7),
        "oh": dict(sx=0.72, top=0.0036, bottom=0.0090, round_=0.6),
        "smile": dict(sx=1.12, top=0.0012, bottom=0.0042, smile=1.15),
        "frown": dict(sx=0.92, top=0.0, bottom=0.0004, frown=1.0),
        "gasp": dict(sx=0.50, top=0.0050, bottom=0.0080, round_=1.0),
    }
    pos = {k: [] for k in SHAPES}

    def add(fn, color, lift):
        for k, sh in SHAPES.items():
            x, z = fn(sh)
            pos[k].append(S.at(x, z, lift))
        colors.append(color)
        return len(colors) - 1

    centre = add(lambda sh: shape(0.0, 0.0, **sh), PAL["mouth"], 0.0007)
    grid = []
    for r in rings[1:]:
        row = []
        for k in range(n):
            a = 2 * math.pi * k / n
            low = math.sin(a) < -0.15
            col = PAL["lip"] if r == 1.0 else (PAL["tongue"] if (low and r <= 0.42) else PAL["mouth"])
            row.append(add(lambda sh, r=r, a=a: shape(r, a, **sh), col, 0.0007))
        grid.append(row)
    for k in range(n):
        faces.append((centre, grid[0][(k + 1) % n], grid[0][k]))
        for g in range(len(grid) - 1):
            faces.append((grid[g][k], grid[g][(k + 1) % n], grid[g + 1][(k + 1) % n], grid[g + 1][k]))

    def top_edge(x_frac, sh):
        # z of the upper lip at a given fraction of the half-width
        a = math.acos(max(-1.0, min(1.0, x_frac)))
        return shape(1.0, a, **sh)

    # upper teeth: a strip under the upper lip that only has height when open
    teeth_top, teeth_bot = [], []
    for k in range(9):
        f = -0.7 + 1.4 * k / 8
        teeth_top.append(add(lambda sh, f=f: (top_edge(f, sh)[0] * 0.97, top_edge(f, sh)[1] - 0.0002),
                             PAL["tooth"], 0.0009))
        teeth_bot.append(add(lambda sh, f=f: (top_edge(f, sh)[0] * 0.97,
                                              top_edge(f, sh)[1] - 0.0002 - min(0.0016, sh["top"] * 0.45)),
                             PAL["tooth"], 0.0009))
    for k in range(8):
        faces.append((teeth_top[k], teeth_top[k + 1], teeth_bot[k + 1], teeth_bot[k])[::-1])

    # the fang - her right side, the way it shows in the wallpaper
    fx = -0.42
    fa = add(lambda sh: (top_edge(fx, sh)[0] - 0.0016, top_edge(fx, sh)[1]), PAL["tooth"], 0.0011)
    fb = add(lambda sh: (top_edge(fx, sh)[0] + 0.0016, top_edge(fx, sh)[1]), PAL["tooth"], 0.0011)
    fc = add(lambda sh: (top_edge(fx, sh)[0] + 0.0002, top_edge(fx, sh)[1] - 0.0034), PAL["tooth"], 0.0011)
    faces.append((fa, fc, fb))

    ob = make_obj(coll, "Luna_Mouth", pos["Basis"], faces, colors, mats["face_vc"])
    add_keys(ob, {k: v for k, v in pos.items() if k != "Basis"})
    return ob


def strip(S, pts, width, color, lift, verts, colors, faces, taper=True):
    """A flat line on the face through (x, z) points."""
    start = len(verts)
    n = len(pts)
    for i, (x, z) in enumerate(pts):
        t = i / (n - 1)
        w = width * (math.sin(math.pi * t) ** 0.6 if taper else 1)
        x0, z0 = pts[max(0, i - 1)]
        x1, z1 = pts[min(n - 1, i + 1)]
        dx, dz = x1 - x0, z1 - z0
        L = math.hypot(dx, dz) or 1
        nx, nz = -dz / L * w, dx / L * w
        verts.append(S.at(x + nx, z + nz, lift))
        verts.append(S.at(x - nx, z - nz, lift))
        colors += [color, color]
    for i in range(n - 1):
        a = start + 2 * i
        faces.append((a, a + 2, a + 3, a + 1))


def build_details(coll, mats, S):
    verts, colors, faces = [], [], []
    for side in (1, -1):
        # brows: thin, high, mostly under the bangs
        pts = [(ex(side, -0.8 + 1.9 * k / 11), EYE_Z + 0.031 + 0.0035 * math.sin(math.pi * k / 11) - 0.002 * k / 11)
               for k in range(12)]
        strip(S, pts, 0.0011, PAL["brow"], 0.0010, verts, colors, faces)
        # lower lashes: a soft line at the outer half
        pts = [(ex(side, 0.05 + 0.95 * k / 8), eye_bottom(0.05 + 0.95 * k / 8) - 0.0019) for k in range(9)]
        strip(S, pts, 0.0005, PAL["lower_lash"], 0.0011, verts, colors, faces)
        # blush hatching, three short diagonal strokes per cheek
        for k in range(3):
            cx = side * (0.040 + 0.0065 * k)
            pts = [(cx - side * 0.0022, 1.4255 - 0.0018), (cx, 1.4255), (cx + side * 0.0022, 1.4255 + 0.0018)]
            strip(S, pts, 0.00045, PAL["blush_line"], 0.0013, verts, colors, faces)
    # the nose: a small shadow on one side, a dot of shade at the tip
    pts = [(0.0010, 1.4305), (0.0016, 1.4245), (0.0006, 1.4195)]
    strip(S, pts, 0.0007, PAL["skin_shade"], 0.0008, verts, colors, faces)
    ob = make_obj(coll, "Luna_Details", verts, faces, colors, mats["face_vc"])
    for side in (1, -1):
        pass
    return ob


def build_blush(coll, mats, S):
    """Two soft ovals. Each maps the whole of luna_blush.png (a radial fade,
    made on export), so the edge fades out instead of stopping."""
    verts, colors, faces, uvs = [], [], [], []
    rings, n = 4, 32
    for side in (1, -1):
        c = len(verts)
        verts.append(S.at(side * 0.0465, 1.4235, 0.0011))
        colors.append(PAL["blush"])
        uvs.append((0.5, 0.5))
        for r in range(1, rings + 1):
            f = r / rings
            for k in range(n):
                a = 2 * math.pi * k / n
                verts.append(S.at(side * 0.0465 + 0.020 * f * math.cos(a), 1.4235 + 0.0095 * f * math.sin(a), 0.0011))
                colors.append(PAL["blush"][:3] + (PAL["blush"][3] * (1 - f * f) ** 2,))
                uvs.append((0.5 + 0.5 * f * math.cos(a), 0.5 + 0.5 * f * math.sin(a)))
        for k in range(n):
            f_ = (c, c + 1 + k, c + 1 + (k + 1) % n)
            faces.append(f_ if side < 0 else f_[::-1])
        for r in range(rings - 1):
            for k in range(n):
                a_ = c + 1 + r * n + k
                b_ = c + 1 + r * n + (k + 1) % n
                f_ = (a_, b_, b_ + n, a_ + n)
                faces.append(f_[::-1] if side > 0 else f_)
    ob = make_obj(coll, "Luna_Blush", verts, faces, colors, mats["blush"], uvs=uvs)
    ob["luna_tex"] = "blush"
    return ob


# ---------------------------------------------------------------------------
# Hair
# ---------------------------------------------------------------------------
def lerp(a, b, t):
    return tuple(a[i] * (1 - t) + b[i] * t for i in range(4))


def hair_col(t, shine=0.0, tips=True):
    """Down the strand: near-black indigo, violet, then magenta tips."""
    if t < 0.5 or not tips:
        c = lerp(PAL["hair_top"], PAL["hair_mid"], min(1.0, t / 0.5))
    else:
        k = ((t - 0.5) / 0.5) ** 1.3
        c = lerp(PAL["hair_mid"], PAL["hair_tip"], k)
        if t > 0.9:
            c = lerp(c, PAL["hair_tip2"], (t - 0.9) / 0.1)
    return lerp(c, PAL["hair_violet"], shine) if shine else c


def bez(p0, p1, p2, p3, t):
    return p0 * (1 - t) ** 3 + p1 * 3 * (1 - t) ** 2 * t + p2 * 3 * (1 - t) * t * t + p3 * t ** 3


def strand(acc, ctrl, width, thick, segs=14, sides=6, color=None, centre=None, flat_tip=False, chain=None,
           uv=None, curve=0.0):
    """A clump of hair along a Bezier: a flattened tube, pointed at the end.
    chain: which spring-bone chain it hangs from; each vertex is recorded
    in HAIR_WEIGHTS with how far down the strand it is, for skinning."""
    verts, colors, faces = acc[:3]
    ctrl = [Vector(c) for c in ctrl]
    centre = centre or HC
    pts = [bez(*ctrl, s / segs) for s in range(segs + 1)]
    rings = []
    for s, p in enumerate(pts):
        t = s / segs
        tan = (pts[min(s + 1, segs)] - pts[max(s - 1, 0)]).normalized()
        out = (p - centre)
        out = (out - tan * out.dot(tan)).normalized()
        side = tan.cross(out).normalized()
        taper = (1 - t ** 1.7) if not flat_tip else (1 - 0.6 * t ** 3)
        w = width * max(0.0, taper) * (0.85 + 0.15 * math.sin(math.pi * min(1, t * 2)))
        th = thick * max(0.0, taper)
        if curve:      # thin at the root, so it starts under the cap instead of a lip above it
            rootf = min(1.0, 0.25 + 0.75 * t / 0.16)
            th *= rootf
            w *= 0.6 + 0.4 * rootf
        ring = []
        c = color(t)
        for k in range(sides):
            a = 2 * math.pi * k / sides
            # curve > 0 bows the lock outward in the middle, like a real clump of
            # hair seen end-on, so it catches light across its width
            bow = curve * w * (1 - math.cos(a) ** 2) * min(1.0, t / 0.16) if curve else 0.0
            verts.append(p + side * (math.cos(a) * w) + out * (math.sin(a) * th + bow))
            colors.append(c)
            ring.append(len(verts) - 1)
            if len(acc) > 3:
                acc[3].append((chain, t))
            if len(acc) > 4:      # u across the strand (one half of the hair texture), v down it
                u0, vfn = uv or (0.25, lambda t_: t_)
                acc[4].append((u0 + 0.22 * math.cos(a), max(0.0, min(1.0, vfn(t)))))
        rings.append(ring)
    for s in range(segs):
        for k in range(sides):
            faces.append((rings[s][k], rings[s][(k + 1) % sides], rings[s + 1][(k + 1) % sides], rings[s + 1][k]))
    # cap the root
    faces.append(tuple(rings[0][::-1]))
    return pts


def build_hair(coll, mats, S):
    obs = []

    # The cap: a shell over the head, open at the face and down the nape.
    U, V = 64, 34
    verts, colors, faces = [], [], []
    keep = {}
    for j in range(V + 1):
        v = -0.95 + (math.pi / 2 + 0.95) * j / V
        for i in range(U):
            u = 2 * math.pi * i / U
            p = head_point(u, v, grow=0.0085)
            p.z += 0.003
            rel = (p.z - HC.z)
            shine = max(0.0, 1 - abs(rel - 0.055) / 0.012) * 0.55 * max(0.0, -math.cos(u) * 0.3 + 0.7)
            verts.append(p)
            colors.append(hair_col(0.18 - 0.15 * max(0, rel) / 0.1, shine, tips=False))
            front = math.cos(u)
            line = 0.012 * max(0, front) ** 0.7 - 0.055 * (1 - max(0, front)) - 0.03 * max(0, -front)
            keep[j * U + i] = rel > line
    for j in range(V):
        for i in range(U):
            a, b = j * U + i, j * U + (i + 1) % U
            quad = (a, b, b + U, a + U)
            if all(keep[q] for q in quad):
                faces.append(quad)
    obs.append(make_obj(coll, "Luna_HairCap", verts, faces, colors, mats["hair"], subsurf=1))

    # Bangs: blunt hime bangs to the lashes, a couple longer between the eyes.
    acc = ([], [], [])
    xs = [-0.080 + 0.0094 * k for k in range(18)]
    for k, x in enumerate(xs):
        edge = abs(x) / 0.08
        tip_z = EYE_Z + 0.019 - 0.004 * (k % 3 == 1) + 0.012 * edge ** 3
        if abs(x) < 0.012:
            tip_z = EYE_Z + 0.006 - 0.003 * (k % 2)   # the long ones over the nose bridge
        tip = S.at(x * 1.02, tip_z, 0.0065 + 0.004 * edge)
        root = HC + Vector((x * 0.45, -0.035, 0.096))
        c1 = HC + Vector((x * 0.85, -0.068, 0.082))
        c2 = S.at(x * 1.0, tip_z + 0.034, 0.0105 + 0.004 * edge)
        w = 0.0115 + 0.003 * ((k * 7) % 3) / 2
        strand(acc, [root, c1, c2, tip], w, 0.0040, segs=16,
               color=lambda t: hair_col(t * 0.45, shine=max(0.0, 1 - abs(t - 0.28) / 0.09) * 0.6, tips=False))
    obs.append(make_obj(coll, "Luna_HairBangs", acc[0], acc[2], acc[1], mats["hair"], subsurf=1))

    # Side locks framing the face, down past the collarbones, pink at the ends.
    acc = ([], [], [])
    for side in (1, -1):
        for k, (dx, dy, length, w) in enumerate(((0.000, -0.030, 0.30, 0.016), (0.010, -0.010, 0.34, 0.018),
                                                   (0.016, 0.012, 0.31, 0.017))):
            top = HC + Vector((side * (0.074 + dx), dy - 0.02, 0.055))
            mid1 = HC + Vector((side * (0.094 + dx), dy - 0.03, -0.010))
            mid2 = HC + Vector((side * (0.088 + dx * 1.4), dy - 0.035, -0.150))
            tip = HC + Vector((side * (0.098 + dx * 2), dy - 0.040 - 0.01 * k, -length))
            strand(acc, [top, mid1, mid2, tip], w, 0.0035, segs=18, color=lambda t: hair_col(0.15 + 0.85 * t),
                   centre=HC + Vector((0, 0.01, -0.1)))
    obs.append(make_obj(coll, "Luna_HairSides", acc[0], acc[2], acc[1], mats["hair"], subsurf=1))

    # Long back hair: a curtain down to the chest, flaring a little.
    acc = ([], [], [])
    n = 19
    for k in range(n):
        a = -1.45 + 2.9 * k / (n - 1)          # around the back of the head
        r = 0.098
        top = HC + Vector((r * math.sin(a) * 0.98, r * math.cos(a) * 0.95, 0.060))
        length = 0.40 + 0.04 * math.sin(k * 1.9)
        flare = 1.3
        bottom = Vector((top.x * flare, 0.100 + 0.012 * math.cos(a), HC.z - length))
        c1 = top + Vector((top.x * 0.25, 0.05 + 0.02 * math.cos(a), -0.10))
        c2 = bottom + Vector((0, 0.02, 0.16))
        strand(acc, [top, c1, c2, bottom], 0.026, 0.008, segs=20, color=lambda t: hair_col(0.1 + 0.9 * t),
               centre=Vector((0, -0.05, top.z - 0.12)))
    obs.append(make_obj(coll, "Luna_HairBack", acc[0], acc[2], acc[1], mats["hair"], subsurf=1))
    return obs


# ---------------------------------------------------------------------------
# Hair: the bob, with spring-bone chains
# ---------------------------------------------------------------------------
# chain name -> the points its bones run through (root first). Filled in by
# the hair builder from a representative strand, used by build_armature.
CHAINS = {}
CHAIN_T0 = 0.18          # the part of each strand above this stays with the head
CHAIN_BONES = 3


def chain_from(name, pts):
    """Bone points for a chain, from one strand's sampled curve."""
    n = len(pts) - 1
    CHAINS[name] = [pts[min(n, round(n * (CHAIN_T0 + (1 - CHAIN_T0) * k / CHAIN_BONES)))].copy()
                    for k in range(CHAIN_BONES + 1)]


def bob_col(t, shine=0.0):
    """Down the strand: near-black indigo, violet, lilac, then magenta ends."""
    if t < 0.42:
        c = lerp(PAL["hair_top"], PAL["hair_mid"], t / 0.42)
    elif t < 0.66:
        c = lerp(PAL["hair_mid"], PAL["hair_violet"], (t - 0.42) / 0.24)
    else:
        c = lerp(PAL["hair_violet"], PAL["hair_tip"], ((t - 0.66) / 0.34) ** 0.7)
        if t > 0.9:
            c = lerp(c, PAL["hair_tip2"], (t - 0.9) / 0.1)
    return lerp(c, PAL["hair_violet"], shine) if shine else c


def build_hair_bob(coll, mats, S):
    obs = []
    CHAINS.clear()

    # The cap, as before: a shell over the skull, open at the face.
    U, V = 64, 34
    verts, colors, faces, cap_uv = [], [], [], []
    keep = {}
    for j in range(V + 1):
        v = -0.95 + (math.pi / 2 + 0.95) * j / V
        for i in range(U):
            u = 2 * math.pi * i / U
            p = head_point(u, v, grow=0.0085)
            p.z += 0.003
            rel = (p.z - HC.z)
            shine = max(0.0, 1 - abs(rel - 0.055) / 0.012) * 0.55 * max(0.0, -math.cos(u) * 0.3 + 0.7)
            verts.append(p)
            colors.append(bob_col(0.12 - 0.1 * max(0, rel) / 0.1, shine))
            cap_uv.append((0.25 + 0.2 * math.cos(u * 9), max(0.0, 0.12 - 0.1 * max(0, rel) / 0.1)))
            front = math.cos(u)
            line = 0.012 * max(0, front) ** 0.7 - 0.055 * (1 - max(0, front)) - 0.03 * max(0, -front)
            keep[j * U + i] = rel > line
    for j in range(V):
        for i in range(U):
            a, b = j * U + i, j * U + (i + 1) % U
            quad = (a, b, b + U, a + U)
            if all(keep[q] for q in quad):
                faces.append(quad)
    obs.append(make_obj(coll, "Luna_HairCap", verts, faces, colors, mats["hair"], uvs=cap_uv, subsurf=1))

    # The crown: locks fanning out from a whorl at the top of the head, over
    # the cap, into the back and the sides - the top of the head is hair.
    acc = ([], [], [], [], [])
    whorl = HC + Vector((0.0, 0.028, 0.099))      # sunk into the cap: no hole where they meet
    n = 26
    for k in range(n):
        a = 2 * math.pi * k / n                     # 0 = towards the back
        if math.cos(a) < -0.55:                     # the front belongs to the bangs
            continue
        d = Vector((math.sin(a), math.cos(a), 0))
        mid = head_point(math.pi - a, math.asin(0.70), 0.0135)
        end = head_point(math.pi - a, math.asin(0.08), 0.0175)        # down over where the bob comes out
        c1 = whorl + (mid - whorl) * 0.5 + Vector((0, 0, 0.006))
        strand(acc, [whorl, c1, mid, end], 0.030, 0.0045, segs=14, sides=8, curve=0.22,
               chain=None, uv=(0.25, lambda t: 0.04 + 0.2 * t),
               color=lambda t: bob_col(0.04 + 0.2 * t, shine=max(0.0, 1 - abs(t - 0.55) / 0.15) * 0.5),
               centre=HC + Vector((0, 0.01, 0.02)))
    obs.append((make_obj(coll, "Luna_HairCrown", acc[0], acc[2], acc[1], mats["hair"], uvs=acc[4], subsurf=1), acc[3]))

    # Bangs: messy and pointed, longer locks between the eyes and one that
    # falls across her right eye the way it does in most of her pictures.
    acc = ([], [], [], [], [])
    xs = [-0.078 + 0.0098 * k for k in range(17)]
    for k, x in enumerate(xs):
        edge = abs(x) / 0.08
        jag = (0.0, 0.011, 0.004, 0.015, 0.007)[k % 5]       # uneven, pointed ends
        tip_z = EYE_Z + 0.027 - jag + 0.012 * edge ** 3
        tip_x = x * 0.98 + 0.006 * math.sin(k * 2.3) + 0.004 * math.copysign(edge, x)
        if abs(x + 0.006) < 0.011:
            tip_z = EYE_Z - 0.004                       # down between the eyes
        if -0.048 < x < -0.022 and k % 2 == 0:
            tip_z = EYE_Z - 0.006; tip_x = x + 0.006    # across her right eye
        tip = S.at(tip_x, tip_z, 0.0068 + 0.004 * edge)
        root = HC + Vector((x * 0.4 + 0.012, -0.03, 0.097))
        c1 = HC + Vector((x * 0.8, -0.072, 0.080))
        c2 = S.at(x * 1.0, tip_z + 0.036, 0.011 + 0.004 * edge)
        w = 0.0115 + 0.004 * ((k * 7) % 3) / 2
        streak = k in (11, 12)                          # the violet streak, like her pictures
        pts = strand(acc, [root, c1, c2, tip], w, 0.0042, segs=16, sides=8, curve=0.18, chain="bangs",
                     uv=(0.75, lambda t: 0.35 + 0.65 * t) if streak else (0.25, lambda t: t * 0.55),
                     color=(lambda t: lerp(PAL["hair_violet"], PAL["hair_streak"], 0.35 + 0.65 * t)) if streak else
                     (lambda t: bob_col(t * 0.55, shine=max(0.0, 1 - abs(t - 0.28) / 0.09) * 0.55)))
        if k == 8:
            chain_from("bangs", pts)
    # The swept lock: from the part, diagonally across her right eye, half covering it.
    for j, (dx, dz, w) in enumerate(((0.0, 0.0, 0.022), (0.008, 0.012, 0.020), (-0.008, -0.004, 0.019),
                                      (0.014, 0.020, 0.017), (-0.014, -0.010, 0.015))):
        root = HC + Vector((0.024 + dx * 0.5, -0.024, 0.098))
        c1 = HC + Vector((0.014 + dx, -0.080, 0.076))
        c2 = S.at(-0.010 + dx, EYE_Z + 0.030 + dz, 0.0135)
        tip = S.at(-0.034 + dx * 1.4, EYE_Z - 0.008 + dz * 0.6, 0.0100)
        strand(acc, [root, c1, c2, tip], w, 0.0052, segs=18, sides=8, curve=0.2, chain="bangs",
               uv=(0.25, lambda t: t * 0.6),
               color=lambda t: bob_col(t * 0.6, shine=max(0.0, 1 - abs(t - 0.3) / 0.1) * 0.6))
    obs.append((make_obj(coll, "Luna_HairBangs", acc[0], acc[2], acc[1], mats["hair"], uvs=acc[4], subsurf=1), acc[3]))

    # Side locks in front of the ears, to the jaw, the ends curling in.
    acc = ([], [], [], [], [])
    for side in (1, -1):
        name = "side_L" if side > 0 else "side_R"
        # overlapping, flat locks hugging the side of the head (placed from the
        # head's own surface, so nothing flares out like a wing), to the jaw
        for k, (u, end_z, w) in enumerate(((1.02, 1.352, 0.019), (1.18, 1.340, 0.021),
                                            (1.34, 1.344, 0.020), (1.50, 1.348, 0.018))):
            u *= side
            top = head_point(u, math.asin(0.72), 0.005)     # the root starts under the cap
            mid1 = head_point(u, 0.0, 0.0125)
            mid2 = Vector((mid1.x * 0.99, mid1.y - 0.004, end_z + 0.05))
            tip = Vector((mid1.x * 0.86, mid1.y - 0.010, end_z))
            pts = strand(acc, [top, mid1, mid2, tip], w, 0.0034, segs=18, sides=8, curve=0.22, chain=name,
                         uv=(0.25, lambda t: 0.1 + 0.9 * t),
                         color=lambda t: bob_col(0.1 + 0.9 * t), centre=HC + Vector((0, 0.01, -0.06)))
            if k == 1:
                chain_from(name, pts)
    obs.append((make_obj(coll, "Luna_HairSides", acc[0], acc[2], acc[1], mats["hair"], uvs=acc[4], subsurf=1), acc[3]))

    # The bob: full over the back of the skull, ending at the nape and jaw,
    # the ends turned in, a few flicking out. Three chains across the back
    # so it sways in pieces rather than as a helmet.
    acc = ([], [], [], [], [])
    names = ("back_R", "back_C", "back_L")       # her right is -x
    # Two layers: an under layer, shorter and darker, filling the gaps, and
    # the top layer over it. Roots start under the cap so no ridge shows.
    layers = (("under", 19, 0.935, 0.012, 0.026, 0.8), ("top", 23, 1.0, 0.0, 0.029, 1.0))
    for layer, n, scale, lift_end, width, bright in layers:
        for k in range(n):
            a = -1.62 + 3.24 * (k + (0.5 if layer == "under" else 0.0)) / (n - (0 if layer == "under" else 1))
            a = max(-1.62, min(1.62, a))
            side_amt = abs(a) / 1.62
            r1 = (0.130 - 0.014 * side_amt) * scale
            # root: on the skull, inside the cap, high on the back of the head
            top = head_point(math.pi - a * 0.98, math.asin(0.80 - 0.25 * side_amt), 0.004)
            # hug the skull first, then swell out round the back: no shelf
            c1 = head_point(math.pi - a * 0.99, math.asin(0.22), 0.016 * scale)
            end_z = 1.338 + 0.012 * side_amt + 0.006 * math.sin(k * 2.1) + lift_end
            flick = 1.0 if (layer == "top" and k % 3 == 1) else 0.0     # every third end flicks out
            rin = (0.104 - 0.012 * (1 - flick) + 0.022 * flick) * scale
            wave = 0.006 * math.sin(k * 1.7 + (1.0 if layer == "under" else 0.0))
            c2 = Vector(((r1 + wave) * math.sin(a), HC.y + (r1 * 0.97 + wave) * math.cos(a) + 0.006,
                         end_z + 0.045))
            tip = Vector((rin * math.sin(a), HC.y + rin * math.cos(a) * 0.92 + 0.004, end_z))
            # weight between the two nearest chains, by angle
            f = (a + 1.62) / 3.24 * 2                # 0..2 across the three chains
            i0 = min(1, int(f)); blend = f - i0
            ch = {names[i0]: 1 - blend, names[i0 + 1]: blend}
            pts = strand(acc, [top, c1, c2, tip], width, 0.0075, segs=20, sides=8, curve=0.25, chain=ch,
                         uv=(0.25, lambda t: 0.05 + 0.95 * t),
                         color=(lambda t, b=bright: lerp(bob_col(0.05 + 0.95 * t), PAL["hair_top"], 1 - b)),
                         centre=Vector((0, 0.0, top.z - 0.09)))
            if layer == "top" and k in (2, n // 2, n - 3):
                chain_from(names[(0, 1, 2)[[2, n // 2, n - 3].index(k)]], pts)
    obs.append((make_obj(coll, "Luna_HairBack", acc[0], acc[2], acc[1], mats["hair"], uvs=acc[4], subsurf=1), acc[3]))
    for h in obs:
        (h[0] if isinstance(h, tuple) else h)["luna_tex"] = "hair"
    return obs


# ---------------------------------------------------------------------------
# Ears
# ---------------------------------------------------------------------------
def ear_seat(want=Vector((0.063, 0.012, 1.551)), sink=0.009):
    """Where an ear stands: on the hair surface in the direction of `want`,
    sunk a little so the root is buried in the hair, not floating on it."""
    d = (want - HC).normalized()
    r = HR + Vector((0.0085, 0.0085, 0.0085))
    t = 1 / math.sqrt((d.x / r.x) ** 2 + (d.y / (r.y * 1.04)) ** 2 + (d.z / r.z) ** 2)
    surf = HC + d * t
    n = Vector(((surf.x - HC.x) / r.x ** 2, (surf.y - HC.y) / r.y ** 2, (surf.z - HC.z) / r.z ** 2)).normalized()
    return surf - n * sink


EAR_BASE = ear_seat()


def build_ear(coll, mats, side):
    """A cat ear standing on the head, built at the origin then placed.
    Dark outside, pink inside, white fur along the inner edge."""
    verts, colors, faces = [], [], []
    h, w, d = 0.086, 0.035, 0.014
    rings, n = 12, 16
    for r in range(rings + 1):
        t = -0.14 + 1.14 * r / rings           # below 0: the root, buried in the hair
        tt = max(0.0, t)
        width = w * (1 - tt) ** 0.85 * (1 + 0.15 * math.sin(math.pi * tt)) * (1 + 0.25 * max(0.0, -t) / 0.14)
        depth = d * (1 - tt) ** 0.8 * (1 + 0.6 * max(0.0, -t) / 0.14)
        for k in range(n):
            a = 2 * math.pi * k / n
            x = math.cos(a) * width
            y = math.sin(a) * depth
            front = math.sin(a) < -0.2 and abs(math.cos(a)) < 0.82
            if front:
                y *= -0.25        # the inside is hollow
            verts.append(Vector((x, y, h * t)))
            colors.append(PAL["ear_in"] if front and 0.02 < t < 0.85 else PAL["ear_out"])
    for r in range(rings):
        for k in range(n):
            a, b = r * n + k, r * n + (k + 1) % n
            faces.append((a, b, b + n, a + n))
    # fur: little tufts from the inner rim
    acc = (verts, colors, faces)
    for k in range(19):
        fx = -0.026 + 0.0029 * k
        base = Vector((fx, -0.003, 0.002 + 0.004 * (k % 3)))
        tip = Vector((fx * 0.45 + 0.003 * math.sin(k * 1.7), -0.015 - 0.003 * (k % 2),
                      0.030 + 0.011 * ((k * 5) % 3)))
        strand(acc, [base, base + Vector((0, -0.007, 0.009)), tip + Vector((0, 0.001, -0.009)), tip],
               0.0058, 0.0020, segs=6, sides=5, color=lambda t: lerp(PAL["fur"], PAL["ear_in"], t * 0.15),
               centre=Vector((fx, 0.02, 0.0)))
    ob = make_obj(coll, f"Luna_Ear_{'L' if side > 0 else 'R'}", verts, faces, colors, mats["ear"], subsurf=1)
    # stand it on the head: tilted out and a little back
    rot = Matrix.Rotation(side * 0.42, 4, "Y") @ Matrix.Rotation(-0.12, 4, "X") @ Matrix.Rotation(side * 0.25, 4, "Z")
    ob.data.transform(rot)
    ob.location = Vector((side * EAR_BASE.x, EAR_BASE.y, EAR_BASE.z))
    return ob


# ---------------------------------------------------------------------------
# Body
# ---------------------------------------------------------------------------
BODY_PROFILE = [  # z, half-width, half-depth, squareness - slim anime shoulders, a short neck
    (1.405, 0.023, 0.022, 0.0), (1.37, 0.023, 0.022, 0.0), (1.338, 0.024, 0.023, 0.0),
    (1.322, 0.034, 0.029, 0.1), (1.309, 0.062, 0.040, 0.3), (1.293, 0.094, 0.049, 0.42),
    (1.273, 0.114, 0.055, 0.36), (1.248, 0.121, 0.060, 0.38), (1.215, 0.117, 0.066, 0.38),
    (1.175, 0.108, 0.070, 0.4), (1.135, 0.103, 0.069, 0.38), (1.090, 0.104, 0.067, 0.36),
]


def body_ring(z):
    """(half-width, half-depth, squareness) at a height: a Catmull-Rom curve
    through the rows, so the surface is smooth across them (a per-row ease
    leaves flat terraces that show up as stripes in the shading)."""
    P = BODY_PROFILE
    if z >= P[0][0]:
        return P[0][1:]
    if z <= P[-1][0]:
        return P[-1][1:]
    for i in range(len(P) - 1):
        z0, z1 = P[i][0], P[i + 1][0]
        if z1 <= z <= z0:
            t = (z0 - z) / (z0 - z1)
            p0, p1, p2, p3 = P[max(0, i - 1)], P[i], P[i + 1], P[min(len(P) - 1, i + 2)]
            return tuple(0.5 * (2 * p1[c] + (-p0[c] + p2[c]) * t + (2 * p0[c] - 5 * p1[c] + 4 * p2[c] - p3[c]) * t * t
                                + (-p0[c] + 3 * p1[c] - 3 * p2[c] + p3[c]) * t ** 3) for c in (1, 2, 3))
    return P[-1][1:]


def body_point(z, a, grow=0.0):
    """A point on the torso: a=0 is her left side (+x), a=pi/2 the front."""
    hw, hd, sq = body_ring(z)
    c, s_ = math.cos(a), math.sin(a)
    e = 2 / (2 + sq * 4)
    x = (hw + grow) * math.copysign(abs(c) ** e, c)
    y = -(hd + grow) * math.copysign(abs(s_) ** e, s_)
    p = Vector((x, y + 0.006, z))
    if z < 1.31:
        p.y += 0.004 * (1.31 - z) / 0.3
    if y < 0:   # a modest bust
        bump = math.exp(-((z - 1.185) / 0.032) ** 2) * math.exp(-((abs(x) - 0.045) / 0.035) ** 2)
        p.y -= 0.016 * bump
    return p


def neckline(a):
    """Where the camisole's top edge sits at angle a."""
    front = max(0.0, math.sin(a))
    back = max(0.0, -math.sin(a))
    return 1.218 - 0.012 * front ** 6 + 0.022 * back


def build_body(coll, mats):
    n, rows = 112, 72
    z_top, z_bot = 1.405, 1.090
    verts, faces = [], []
    for j in range(rows + 1):
        z = z_top - (z_top - z_bot) * j / rows
        for k in range(n):
            verts.append(body_point(z, 2 * math.pi * k / n))
    for j in range(rows):
        for k in range(n):
            a, b = j * n + k, j * n + (k + 1) % n
            faces.append((a, a + n, b + n, b))
    # arms hanging at her sides, from the shoulder to the bottom of the bust
    for side in (1, -1):
        path = [Vector((side * 0.088, 0.006, 1.262)), Vector((side * 0.122, 0.010, 1.230)),
                Vector((side * 0.134, 0.014, 1.160)), Vector((side * 0.137, 0.017, 1.085))]
        radii = [0.022, 0.025, 0.023, 0.021]
        ring_n, steps = 24, 16
        start = len(verts)
        for i in range(steps + 1):
            t = i / steps
            seg = min(2, int(t * 3)); tt = t * 3 - seg
            p = path[seg].lerp(path[seg + 1], tt)
            r = radii[seg] * (1 - tt) + radii[seg + 1] * tt
            if t < 0.16:   # starts thin inside the torso and swells into the shoulder
                r *= 0.35 + 0.65 * math.sin(math.pi / 2 * t / 0.16)
            tan = (path[min(3, seg + 1)] - path[seg]).normalized()
            ax = Vector((0, 1, 0)).cross(tan).normalized()
            ay = tan.cross(ax).normalized()
            for k in range(ring_n):
                a = 2 * math.pi * k / ring_n
                verts.append(p + ax * math.cos(a) * r + ay * math.sin(a) * r * 0.92)
        for i in range(steps):
            for k in range(ring_n):
                a = start + i * ring_n + k
                b = start + i * ring_n + (k + 1) % ring_n
                f = (a, b, b + ring_n, a + ring_n)
                faces.append(f if side > 0 else f[::-1])
        faces.append(tuple(range(start, start + ring_n))[::-1] if side > 0 else tuple(range(start, start + ring_n)))
    ob = make_obj(coll, "Luna_Body", verts, faces, None, mats["skin"], subsurf=1)
    outward(ob)

    # the camisole: a shell just off the skin, with a clean top edge, and straps
    verts, faces = [], []
    cols, trows = 96, 26
    for k in range(cols):
        a = 2 * math.pi * k / cols
        zt = neckline(a)
        for j in range(trows + 1):
            z = z_bot - 0.004 + (zt - z_bot + 0.004) * j / trows
            verts.append(body_point(z, a, grow=0.0035))
    for k in range(cols):
        for j in range(trows):
            a = k * (trows + 1) + j
            b = ((k + 1) % cols) * (trows + 1) + j
            faces.append((a, b, b + 1, a + 1))
    top = make_obj(coll, "Luna_Top", verts, faces, None, mats["top"], subsurf=1)
    outward(top)

    # straps: their own mesh, no subdivision (it would shrink a thin ribbon to nothing)
    verts, faces = [], []
    bpy.context.view_layer.update()
    bvh = BVHTree.FromObject(ob, bpy.context.evaluated_depsgraph_get())
    for side in (1, -1):
        pts = []
        x = side * 0.066
        c = Vector((x, 0.006, 1.19))
        for i in range(25):
            th = 0.25 + (math.pi - 0.5) * i / 24          # front, over the shoulder, to the back
            d = Vector((0, -math.cos(th), math.sin(th)))
            hit, nrm, _f, _d = bvh.ray_cast(c + d * 0.4, -d)
            if hit is None:
                continue
            front = hit.y < 0.006
            if hit.z < neckline(math.pi / 2 if front else -math.pi / 2) - 0.006:
                continue
            pts.append(hit + d * 0.0042)          # out along the ray: the side we came from
        start = len(verts)
        for pnt in pts:
            for dx in (-0.0035, 0.0035):
                verts.append(pnt + Vector((dx, 0, 0)))
        for i in range(len(pts) - 1):
            a_ = start + 2 * i
            faces.append((a_, a_ + 2, a_ + 3, a_ + 1) if side > 0 else (a_ + 1, a_ + 3, a_ + 2, a_))
    straps = make_obj(coll, "Luna_Straps", verts, faces, None, mats["top"])

    # choker: a band, a ring and a little bell
    verts, faces = [], []
    for z in (1.336, 1.350):
        for k in range(n):
            a = 2 * math.pi * k / n
            verts.append(Vector((0.0285 * math.cos(a), -0.0265 * math.sin(a) + 0.006, z)))
    for k in range(n):
        faces.append((k, (k + 1) % n, n + (k + 1) % n, n + k))
    choker = make_obj(coll, "Luna_Choker", verts, faces, None, mats["choker"], subsurf=1)
    ring = bpy.data.objects.new("Luna_ChokerRing", bpy.data.meshes.new("Luna_ChokerRing"))
    bm = bmesh.new()
    bmesh.ops.create_uvsphere(bm, u_segments=16, v_segments=10, radius=0.0058)
    bmesh.ops.translate(bm, verts=bm.verts, vec=(0, 0, -0.0065))
    ring_v = bmesh.ops.create_cone(bm, cap_ends=True, segments=16, radius1=0.0028, radius2=0.0028, depth=0.0012)
    bmesh.ops.rotate(bm, verts=ring_v["verts"], cent=(0, 0, 0), matrix=Matrix.Rotation(math.pi / 2, 3, "X"))
    bm.to_mesh(ring.data)
    bm.free()
    ring.data.materials.append(mats["metal"])
    ring.location = (0, -0.0235, 1.336)
    coll.objects.link(ring)
    return [ob, top, straps, choker, ring]


# ---------------------------------------------------------------------------
# Armature
# ---------------------------------------------------------------------------
BONES = [  # name (VRM humanoid name where there is one), parent, head, tail
    ("hips", None, (0, 0, 0.92), (0, 0, 1.02)),
    ("spine", "hips", (0, 0, 1.02), (0, 0, 1.12)),
    ("chest", "spine", (0, 0, 1.12), (0, 0, 1.22)),
    ("upperChest", "chest", (0, 0, 1.22), (0, 0, 1.30)),
    ("neck", "upperChest", (0, 0.003, 1.30), (0, 0.003, 1.39)),
    ("head", "neck", (0, 0.003, 1.39), (0, 0.003, 1.58)),
    ("leftEye", "head", (EYE_X, -0.05, EYE_Z), (EYE_X, -0.07, EYE_Z)),
    ("rightEye", "head", (-EYE_X, -0.05, EYE_Z), (-EYE_X, -0.07, EYE_Z)),
    ("Ear_L", "head", (EAR_BASE.x, EAR_BASE.y, EAR_BASE.z), (EAR_BASE.x + 0.025, EAR_BASE.y, EAR_BASE.z + 0.06)),
    ("Ear_R", "head", (-EAR_BASE.x, EAR_BASE.y, EAR_BASE.z), (-EAR_BASE.x - 0.025, EAR_BASE.y, EAR_BASE.z + 0.06)),
    # arms hang at her sides (she's a bust: only the upper arm has a mesh)
    ("leftShoulder", "upperChest", (0.02, 0.004, 1.30), (0.097, 0.006, 1.274)),
    ("leftUpperArm", "leftShoulder", (0.099, 0.006, 1.272), (0.136, 0.016, 1.115)),
    ("leftLowerArm", "leftUpperArm", (0.136, 0.016, 1.115), (0.140, 0.02, 0.92)),
    ("leftHand", "leftLowerArm", (0.140, 0.02, 0.92), (0.142, 0.02, 0.84)),
    ("rightShoulder", "upperChest", (-0.02, 0.004, 1.30), (-0.097, 0.006, 1.274)),
    ("rightUpperArm", "rightShoulder", (-0.099, 0.006, 1.272), (-0.136, 0.016, 1.115)),
    ("rightLowerArm", "rightUpperArm", (-0.136, 0.016, 1.115), (-0.140, 0.02, 0.92)),
    ("rightHand", "rightLowerArm", (-0.140, 0.02, 0.92), (-0.142, 0.02, 0.84)),
    ("leftUpperLeg", "hips", (0.08, 0, 0.90), (0.08, 0, 0.50)),
    ("leftLowerLeg", "leftUpperLeg", (0.08, 0, 0.50), (0.08, 0, 0.10)),
    ("leftFoot", "leftLowerLeg", (0.08, 0, 0.10), (0.08, -0.10, 0.03)),
    ("rightUpperLeg", "hips", (-0.08, 0, 0.90), (-0.08, 0, 0.50)),
    ("rightLowerLeg", "rightUpperLeg", (-0.08, 0, 0.50), (-0.08, 0, 0.10)),
    ("rightFoot", "rightLowerLeg", (-0.08, 0, 0.10), (-0.08, -0.10, 0.03)),
]


def chain_bone(name, i):
    return f"hair_{name}_{i + 1}"


def build_armature(coll):
    arm = bpy.data.armatures.new("Luna_Armature")
    ob = bpy.data.objects.new("Luna_Armature", arm)
    coll.objects.link(ob)
    bpy.context.view_layer.objects.active = ob
    for o in bpy.context.selected_objects:
        o.select_set(False)
    ob.select_set(True)
    bpy.ops.object.mode_set(mode="EDIT")
    for name, parent, head, tail in BONES:
        b = arm.edit_bones.new(name)
        b.head, b.tail = head, tail
        if parent:
            b.parent = arm.edit_bones[parent]
    # hair chains: head -> 1 -> 2 -> 3, through the points the builder chose
    for cname, pts in CHAINS.items():
        parent = arm.edit_bones["head"]
        for i in range(len(pts) - 1):
            b = arm.edit_bones.new(chain_bone(cname, i))
            b.head, b.tail = pts[i], pts[i + 1]
            b.parent = parent
            b.use_connect = i > 0
            parent = b
        # a short end bone: spring chains need a tail joint to swing the last bone
        end = arm.edit_bones.new(f"hair_{cname}_end")
        d = (pts[-1] - pts[-2]).normalized() * 0.012
        end.head, end.tail = pts[-1], pts[-1] + d
        end.parent = parent
        end.use_connect = True
        end.use_deform = False
    bpy.ops.object.mode_set(mode="OBJECT")
    ob.show_in_front = True
    return ob


def skin(ob, arm, weights):
    """Deform ob with the armature: weights(i, co) -> {bone: weight}."""
    groups = {}
    for i, v in enumerate(ob.data.vertices):
        for bone, w in weights(i, v.co).items():
            if w <= 1e-4:
                continue
            if bone not in groups:
                groups[bone] = ob.vertex_groups.new(name=bone)
            groups[bone].add([i], w, "ADD")
    # deform first, then subdivide: take the subdivision off and put it back after
    levels = [(m.levels, m.render_levels) for m in ob.modifiers if m.type == "SUBSURF"]
    for m in [m for m in ob.modifiers if m.type == "SUBSURF"]:
        ob.modifiers.remove(m)
    mod = ob.modifiers.new("Armature", "ARMATURE")
    mod.object = arm
    for lv, rl in levels:
        sub = ob.modifiers.new("Subdivision", "SUBSURF")
        sub.levels, sub.render_levels = lv, rl
    world = ob.matrix_world.copy()
    ob.parent = arm
    ob.matrix_world = world


def only(bone):
    return lambda i, co: {bone: 1.0}


def hair_weights(info):
    def w(i, co):
        chain, t = info[i] if i < len(info) else (None, 0.0)
        if chain is None:
            return {"head": 1.0}
        chains = chain if isinstance(chain, dict) else {chain: 1.0}
        out = {}
        if t < CHAIN_T0 + 0.06:            # the root eases off the head
            h = 1.0 if t <= CHAIN_T0 else 1 - (t - CHAIN_T0) / 0.06
            out["head"] = h
        else:
            h = 0.0
        f = max(0.0, (t - CHAIN_T0) / (1 - CHAIN_T0)) * CHAIN_BONES
        i0 = min(CHAIN_BONES - 1, int(f))
        frac = min(1.0, f - i0) if i0 < CHAIN_BONES - 1 else 0.0
        for name, cw in chains.items():
            if name not in CHAINS:
                continue
            out[chain_bone(name, i0)] = out.get(chain_bone(name, i0), 0) + (1 - h) * cw * (1 - frac)
            if frac:
                out[chain_bone(name, i0 + 1)] = out.get(chain_bone(name, i0 + 1), 0) + (1 - h) * cw * frac
        return out
    return w


def smooth(a, b, x):
    t = max(0.0, min(1.0, (x - a) / (b - a)))
    return t * t * (3 - 2 * t)


def torso_weights(i, co):
    """Neck into head, chest up into the neck, shoulders out to the arms."""
    z, ax = co.z, abs(co.x)
    side = "left" if co.x > 0 else "right"
    hw = body_ring(z)[0]
    if ax > hw + 0.004 and z < 1.285:           # the arm
        top = smooth(1.245, 1.272, z)
        return {f"{side}UpperArm": 1 - top * 0.6, f"{side}Shoulder": top * 0.6}
    out = {}
    head = smooth(1.385, 1.405, z)
    neck = smooth(1.30, 1.335, z) * (1 - head)
    rest = 1 - head - neck
    shoulder = smooth(0.06, 0.105, ax) * smooth(1.21, 1.26, z) * rest * 0.7
    rest -= shoulder
    upper = smooth(1.13, 1.2, z)
    out.update({"head": head, "neck": neck, f"{side}Shoulder": shoulder,
                "upperChest": rest * upper, "chest": rest * (1 - upper)})
    return out


# ---------------------------------------------------------------------------
def main():
    sc, coll = scene()
    mats = {
        "skin": material("Luna_Skin", PAL["skin"]),
        "eye": material("Luna_Eye", image=os.path.join(TEXTURES, "iris.png"), rough=0.4),
        "face_vc": material("Luna_FaceParts", vc=True),
        "blush": material("Luna_Blush", vc=True, blend=True),
        "hair": material("Luna_Hair", vc=True, rough=0.55),
        "ear": material("Luna_Ears", vc=True),
        "body": material("Luna_Body", vc=True),
        "top": material("Luna_Top", PAL["top"], rough=0.6),
        "choker": material("Luna_Choker", PAL["choker"], rough=0.35),
        "metal": material("Luna_Metal", PAL["metal"], rough=0.25),
    }
    face = build_head(coll, mats)
    bpy.context.view_layer.update()
    S = Surface(face)
    head_parts = [face, build_eyes(coll, mats, S), build_lids(coll, mats, S), build_lower_lids(coll, mats, S),
                  build_mouth(coll, mats, S), build_details(coll, mats, S), build_blush(coll, mats, S)]
    hair = build_hair_bob(coll, mats, S) if HAIR_STYLE == "bob" else build_hair(coll, mats, S)
    for h in hair:
        o = h[0] if isinstance(h, tuple) else h
        if o.name != "Luna_HairCap":
            print("pushed out of the head:", o.name, push_out(o, face, 0.004))
    ears = [build_ear(coll, mats, 1), build_ear(coll, mats, -1)]
    body = build_body(coll, mats)
    arm = build_armature(coll)
    bpy.context.view_layer.update()
    for o in head_parts:
        skin(o, arm, only("head"))
    for h in hair:
        if isinstance(h, tuple):
            skin(h[0], arm, hair_weights(h[1]))
        else:
            skin(h, arm, only("head"))
    skin(ears[0], arm, only("Ear_L"))
    skin(ears[1], arm, only("Ear_R"))
    for o in body:
        skin(o, arm, torso_weights if o.name in ("Luna_Body", "Luna_Top", "Luna_Straps") else only("neck"))
    unwrap(coll)
    print("built:", sorted(o.name for o in coll.objects), "chains:", sorted(CHAINS))


def unwrap(coll):
    """UVs on everything that doesn't have its own (the eyes do), laid out
    per part, so textures can be painted for each piece later."""
    for o in coll.objects:
        if o.type != "MESH" or o.data.uv_layers:
            continue
        bpy.ops.object.select_all(action="DESELECT")
        o.select_set(True)
        bpy.context.view_layer.objects.active = o
        bpy.ops.object.mode_set(mode="EDIT")
        bpy.ops.mesh.select_all(action="SELECT")
        bpy.ops.uv.smart_project(angle_limit=math.radians(66), island_margin=0.004)
        bpy.ops.object.mode_set(mode="OBJECT")


main()
