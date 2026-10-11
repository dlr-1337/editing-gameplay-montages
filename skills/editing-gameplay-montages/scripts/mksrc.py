"""Give the source files short names without copying them.

usage: python mksrc.py [clips.json]

clips.json:  {"c1": "C:/path/4k TOPPP.mp4", "c2": "C:/path/other clip.mp4", "music": "C:/path/song.flac"}
          -> src/c1.mp4, src/c2.mp4, src/music.flac
as hard links (same drive, no extra disk space) or copies (other drive). Existing entries are kept.
Keep clips.json: it is the only record of which original file each short name stands for."""
import json, os, shutil, sys

spec = json.load(open(sys.argv[1] if len(sys.argv) > 1 else "clips.json", encoding="utf-8-sig"))    # utf-8-sig: PowerShell writes a BOM
os.makedirs("src", exist_ok=True)
for name, p in spec.items():
    dst = os.path.join("src", name + os.path.splitext(p)[1].lower())
    if os.path.exists(dst):
        print("kept  ", dst)
        continue
    try:
        os.link(p, dst)
        how = "linked"
    except OSError:
        shutil.copy2(p, dst)
        how = "copied"
    print(how, dst, "<-", p)
