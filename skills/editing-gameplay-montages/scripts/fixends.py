"""Rebuild the in-between frames next to every real frame.

Measured on this RIFE build (v4.25, ncnn): for a time step below about 0.08 the network returns the first
frame unchanged (and the second one above 0.92), then catches up by about 0.25. In a 16x grid that makes
the sub-frames 15/16, 0 and 1/16 identical: slow motion stalls for an eighth of a frame at every real frame
and hurries afterwards. Steps between 0.25 and 0.75 are linear.

Fix: the sub-frames 1, 2, 3 sixteenths are interpolated between the real frame and the 4/16 sub-frame at
steps 0.25 / 0.5 / 0.75 (the linear zone), and 13, 14, 15 between the 12/16 sub-frame and the next real frame.
Intervals that only have an 8x grid get 2/16 and 14/16 the same way.

usage: python fixends.py [clip ...]      resumable (fixends_done.json)"""
import glob, json, os, sys
import cv2
import rifeutil

JPG = [cv2.IMWRITE_JPEG_QUALITY, 95, cv2.IMWRITE_JPEG_SAMPLING_FACTOR, cv2.IMWRITE_JPEG_SAMPLING_FACTOR_444]
DONE = "fixends_done.json"
done = set(tuple(x) for x in json.load(open(DONE))) if os.path.exists(DONE) else set()


def p(clip, key):
    return f"store/{clip}/{key:08d}.jpg"


def rd(clip, key):
    return cv2.cvtColor(cv2.imread(p(clip, key)), cv2.COLOR_BGR2RGB)


def wr(clip, key, rgb):
    cv2.imwrite(p(clip, key), cv2.cvtColor(rgb, cv2.COLOR_RGB2BGR), JPG)


clips = sys.argv[1:] or sorted(os.path.basename(d) for d in glob.glob("store/*"))
rife = rifeutil.load()
n = 0
for clip in clips:
    keys = set(int(os.path.basename(f)[:-4]) for f in glob.glob(f"store/{clip}/*.jpg"))
    for j in sorted({k // 16 for k in keys}):
        b = j * 16
        if (clip, j) in done or not {b, b + 4, b + 12, b + 16} <= keys or b + 2 not in keys:
            continue
        A, K4, K12, B = rd(clip, b), rd(clip, b + 4), rd(clip, b + 12), rd(clip, b + 16)
        jobs = [(1, A, K4, 0.25), (2, A, K4, 0.5), (3, A, K4, 0.75), (13, K12, B, 0.25), (14, K12, B, 0.5), (15, K12, B, 0.75)]
        for s, x, y, t in jobs:
            if b + s in keys:
                wr(clip, b + s, rife.process_cv2(x, y, t))
                n += 1
        done.add((clip, j))
        if len(done) % 40 == 0:
            json.dump(sorted(done), open(DONE, "w"))
            print(clip, j, "| rebuilt", n, flush=True)
json.dump(sorted(done), open(DONE, "w"))
print("done: rebuilt", n, "sub-frames")
rifeutil.finish()
