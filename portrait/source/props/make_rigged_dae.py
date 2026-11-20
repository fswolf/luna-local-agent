"""Rigged .dae for Second Life from Blender's export (blanket_sl.json):
vertices in SL avatar space, weights on SL bones (mChest...), UVs.
Joints at SL's default skeleton rest (identity rotation), so the inverse
bind matrices are just the negated rest positions."""
import json, sys, numpy as np
src, out, tex = sys.argv[1], sys.argv[2], sys.argv[3]
D = json.load(open(src))
# the blanket's UVs tile its plaid 3 x 1.4 times; one texture for the whole cloth instead (a 2:1 image)
US, VS = 3.0, 1.4
for t in D["tris"]:
    for c in t: c[1] = [c[1][0] / US, c[1][1] / VS]
# SL rest positions (avatar_skeleton.xml): name -> (parent, local pos)
SK = {"mPelvis": (None, (0, 0, 1.067)), "mTorso": ("mPelvis", (0, 0, 0.084)), "mChest": ("mTorso", (-0.015, 0, 0.205)),
      "mNeck": ("mChest", (-0.010, 0, 0.251)), "mCollarLeft": ("mChest", (-0.021, 0.085, 0.165)),
      "mShoulderLeft": ("mCollarLeft", (0, 0.079, 0)), "mElbowLeft": ("mShoulderLeft", (0, 0.248, 0)),
      "mCollarRight": ("mChest", (-0.021, -0.085, 0.165)), "mShoulderRight": ("mCollarRight", (0, -0.079, 0)),
      "mElbowRight": ("mShoulderRight", (0, -0.248, 0))}
def world(n):
    p, l = SK[n]; return np.array(l) + (world(p) if p else 0)
joints = list(SK)
V = np.array(D["verts"]); N = np.array(D["normals"])
# one vertex per (vertex, uv) pair
key = {}; pos_i, uv, tri_idx = [], [], []
for t in D["tris"]:
    row = []
    for vi, (u, v) in t:
        k = (vi, round(u, 6), round(v, 6))
        if k not in key: key[k] = len(pos_i); pos_i.append(vi); uv.append((u, v))
        row.append(key[k])
    tri_idx.append(row)
pos_i = np.array(pos_i); P = V[pos_i]; NN = N[pos_i]; UV = np.array(uv); T = np.array(tri_idx)
W = [D["weights"][i] for i in pos_i]
f = lambda a: " ".join(f"{x:.6g}" for x in np.asarray(a).ravel())
vcount, vlist, wvals = [], [], [1.0]
for w in W:
    vcount.append(len(w))
    for j, val in w.items():
        vlist += [joints.index(j), len(wvals)]; wvals.append(val)
ibm = []
for j in joints:
    m = np.eye(4); m[:3, 3] = -world(j); ibm += list(m.ravel())
def node(n, ind):
    p, l = SK[n]; m = np.eye(4); m[:3, 3] = l
    kids = "".join(node(c, ind + 1) for c in SK if SK[c][0] == n)
    return f'<node id="{n}" name="{n}" sid="{n}" type="JOINT"><matrix sid="transform">{f(m)}</matrix>{kids}</node>'
idx = np.c_[T.ravel(), T.ravel(), T.ravel()].ravel()
dae = f'''<?xml version="1.0" encoding="utf-8"?>
<COLLADA xmlns="http://www.collada.org/2005/11/COLLADASchema" version="1.4.1">
<asset><unit name="meter" meter="1"/><up_axis>Z_UP</up_axis></asset>
<library_images><image id="tex" name="tex"><init_from>{tex}</init_from></image></library_images>
<library_effects><effect id="fx"><profile_COMMON>
<newparam sid="surf"><surface type="2D"><init_from>tex</init_from></surface></newparam>
<newparam sid="samp"><sampler2D><source>surf</source></sampler2D></newparam>
<technique sid="common"><phong><diffuse><texture texture="samp" texcoord="UVMap"/></diffuse></phong></technique>
</profile_COMMON></effect></library_effects>
<library_materials><material id="mat" name="Blanket"><instance_effect url="#fx"/></material></library_materials>
<library_geometries><geometry id="geo" name="Blanket"><mesh>
<source id="pos"><float_array id="pos-a" count="{P.size}">{f(P)}</float_array><technique_common><accessor source="#pos-a" count="{len(P)}" stride="3"><param name="X" type="float"/><param name="Y" type="float"/><param name="Z" type="float"/></accessor></technique_common></source>
<source id="nrm"><float_array id="nrm-a" count="{NN.size}">{f(NN)}</float_array><technique_common><accessor source="#nrm-a" count="{len(NN)}" stride="3"><param name="X" type="float"/><param name="Y" type="float"/><param name="Z" type="float"/></accessor></technique_common></source>
<source id="uv"><float_array id="uv-a" count="{UV.size}">{f(UV)}</float_array><technique_common><accessor source="#uv-a" count="{len(UV)}" stride="2"><param name="S" type="float"/><param name="T" type="float"/></accessor></technique_common></source>
<vertices id="vtx"><input semantic="POSITION" source="#pos"/></vertices>
<triangles material="Blanket" count="{len(T)}"><input semantic="VERTEX" source="#vtx" offset="0"/><input semantic="NORMAL" source="#nrm" offset="1"/><input semantic="TEXCOORD" source="#uv" offset="2" set="0"/><p>{" ".join(map(str, idx))}</p></triangles>
</mesh></geometry></library_geometries>
<library_controllers><controller id="skin" name="Blanket"><skin source="#geo">
<bind_shape_matrix>{f(np.eye(4))}</bind_shape_matrix>
<source id="jn"><Name_array id="jn-a" count="{len(joints)}">{" ".join(joints)}</Name_array><technique_common><accessor source="#jn-a" count="{len(joints)}" stride="1"><param name="JOINT" type="name"/></accessor></technique_common></source>
<source id="ib"><float_array id="ib-a" count="{len(ibm)}">{f(ibm)}</float_array><technique_common><accessor source="#ib-a" count="{len(joints)}" stride="16"><param name="TRANSFORM" type="float4x4"/></accessor></technique_common></source>
<source id="wt"><float_array id="wt-a" count="{len(wvals)}">{f(wvals)}</float_array><technique_common><accessor source="#wt-a" count="{len(wvals)}" stride="1"><param name="WEIGHT" type="float"/></accessor></technique_common></source>
<joints><input semantic="JOINT" source="#jn"/><input semantic="INV_BIND_MATRIX" source="#ib"/></joints>
<vertex_weights count="{len(P)}"><input semantic="JOINT" source="#jn" offset="0"/><input semantic="WEIGHT" source="#wt" offset="1"/>
<vcount>{" ".join(map(str, vcount))}</vcount><v>{" ".join(map(str, vlist))}</v></vertex_weights>
</skin></controller></library_controllers>
<library_visual_scenes><visual_scene id="scene" name="scene">
{node("mPelvis", 0)}
<node id="Blanket" name="Blanket" type="NODE"><matrix sid="transform">{f(np.eye(4))}</matrix>
<instance_controller url="#skin"><skeleton>#mPelvis</skeleton><bind_material><technique_common><instance_material symbol="Blanket" target="#mat"><bind_vertex_input semantic="UVMap" input_semantic="TEXCOORD" input_set="0"/></instance_material></technique_common></bind_material></instance_controller>
</node></visual_scene></library_visual_scenes>
<scene><instance_visual_scene url="#scene"/></scene>
</COLLADA>'''
open(out, "w").write(dae)
print("verts", len(P), "tris", len(T), "joints", joints)
