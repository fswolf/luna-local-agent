"""Add a Live2D model to the portrait and make it the one she uses.

    python portrait/add_live2d.py ~/Downloads/1_希格雯.rar --name sigewinne
    python portrait/add_live2d.py ~/Downloads/some-model/          (a folder)

Copies the model into portrait/models/<name>/ with plain ASCII file names
(browsers and URLs are happier), registers its expressions - many
VTube Studio models ship .exp3.json files that the model3.json never
lists - and points config.json's portrait at it. The original is left
alone.

--texture 4096 (the default) shrinks textures bigger than that. A portrait
window doesn't need 8K: one 8192x8192 texture is 256 MB of video memory,
4096 is 64. --texture 0 keeps them as they are.

Archives: .zip always; .rar needs `unrar`, `7z` or `bsdtar` installed
(or extract it yourself and pass the folder).
"""
import argparse
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import zipfile

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)

# Expression files seen in the wild, by what they show -> (file name, role
# for live2d.js: confused / flustered / sad / happy)
KNOWN = {
    "圈圈眼": ("spiral_eyes", "confused"), "蚊香眼": ("spiral_eyes", "confused"),
    "对角眼": ("x_eyes", "flustered"), "><": ("x_eyes", "flustered"), "星星眼": ("star_eyes", "happy"),
    "泪花": ("tears", "sad"), "哭": ("tears", "sad"), "脸红": ("blush", "flustered"),
    "爱心眼": ("heart_eyes", "happy"), "黑脸": ("dark_face", "angry"),
}


def extract(src, dest):
    if os.path.isdir(src):
        return src
    if src.lower().endswith(".zip"):
        with zipfile.ZipFile(src) as z:
            z.extractall(dest)
        return dest
    for cmd in (["unrar", "x", "-o+", src, dest + os.sep], ["7z", "x", f"-o{dest}", "-y", src],
                ["bsdtar", "-xf", src, "-C", dest]):
        if shutil.which(cmd[0]):
            if subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL).returncode == 0:
                return dest
    sys.exit("Couldn't open the archive - install unrar (or p7zip), or extract it and pass the folder.")


def slug(text):
    return re.sub(r"[^a-z0-9]+", "_", text.lower()).strip("_") or "model"


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("source", help="folder, .zip or .rar")
    ap.add_argument("--name", help="short name for it (default: from the file)")
    ap.add_argument("--texture", type=int, default=4096, help="max texture size, 0 = keep")
    ap.add_argument("--no-config", action="store_true", help="copy it, don't switch to it")
    args = ap.parse_args()

    with tempfile.TemporaryDirectory() as tmp:
        root = extract(os.path.expanduser(args.source), tmp)
        found = [os.path.join(d, f) for d, _s, fs in os.walk(root) for f in fs if f.endswith(".model3.json")]
        if len(found) != 1:
            sys.exit(f"Expected one .model3.json, found {len(found)}: {found}")
        model3 = found[0]
        src_dir = os.path.dirname(model3)
        base = os.path.basename(model3)[:-len(".model3.json")]
        name = slug(args.name or base) if (args.name or base.isascii()) else "model"
        out = os.path.join(HERE, "models", name)
        if os.path.exists(out):
            shutil.rmtree(out)
        os.makedirs(os.path.join(out, "textures"))

        with open(model3, encoding="utf-8") as f:
            spec = json.load(f)
        refs = spec["FileReferences"]

        def copy(rel, new_rel):
            shutil.copy2(os.path.join(src_dir, rel), os.path.join(out, new_rel))
            return new_rel

        refs["Moc"] = copy(refs["Moc"], f"{name}.moc3")
        textures = []
        for i, t in enumerate(refs.get("Textures", [])):
            new = copy(t, f"textures/texture_{i:02d}.png")
            textures.append(new)
            if args.texture:
                try:
                    from PIL import Image

                    with Image.open(os.path.join(out, new)) as im:
                        if max(im.size) > args.texture:
                            k = args.texture / max(im.size)
                            im.resize((round(im.size[0] * k), round(im.size[1] * k)), Image.LANCZOS) \
                              .save(os.path.join(out, new), optimize=True)
                            print(f"  {new}: {im.size[0]} -> {round(im.size[0] * k)} px")
                except ImportError:
                    print("  (Pillow isn't installed - textures kept full size)")
        refs["Textures"] = textures
        for key, ext in (("Physics", "physics3.json"), ("DisplayInfo", "cdi3.json"), ("Pose", "pose3.json"),
                         ("UserData", "userdata3.json")):
            if refs.get(key):
                refs[key] = copy(refs[key], f"{name}.{ext}")

        # Expressions: the listed ones, plus any .exp3.json lying next to the model.
        listed = {e["File"]: e.get("Name") for e in refs.get("Expressions", [])}
        for f in os.listdir(src_dir):
            if f.endswith(".exp3.json") and f not in listed:
                listed[f] = f[:-len(".exp3.json")]
        roles, exprs = {}, []
        for i, (rel, label) in enumerate(listed.items()):
            label = label or os.path.basename(rel)[:-len(".exp3.json")]
            ascii_name, role = KNOWN.get(label, (slug(label) if label.isascii() else f"expression_{i}", None))
            new = copy(rel, f"{ascii_name}.exp3.json")
            exprs.append({"Name": ascii_name, "File": new})
            if role and role not in roles:
                roles[role] = ascii_name
        if exprs:
            refs["Expressions"] = exprs

        with open(os.path.join(out, f"{name}.model3.json"), "w", encoding="utf-8") as f:
            json.dump(spec, f, ensure_ascii=False, indent=2)

    rel_model = f"models/{name}/{name}.model3.json"
    print(f"added {rel_model}" + (f" - expressions: {', '.join(e['Name'] for e in exprs)}" if exprs else ""))

    if not args.no_config:
        cfg_path = os.path.join(ROOT, "config.json")
        with open(cfg_path, encoding="utf-8") as f:
            cfg = json.load(f)
        p = cfg.setdefault("portrait", {})
        p["model"] = rel_model
        p.setdefault("live2d", {})["expressions"] = roles
        with open(cfg_path, "w", encoding="utf-8") as f:
            json.dump(cfg, f, ensure_ascii=False, indent=4)
            f.write("\n")
        print(f"config.json: portrait.model = {rel_model}" + (f", roles {roles}" if roles else ""))
        print("Restart Luna (or just reload the portrait window) to see her.")


if __name__ == "__main__":
    main()
