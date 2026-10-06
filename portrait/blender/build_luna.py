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


def hexc(h, a=1.0):
    h = h.lstrip("#")
    c = [int(h[i:i + 2], 16) / 255 for i in (0, 2, 4)]
    # vertex colours are linear in Blender; the palette is written in sRGB
    return tuple(((x + 0.055) / 1.055) ** 2.4 if x > 0.04045 else x / 12.92 for x in c) + (a,)


PAL = {
    "skin": hexc("#f7e3e9"), "skin_shade": hexc("#e9c0cd"), "blush": hexc("#ff6f9e", 0.42),
    "blush_line": hexc("#f0819f"),
    "hair_top": hexc("#17112d"), "hair_mid": hexc("#33275f"), "hair_violet": hexc("#5b46a8"),
    "hair_tip": hexc("#d65ec6"), "hair_tip2": hexc("#f08ad6"),
    "ear_out": hexc("#1f1838"), "ear_in": hexc("#f4a9c8"), "fur": hexc("#fbf2f7"),
    "lash": hexc("#120c19"), "lower_lash": hexc("#7a3550"), "brow": hexc("#2a2050"),
    "lip": hexc("#4d1426"), "mouth": hexc("#7c2239"), "tongue": hexc("#e8708f"), "tooth": hexc("#fffafc"),
    "top": hexc("#151019"), "choker": hexc("#100c14"), "metal": hexc("#cfc8dc"),
}

HC = Vector((0.0, 0.0, 1.47))         # head centre
HR = Vector((0.084, 0.089, 0.099))    # half sizes: x, depth (y), height

EYE_X, EYE_Z = 0.0335, 1.452
EYE_W, EYE_H = 0.0205, 0.0245
MOUTH_Z, MOUTH_W = 1.391, 0.0118


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
        p.x *= 1 - 0.36 * t ** 1.3
        p.y *= 1 - 0.18 * t
        p.z *= 1 + 0.10 * t ** 1.5
        p.y -= 0.010 * t ** 2.2 * front ** 2
    if y < 0:   # the face: flatter, cheeks a touch fuller under the eyes
        p.y *= 1 - 0.13 * front * (1 - abs(z) ** 1.5)
        p.x *= 1 + 0.035 * front * max(0.0, 1 - abs(z + 0.25) * 2.2)
    else:       # the back of the skull: rounder
        p.y *= 1.04
    return HC + p


def build_head(coll, mats):
    U, V = 64, 44
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
    ob = make_obj(coll, "Luna_Face", verts, faces, mat=mats["skin"], subsurf=1)
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
    verts, colors, faces = [], [], []
    for side in (1, -1):
        c = len(verts)
        verts.append(S.at(side * 0.0465, 1.4235, 0.0011))
        colors.append(PAL["blush"])
        n = 28
        for k in range(n):
            a = 2 * math.pi * k / n
            verts.append(S.at(side * 0.0465 + 0.0175 * math.cos(a), 1.4235 + 0.0075 * math.sin(a), 0.0011))
            colors.append(PAL["blush"][:3] + (0.0,))
        for k in range(n):
            f = (c, c + 1 + k, c + 1 + (k + 1) % n)
            faces.append(f if side < 0 else f[::-1])
    return make_obj(coll, "Luna_Blush", verts, faces, colors, mats["blush"])


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


def strand(acc, ctrl, width, thick, segs=14, sides=6, color=None, centre=None, flat_tip=False):
    """A clump of hair along a Bezier: a flattened tube, pointed at the end."""
    verts, colors, faces = acc
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
        ring = []
        c = color(t)
        for k in range(sides):
            a = 2 * math.pi * k / sides
            verts.append(p + side * (math.cos(a) * w) + out * (math.sin(a) * th))
            colors.append(c)
            ring.append(len(verts) - 1)
        rings.append(ring)
    for s in range(segs):
        for k in range(sides):
            faces.append((rings[s][k], rings[s][(k + 1) % sides], rings[s + 1][(k + 1) % sides], rings[s + 1][k]))
    # cap the root
    faces.append(tuple(rings[0][::-1]))


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
# Ears
# ---------------------------------------------------------------------------
EAR_BASE = Vector((0.061, 0.006, 1.552))


def build_ear(coll, mats, side):
    """A cat ear standing on the head, built at the origin then placed.
    Dark outside, pink inside, white fur along the inner edge."""
    verts, colors, faces = [], [], []
    h, w, d = 0.074, 0.030, 0.013
    rings, n = 10, 16
    for r in range(rings + 1):
        t = r / rings
        width = w * (1 - t) ** 0.85 * (1 + 0.15 * math.sin(math.pi * t))
        depth = d * (1 - t) ** 0.8
        for k in range(n):
            a = 2 * math.pi * k / n
            x = math.cos(a) * width
            y = math.sin(a) * depth
            front = math.sin(a) < -0.2 and abs(math.cos(a)) < 0.82
            if front:
                y *= -0.25        # the inside is hollow
            verts.append(Vector((x, y, h * t)))
            colors.append(PAL["ear_in"] if front and t < 0.85 else PAL["ear_out"])
    for r in range(rings):
        for k in range(n):
            a, b = r * n + k, r * n + (k + 1) % n
            faces.append((a, b, b + n, a + n))
    # fur: little tufts from the inner rim
    acc = (verts, colors, faces)
    for k in range(9):
        fx = -0.019 + 0.0047 * k
        base = Vector((fx, -0.003, 0.002 + 0.003 * (k % 3)))
        tip = Vector((fx * 0.55 + 0.002 * math.sin(k * 1.7), -0.011 - 0.002 * (k % 2), 0.020 + 0.007 * ((k * 5) % 3)))
        strand(acc, [base, base + Vector((0, -0.005, 0.006)), tip + Vector((0, 0.001, -0.006)), tip],
               0.0042, 0.0016, segs=6, sides=5, color=lambda t: lerp(PAL["fur"], PAL["ear_in"], t * 0.25),
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
def build_body(coll, mats):
    verts, colors, faces = [], [], []
    n = 48
    profile = [  # z, half-width, half-depth, squareness
        (1.405, 0.024, 0.022, 0.0), (1.37, 0.025, 0.023, 0.0), (1.335, 0.027, 0.025, 0.0),
        (1.312, 0.036, 0.031, 0.1), (1.295, 0.068, 0.045, 0.3), (1.275, 0.108, 0.056, 0.45),
        (1.250, 0.140, 0.064, 0.55), (1.222, 0.153, 0.070, 0.55), (1.185, 0.150, 0.077, 0.5),
        (1.14, 0.140, 0.080, 0.45), (1.10, 0.132, 0.078, 0.4),
    ]
    # Catmull-Rom between the profile rings, so colour edges (the
    # neckline, the straps) land on real vertices instead of smearing.
    fine = []
    for i in range(len(profile) - 1):
        p0, p1 = profile[max(0, i - 1)], profile[i]
        p2, p3 = profile[i + 1], profile[min(len(profile) - 1, i + 2)]
        for s_ in range(4):
            t = s_ / 4
            fine.append(tuple(0.5 * ((2 * p1[c]) + (-p0[c] + p2[c]) * t + (2 * p0[c] - 5 * p1[c] + 4 * p2[c] - p3[c]) * t * t
                                     + (-p0[c] + 3 * p1[c] - 3 * p2[c] + p3[c]) * t ** 3) for c in range(4)))
    fine.append(profile[-1])
    profile = fine
    n = 96
    for z, hw, hd, sq in profile:
        for k in range(n):
            a = 2 * math.pi * k / n
            c, s = math.cos(a), math.sin(a)
            e = 2 / (2 + sq * 4)
            x = hw * math.copysign(abs(c) ** e, c)
            y = -hd * math.copysign(abs(s) ** e, s)
            p = Vector((x, y + 0.006, z))
            if z < 1.31:
                p.y += 0.004 * (1.31 - z) / 0.3
            verts.append(p)
            # a black camisole: neckline under the collarbones, thin straps
            strap = abs(abs(x) - 0.085) < 0.006 and z > 1.18 and z < 1.285
            neckline = 1.20 - 0.03 * max(0.0, 1 - abs(x) / 0.10) ** 2 + 0.01 * (y > 0.03)
            colors.append(PAL["top"] if (z < neckline or strap) else PAL["skin"])
    for j in range(len(profile) - 1):
        for k in range(n):
            a, b = j * n + k, j * n + (k + 1) % n
            faces.append((a, a + n, b + n, b))
    ob = make_obj(coll, "Luna_Body", verts, faces, colors, mats["body"], subsurf=1)

    # choker: a band with a small ring at the front
    verts, faces = [], []
    for z in (1.338, 1.351):
        for k in range(n):
            a = 2 * math.pi * k / n
            verts.append(Vector((0.0285 * math.cos(a), -0.0265 * math.sin(a) + 0.006, z)))
    for k in range(n):
        faces.append((k, (k + 1) % n, n + (k + 1) % n, n + k))
    choker = make_obj(coll, "Luna_Choker", verts, faces, None, mats["choker"], subsurf=1)
    ring = bpy.data.objects.new("Luna_ChokerRing", bpy.data.meshes.new("Luna_ChokerRing"))
    bm = bmesh.new()
    bmesh.ops.create_cone(bm, cap_ends=True, segments=16, radius1=0.0042, radius2=0.0042, depth=0.0012)
    bmesh.ops.rotate(bm, verts=bm.verts, cent=(0, 0, 0), matrix=Matrix.Rotation(math.pi / 2, 3, "X"))
    bm.to_mesh(ring.data)
    bm.free()
    ring.data.materials.append(mats["metal"])
    ring.location = (0, -0.0225, 1.334)
    coll.objects.link(ring)
    return [ob, choker, ring]


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
    ("leftShoulder", "upperChest", (0.02, 0, 1.29), (0.10, 0, 1.28)),
    ("leftUpperArm", "leftShoulder", (0.15, 0, 1.27), (0.40, 0, 1.27)),
    ("leftLowerArm", "leftUpperArm", (0.40, 0, 1.27), (0.62, 0, 1.27)),
    ("leftHand", "leftLowerArm", (0.62, 0, 1.27), (0.70, 0, 1.27)),
    ("rightShoulder", "upperChest", (-0.02, 0, 1.29), (-0.10, 0, 1.28)),
    ("rightUpperArm", "rightShoulder", (-0.15, 0, 1.27), (-0.40, 0, 1.27)),
    ("rightLowerArm", "rightUpperArm", (-0.40, 0, 1.27), (-0.62, 0, 1.27)),
    ("rightHand", "rightLowerArm", (-0.62, 0, 1.27), (-0.70, 0, 1.27)),
    ("leftUpperLeg", "hips", (0.08, 0, 0.90), (0.08, 0, 0.50)),
    ("leftLowerLeg", "leftUpperLeg", (0.08, 0, 0.50), (0.08, 0, 0.10)),
    ("leftFoot", "leftLowerLeg", (0.08, 0, 0.10), (0.08, -0.10, 0.03)),
    ("rightUpperLeg", "hips", (-0.08, 0, 0.90), (-0.08, 0, 0.50)),
    ("rightLowerLeg", "rightUpperLeg", (-0.08, 0, 0.50), (-0.08, 0, 0.10)),
    ("rightFoot", "rightLowerLeg", (-0.08, 0, 0.10), (-0.08, -0.10, 0.03)),
]


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
    bpy.ops.object.mode_set(mode="OBJECT")
    return ob


def parent_to_bone(ob, arm, bone):
    world = ob.matrix_world.copy()
    ob.parent = arm
    ob.parent_type = "BONE"
    ob.parent_bone = bone
    bpy.context.view_layer.update()
    ob.matrix_world = world


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
        "choker": material("Luna_Choker", PAL["choker"], rough=0.35),
        "metal": material("Luna_Metal", PAL["metal"], rough=0.25),
    }
    face = build_head(coll, mats)
    bpy.context.view_layer.update()
    S = Surface(face)
    head_parts = [face, build_eyes(coll, mats, S), build_lids(coll, mats, S), build_lower_lids(coll, mats, S),
                  build_mouth(coll, mats, S), build_details(coll, mats, S), build_blush(coll, mats, S)]
    head_parts += build_hair(coll, mats, S)
    ears = [build_ear(coll, mats, 1), build_ear(coll, mats, -1)]
    body = build_body(coll, mats)
    arm = build_armature(coll)
    bpy.context.view_layer.update()
    for o in head_parts:
        parent_to_bone(o, arm, "head")
    parent_to_bone(ears[0], arm, "Ear_L")
    parent_to_bone(ears[1], arm, "Ear_R")
    for o in body:
        parent_to_bone(o, arm, "upperChest" if o.name == "Luna_Body" else "neck")
    print("built:", sorted(o.name for o in coll.objects))


main()
