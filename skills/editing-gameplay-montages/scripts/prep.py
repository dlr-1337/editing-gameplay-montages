"""Build the sub-frame store used by the renderer.

For every requested source range: read the real frames by exact index, rebuild frames the recording
duplicated, and interpolate between consecutive frames with RIFE. A sub-frame is stored as
store/<clip>/<key>.jpg with key = frame_index * 16 + sixteenths, so a 4x grid uses sixteenths
0, 4, 8, 12 and a dense 16x grid uses all of them. Existing files are kept (resumable).

usage: python prep.py ranges.json        ranges.json = [[clip, t0_seconds, t1_seconds, 4 or 16], ...]"""
import os, sys, time, json
import numpy as np
import cv2
import clipio
import rifeutil

JPG = [cv2.IMWRITE_JPEG_QUALITY, 95, cv2.IMWRITE_JPEG_SAMPLING_FACTOR, cv2.IMWRITE_JPEG_SAMPLING_FACTOR_444]
CHUNK = 96
DUP = 0.20          # change (see motion) below which a frame is a copy of its predecessor: the two recording
                    # duplicates of the first project measured 0.10 and 0.14, the stillest real pause of the aim 0.32


def path(clip, key):
    return f"store/{clip}/{key:08d}.jpg"


def save(clip, key, rgb):
    cv2.imwrite(path(clip, key), cv2.cvtColor(rgb, cv2.COLOR_RGB2BGR), JPG)


def motion(a, b):
    return float(np.abs(a[::6, ::6].astype(np.int16) - b[::6, ::6]).mean())


def run(clip, t0, t1, factor, rife, log):
    tween = rifeutil.Tween(rife)                     # never ask RIFE for a time step near 0 or 1 (see rifeutil.Tween)
    os.makedirs(f"store/{clip}", exist_ok=True)
    step = 16 // factor
    a = max(0, int(np.floor(clipio.t2n(clip, t0))))
    b = min(clipio.n_frames(clip) - 1, int(np.ceil(clipio.t2n(clip, t1))))
    done = made = fixed = 0
    n = a
    while n < b:
        m = min(b, n + CHUNK)
        need = [k for j in range(n, m) for k in range(j * 16, j * 16 + 16, step) if not os.path.exists(path(clip, k))]
        if not os.path.exists(path(clip, m * 16)):
            need.append(m * 16)
        if not need:
            done += (m - n) * factor
            n = m
            continue
        fr = clipio.read_frames(clip, max(0, n - 1), min(clipio.n_frames(clip) - 1, m + 4))
        off = max(0, n - 1)
        mo = [motion(fr[i], fr[i + 1]) for i in range(len(fr) - 1)]
        med = float(np.median(mo))
        # a frame (or a run of up to 3) that repeats its predecessor while the scene is moving is a recording
        # hiccup: interpolate straight across it, from the real frames on both sides
        prv = list(range(len(fr)))                   # for every frame: the real frame at or before it ...
        nxt = list(range(1, len(fr) + 1))            # ... and the next real frame after it
        i = 1
        while i < len(fr):
            if mo[i - 1] < DUP and med > 0.6:
                j = i
                while j < len(fr) - 1 and mo[j] < DUP:
                    j += 1                            # fr[i..j] repeat fr[i-1]; fr[j+1] is the next real frame
                if j + 1 < len(fr) and j - i + 1 <= 3:
                    for q in range(i - 1, j + 1):
                        prv[q], nxt[q] = i - 1, j + 1
                    if (clip, off + i, j - i + 1) not in log:
                        log.append((clip, off + i, j - i + 1))
                        fixed += j - i + 1
                i = j + 1
            else:
                i += 1

        def sub(q, s):                                # the picture s/16 of a frame after frame q of this chunk
            t = (q - prv[q] + s / 16) / (nxt[q] - prv[q])
            return fr[prv[q]] if t == 0 else tween(fr[prv[q]], fr[nxt[q]], t, tag=(clip, off + prv[q], off + nxt[q]))

        for j in range(n, m):
            for s in range(0, 16, step):
                k = j * 16 + s
                if os.path.exists(path(clip, k)):
                    continue
                save(clip, k, sub(j - off, s))
                made += 1
        if not os.path.exists(path(clip, m * 16)):
            save(clip, m * 16, sub(m - off, 0))
        n = m
    return a, b, made, fixed


if __name__ == "__main__":
    spec = json.load(open(sys.argv[1], encoding="utf-8-sig"))          # [[clip, t0, t1, factor], ...]
    rife = rifeutil.load()
    log, t_start = [], time.time()
    for clip, t0, t1, factor in spec:
        ts = time.time()
        a, b, made, fixed = run(clip, t0, t1, factor, rife, log)
        print(f"{clip} {t0:.2f}-{t1:.2f}s  frames {a}-{b}  x{factor}: wrote {made} sub-frames, repaired {fixed} duplicates, "
              f"{time.time() - ts:.0f}s", flush=True)
    print("frames the recording duplicated, rebuilt from their neighbours (clip, frame, how many):", log)
    if log:
        print("   check each with:  python cadence.py <clip> <frame-8> <frame+8> --detail")
    print(f"total {time.time() - t_start:.0f}s", flush=True)
    rifeutil.finish()
