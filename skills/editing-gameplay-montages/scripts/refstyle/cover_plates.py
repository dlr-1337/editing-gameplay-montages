"""Background plates for the cover: frames of the edit without lyric words and without any camera move
(no push-in, no kill punch, no shake): the user dislikes enlarged gameplay."""
import os, sys
import cv2
import render, textfx, timeline as T
os.makedirs("cover", exist_ok=True)
textfx.draw = lambda canvas, n, r: None
render.cam = lambda i, u: (T.SEGS[i]["view"][0], T.SEGS[i]["view"][1], T.SEGS[i]["view"][2], 0.0)
PLATES = {}          # set per project: {"name": beat just after a clean kill}, three different scenes, e.g. {"A_tap": 32.05}
if not PLATES:
    sys.exit("cover_plates.py: set PLATES to three beats just after clean kills.")
st = render.Store()
for name, beat in PLATES.items():
    n = int(round((beat - T.R0) * T.FPB))
    cv2.imwrite("cover/plate_%s.png" % name, cv2.cvtColor(render.render_frame(n, st), cv2.COLOR_RGB2BGR))
    print(name, n)
