"""Rebuild source frames that the recording duplicated: every stored sub-frame between the two real
neighbours of the bad frame is re-interpolated directly from those neighbours.

usage: python repair.py c3:125 c1:5683        clip:frame of each frame that is a copy of its neighbour

prep.py already repairs the exact duplicates it meets while it builds the store; use this for frames
found afterwards (cadence.py marks them with D). Do NOT use it on a real pause of the aim (cadence.py
--detail tells the two apart)."""
import os, sys, glob
import cv2, numpy as np
import rifeutil

JPG = [cv2.IMWRITE_JPEG_QUALITY, 95, cv2.IMWRITE_JPEG_SAMPLING_FACTOR, cv2.IMWRITE_JPEG_SAMPLING_FACTOR_444]
jobs = [(a.split(":")[0], int(a.split(":")[1])) for a in sys.argv[1:]]
if not jobs:
    sys.exit(__doc__)
rife = rifeutil.load()
tween = rifeutil.Tween(rife)                         # no time steps near 0 or 1 (see rifeutil.Tween)
for clip, j in jobs:
    k0, k1 = (j - 1) * 16, (j + 1) * 16
    f0 = cv2.cvtColor(cv2.imread(f"store/{clip}/{k0:08d}.jpg"), cv2.COLOR_BGR2RGB)
    f1 = cv2.cvtColor(cv2.imread(f"store/{clip}/{k1:08d}.jpg"), cv2.COLOR_BGR2RGB)
    n = 0
    for path in sorted(glob.glob(f"store/{clip}/*.jpg")):
        k = int(os.path.basename(path)[:-4])
        if k0 < k < k1:
            out = tween(f0, f1, (k - k0) / 32.0, tag=(clip, j))
            cv2.imwrite(path, cv2.cvtColor(out, cv2.COLOR_RGB2BGR), JPG)
            n += 1
    # check: the rebuilt frame must now differ from both neighbours
    mid = cv2.imread(f"store/{clip}/{j * 16:08d}.jpg").astype(np.int16)
    a = cv2.imread(f"store/{clip}/{k0:08d}.jpg").astype(np.int16); b = cv2.imread(f"store/{clip}/{k1:08d}.jpg").astype(np.int16)
    print(clip, j, "rewrote", n, "sub-frames; rebuilt frame vs previous %.2f, vs next %.2f" % (np.abs(mid - a).mean(), np.abs(mid - b).mean()))
rifeutil.finish()
