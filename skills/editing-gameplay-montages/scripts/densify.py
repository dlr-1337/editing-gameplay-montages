"""Add more in-between frames where the picture moves fast, so motion blur is a smooth smear
instead of a few stepped copies. Only source intervals that the edit shows at (near) real time or
faster are considered; the faster the picture moves between two real frames, the denser the grid
(8 or 16 sub-frames instead of 4). Existing files are kept.

usage: python densify.py plan 12 28     (only prints the plan)
       python densify.py run 12 28      (12 / 28 = output pixels of travel per frame that trigger 8x / 16x)"""
import os, sys, glob, json
import numpy as np
import cv2
import timeline as T

JPG = [cv2.IMWRITE_JPEG_QUALITY, 95, cv2.IMWRITE_JPEG_SAMPLING_FACTOR, cv2.IMWRITE_JPEG_SAMPLING_FACTOR_444]
T8, T16 = float(sys.argv[2]), float(sys.argv[3])


def path(clip, key):
    return f"store/{clip}/{key:08d}.jpg"


# 1) which source intervals does the edit show, and how fast
used = {}
h = 0.5 / T.FPB / 2
for n in range(T.N_FRAMES):
    r = T.frame_beat(n)
    a, b, p, tin = T.active(r)
    for i in ([a] if b is None else [a, b]):
        s = T.SEGS[i]
        p0, p1 = float(s["map"](r - h)[0]), float(s["map"](r + h)[0])
        v = float(s["map"](r)[1])
        for j in range(int(np.floor(p0)), int(np.floor(p1)) + 1):
            k = (s["clip"], j)
            used[k] = max(used.get(k, 0.0), v)
cand = sorted(k for k, v in used.items() if v >= 0.75)

# 2) how much the picture changes across each of those intervals
gray = {}


def small(clip, j):
    if (clip, j) not in gray:
        im = cv2.imread(path(clip, j * 16), cv2.IMREAD_GRAYSCALE)
        gray[(clip, j)] = cv2.resize(im, (336, 270), interpolation=cv2.INTER_AREA).astype(np.int16)
    return gray[(clip, j)]


mot = {}
for clip, j in cand:
    if os.path.exists(path(clip, j * 16)) and os.path.exists(path(clip, (j + 1) * 16)):
        a8, b8 = small(clip, j).astype(np.uint8), small(clip, j + 1).astype(np.uint8)
        flow = cv2.calcOpticalFlowFarneback(a8, b8, None, 0.5, 5, 21, 3, 5, 1.1, 0)
        mag = np.hypot(flow[..., 0], flow[..., 1])
        # how far the fast parts of the picture travel between the two frames, in output pixels
        mot[(clip, j)] = float(np.percentile(mag, 90)) * 4 * (1080 / 1280)
vals = np.array(list(mot.values()))
plan = {k: (16 if m >= T16 else 8 if m >= T8 else 4) for k, m in mot.items()}
need = []
for (clip, j), fac in plan.items():
    if fac > 4:
        for s in range(0, 16, 16 // fac):
            if not os.path.exists(path(clip, j * 16 + s)):
                need.append((clip, j, s))
n8, n16 = sum(1 for f in plan.values() if f == 8), sum(1 for f in plan.values() if f == 16)
print(f"intervals shown at >=0.75x: {len(mot)}; travel per frame in output px, percentiles 50/75/90/97: "
      + " / ".join("%.1f" % np.percentile(vals, q) for q in (50, 75, 90, 97)))
print(f"plan: {n8} intervals at 8x, {n16} at 16x -> {len(need)} new sub-frames")
if sys.argv[1] != "run":
    sys.exit()

import rifeutil
rife = rifeutil.load()
tween = rifeutil.Tween(rife)                         # no time steps near 0 or 1 (see rifeutil.Tween)
cur, f0, f1 = None, None, None
for q, (clip, j, s) in enumerate(sorted(need)):
    if cur != (clip, j):
        f0 = cv2.cvtColor(cv2.imread(path(clip, j * 16)), cv2.COLOR_BGR2RGB)
        f1 = cv2.cvtColor(cv2.imread(path(clip, (j + 1) * 16)), cv2.COLOR_BGR2RGB)
        cur = (clip, j)
    out = tween(f0, f1, s / 16.0, tag=(clip, j))
    cv2.imwrite(path(clip, j * 16 + s), cv2.cvtColor(out, cv2.COLOR_RGB2BGR), JPG)
    if q % 500 == 0:
        print(f"{q}/{len(need)}", flush=True)
print("done", len(need))
rifeutil.finish()
