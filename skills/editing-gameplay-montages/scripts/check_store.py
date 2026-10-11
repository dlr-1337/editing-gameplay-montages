"""Does the sub-frame store hold everything the render will ask for (at the current shutter)?
Run after every change of timeline.py and before a render; "missing footage" must be 0."""
import glob, os, re, numpy as np
import cv2
import timeline as T
SH = float(re.search(r"^SHUTTER = ([0-9.]+)", open("render.py", encoding="utf-8").read(), re.M).group(1))
keys = {c: np.array(sorted(int(os.path.basename(f)[:-4]) for f in glob.glob(f"store/{c}/*.jpg"))) for c in sorted({s["clip"] for s in T.SEGS})}
h = SH / T.FPB / 2
bad, nkeys, used = 0, [], set()
for n in range(T.N_FRAMES):
    r = T.frame_beat(n)
    a, b, p, tin = T.active(r)
    tot = 0
    for i in ([a] if b is None else [a, b]):
        s = T.SEGS[i]; mp = s["map"]
        hh = s.get("shutter", SH) / T.FPB / 2
        p0, p1 = float(mp(r - hh)[0]) * 16, float(mp(r + hh)[0]) * 16
        k = keys[s["clip"]]
        i0 = max(0, int(np.searchsorted(k, p0, side="right")) - 1); i1 = min(len(k) - 1, int(np.searchsorted(k, p1, side="left")))
        ks = k[i0:i1 + 1]; tot += len(ks)
        used.update((s["clip"], j) for j in range(int(p0 // 16), int(p1 // 16) + 2))
        if len(ks) == 0 or not (ks[0] <= p0 + 1e-6 and ks[-1] >= p1 - 1e-6 and (len(ks) == 1 or np.diff(ks).max() <= 4)):
            bad += 1
            if bad < 8: print("MISSING frame", n, "beat %.2f" % r, s["clip"], "need %.2f..%.2f" % (p0 / 16, p1 / 16),
                              "have %.2f..%.2f" % (ks[0] / 16, ks[-1] / 16) if len(ks) else "have nothing")
    nkeys.append(tot)
nkeys = np.array(nkeys)
if bad:
    print("-> python ranges.py && python prep.py ranges.json   (builds exactly what is missing)")
print("shutter", SH, "| output frames with missing footage:", bad, "| sub-frames blended per output frame: median %d, 90%% %d, max %d" % (np.median(nkeys), np.percentile(nkeys, 90), nkeys.max()))

# a frame the recording duplicated must have been rebuilt (prep.py does it while building; repair.py afterwards)
def small(c, j):
    f = f"store/{c}/{j * 16:08d}.jpg"
    return cv2.imread(f, cv2.IMREAD_REDUCED_GRAYSCALE_4).astype(np.int16) if os.path.exists(f) else None


dups, prev = [], (None, None, None)
for c, j in sorted(used):
    im = small(c, j)
    if im is not None and prev[2] is not None and prev[:2] == (c, j - 1):
        ch = float(np.abs(im - prev[2]).mean())
        if ch < 0.13:                                 # an unrepaired copy measured 0.07, the stillest real pause 0.20
            dups.append((c, j, round(ch, 3)))
    prev = (c, j, im)
runs = [d for d in dups if not any(e[0] == d[0] and abs(e[1] - d[1]) in (1, 2, 3, 4) for e in dups)]
print("real frames in the store that copy their predecessor (isolated ones are recording duplicates):", runs or "none")
if runs:
    print("-> confirm with  python cadence.py <clip> <frame-8> <frame+8> --detail , then  python repair.py " + " ".join("%s:%d" % d[:2] for d in runs))
