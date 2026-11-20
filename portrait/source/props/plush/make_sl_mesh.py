"""Mochi for Second Life, v2: one closed surface instead of stacked parts.

The plush is several pieces (fur shell, inner ears, eyes, eye shine, blush,
paw pads) laid over each other. Decimated separately they gap and fight,
which showed in SL as holes in the ears and jagged eye rims. So:
  1. points + normals sampled from every piece -> screened Poisson -> one
     watertight surface, decimated to ~TRIS and smoothed;
  2. xatlas UVs;
  3. each texel (4 samples, for soft edges) takes the colour of the
     original piece nearest to it, decals winning over fur when they're
     within a hair of the surface.
    python3 make_sl2.py plush.glb out.dae out.png [scale] [tris]
"""
import sys, numpy as np, trimesh, xatlas, collada, pymeshlab
from collada import source, geometry, material, scene
from scipy.spatial import cKDTree
from PIL import Image, ImageFilter
src, out_dae, out_png = sys.argv[1:4]
scale = float(sys.argv[4]) if len(sys.argv) > 4 else 2.0
TRIS = int(sys.argv[5]) if len(sys.argv) > 5 else 9000
SIZE = 1024
def srgb(c): return np.where(c <= 0.0031308, 12.92*c, 1.055*np.power(c, 1/2.4) - 0.055)
R = trimesh.transformations.rotation_matrix(np.pi/2, [0,0,1]) @ trimesh.transformations.rotation_matrix(np.pi/2, [1,0,0])
S = trimesh.load(src)
parts = []
for name, g in S.geometry.items():
    g = g.copy(); g.apply_transform(R); g.apply_scale(scale)
    m = g.visual.material; c = getattr(m, "baseColorFactor", None)
    c = np.array(c if c is not None else [255, 255, 255, 255], float); c = c/255.0 if c.max() > 1 else c
    parts.append((m.name, srgb(c[:3]) if m.name != "Shine" else np.ones(3), g))
rank = {"Shine": 4, "Eye": 3, "Blush": 2, "Pink": 1, "Fur": 0}
# 1. one closed surface
pts, nrm = [], []
for _, _, g in parts:
    p, fi = trimesh.sample.sample_surface_even(g, 60000 if g.area > 0.01 else 15000)
    pts.append(p); nrm.append(g.face_normals[fi])
ms = pymeshlab.MeshSet()
ms.add_mesh(pymeshlab.Mesh(vertex_matrix=np.vstack(pts), v_normals_matrix=np.vstack(nrm)))
ms.generate_surface_reconstruction_screened_poisson(depth=9, preclean=True)
m = ms.current_mesh(); body = trimesh.Trimesh(m.vertex_matrix(), m.face_matrix())
body = body.split(only_watertight=False); body = max(body, key=lambda b: b.area)   # drop stray bits
body = body.simplify_quadric_decimation(face_count=TRIS)
trimesh.smoothing.filter_taubin(body, iterations=6)
body.fix_normals()
body.vertices -= (body.bounds[0] + body.bounds[1]) / 2
shift = None
# 2. UVs
vmap, idx, uvs = xatlas.parametrize(body.vertices, body.faces)
verts = body.vertices[vmap]; normals = body.vertex_normals[vmap]
# the parts, in the same place as the body (it was centred)
centre = (np.min([g.bounds[0] for *_, g in parts], 0) + np.max([g.bounds[1] for *_, g in parts], 0)) / 2
trees = []
for name, col, g in parts:
    p, _ = trimesh.sample.sample_surface_even(g, 120000 if name == "Fur" else 40000)
    trees.append((rank[name], col, cKDTree(p - centre)))
# 3. bake
SS = 2                                                  # 2x2 samples per texel
img = np.zeros((SIZE, SIZE, 3), np.float32); hit = np.zeros((SIZE, SIZE), np.float32)
zmin, zmax = verts[:, 2].min(), verts[:, 2].max()
NEAR = 0.0035 * scale                                   # a decal counts when it's this close
allp, allc = [], []
for fi, tri in enumerate(idx):
    p = uvs[tri] * SIZE; p[:, 1] = SIZE - p[:, 1]
    x0, y0 = np.floor(p.min(0) - 1).astype(int); x1, y1 = np.ceil(p.max(0) + 1).astype(int)
    g = (np.arange(SS) + 0.5) / SS
    xs = (np.arange(x0, x1)[:, None] + g[None]).ravel(); ys = (np.arange(y0, y1)[:, None] + g[None]).ravel()
    X, Y = np.meshgrid(xs, ys); q = np.stack([X.ravel(), Y.ravel()], 1)
    a, b, c = p; d = (b[1]-c[1])*(a[0]-c[0]) + (c[0]-b[0])*(a[1]-c[1])
    if abs(d) < 1e-12: continue
    w0 = ((b[1]-c[1])*(q[:,0]-c[0]) + (c[0]-b[0])*(q[:,1]-c[1]))/d
    w1 = ((c[1]-a[1])*(q[:,0]-c[0]) + (a[0]-c[0])*(q[:,1]-c[1]))/d
    W = np.stack([w0, w1, 1-w0-w1], 1); ok = (W >= -1e-4).all(1)
    if not ok.any(): continue
    allp.append(np.c_[q[ok], W[ok] @ verts[tri], W[ok] @ normals[tri]])
A = np.vstack(allp); q, pos, nz = A[:, :2], A[:, 2:5], A[:, 7]
# the nearest piece wins; a decal (higher rank) also wins when it's within a hair of the nearest,
# since decals sit just above the fur. Crisp edges, thin lines stay thin.
D = np.stack([tree.query(pos)[0] for _, _, tree in trees], 1)
ranks = np.array([r for r, _, _ in trees]); cols = np.array([c for _, c, _ in trees])
margin = np.array([0.004 if r == rank['Shine'] else 0.0008 for r in ranks]) * scale   # the shine floats above the eye
close = D <= D.min(1, keepdims=True) + margin[None]
pick = np.where(close, ranks[None], -1).argmax(1)
best_c = cols[pick].astype(float); best_r = ranks[pick]
h = (pos[:, 2] - zmin) / (zmax - zmin)
best_c *= (0.82 + 0.18*h + 0.05*nz)[:, None]
px = np.clip(q.astype(int), 0, SIZE-1)
np.add.at(img, (px[:, 1], px[:, 0]), best_c); np.add.at(hit, (px[:, 1], px[:, 0]), 1)
mask = hit > 0; img[mask] /= hit[mask][:, None]
rng = np.random.default_rng(7)
grain = np.asarray(Image.fromarray((rng.random((SIZE, SIZE))*255).astype(np.uint8)).filter(ImageFilter.GaussianBlur(1.2)), np.float32)/255 - 0.5
img = np.clip(img + grain[..., None]*0.05*mask[..., None], 0, 1)
im = Image.fromarray((img*255).astype(np.uint8)); mk = Image.fromarray((mask*255).astype(np.uint8))
for _ in range(8):
    grown = im.filter(ImageFilter.MaxFilter(3)); gm = mk.filter(ImageFilter.MaxFilter(3))
    im = Image.composite(im, grown, mk); mk = gm
im.save(out_png)
# .dae
dae = collada.Collada()
ci = material.CImage("mochi-img", out_png.split("/")[-1]); dae.images.append(ci)
surf = material.Surface("mochi-surf", ci); samp = material.Sampler2D("mochi-samp", surf)
eff = material.Effect("mochi-fx", [surf, samp], "phong", diffuse=material.Map(samp, "UVMap"))
mat = material.Material("mochi-mat", "Mochi", eff); dae.effects.append(eff); dae.materials.append(mat)
geo = geometry.Geometry(dae, "plush", "Mochi", [source.FloatSource("v", verts.flatten(), ("X","Y","Z")),
      source.FloatSource("n", normals.flatten(), ("X","Y","Z")), source.FloatSource("t", uvs.flatten(), ("S","T"))])
il = source.InputList(); il.addInput(0, "VERTEX", "#v"); il.addInput(1, "NORMAL", "#n"); il.addInput(2, "TEXCOORD", "#t", set="0")
geo.primitives.append(geo.createTriangleSet(np.repeat(idx.flatten(), 3), il, "Mochi")); dae.geometries.append(geo)
node = scene.Node("Mochi", children=[scene.GeometryNode(geo, [scene.MaterialNode("Mochi", mat, inputs=[("UVMap", "TEXCOORD", "0")])])],
                  transforms=[scene.MatrixTransform(np.eye(4).flatten())])
dae.scenes.append(scene.Scene("scene", [node])); dae.scene = dae.scenes[0]
dae.assetInfo.upaxis = collada.asset.UP_AXIS.Z_UP
dae.write(out_dae)
print("tris", len(idx), "watertight", body.is_watertight, "size m", np.round(verts.max(0) - verts.min(0), 3))
