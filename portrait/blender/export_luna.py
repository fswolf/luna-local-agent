"""Export Luna (the "Luna" collection) to portrait/models/luna.glb.

Run inside Blender after build_luna.py. Then, in the repo:

    python portrait/make_vrm.py        # luna.glb -> luna.vrm

The .glb is plain glTF: meshes, the bone hierarchy, shape keys and
vertex colours. Everything VRM-specific - which bone is the head, which
shape key is a blink, the toon shading - is added by make_vrm.py.
"""
import os

import bpy

REPO = os.environ.get("LUNA_REPO") or os.path.expanduser("~/ai-voice")
OUT = os.path.join(REPO, "portrait", "models", "luna.glb")


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
