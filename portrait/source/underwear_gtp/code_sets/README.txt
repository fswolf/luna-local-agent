Luna's underwear sets for human.vrm, drawn in code (no image generator).

  python3 make_set2.py <set>.json <out_dir>     -> <name>-bra.png, <name>-panties.png

cur_bra.png / cur_panties.png are the model's own textures: their outline is the UV shape every
set is cut to. The .json files are the four sets (colours, motif, sizes, emblem spots).
Copy the results to portrait/models/luna/sets/ and list them in human.outfits.json.
Needs numpy, scipy and Pillow.
