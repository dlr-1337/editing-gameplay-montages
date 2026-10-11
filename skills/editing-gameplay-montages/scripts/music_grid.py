"""Measure where the drum hits of a track really start, relative to a provisional beat grid, and print
the corrected first-beat time (BEAT0 for timeline.py) plus any tempo drift.

usage: python music_grid.py BPM BEAT0 [T0 T1] [file]     T0..T1: part of the track to measure (seconds)
       e.g. python music_grid.py 130 0.423 27 72

Method: 3 ms RMS envelope; around every half beat of the grid, the steepest 6 ms rise of the log
envelope; the onset is where the envelope crosses the middle of that rise. Only clear hits count.
Run it a second time with the corrected BEAT0: the median offset must come out within about 2 ms."""
import glob, subprocess, sys
import numpy as np
from ff import FF

args = [a for a in sys.argv[1:]]
files = [a for a in args if not a.replace(".", "", 1).replace("-", "", 1).isdigit()]
nums = [float(a) for a in args if a not in files]
BPM, BEAT0 = nums[0], nums[1]
SRC = files[0] if files else sorted(glob.glob("src/music.*"))[0]
PER = 60.0 / BPM
SR = 44100
raw = subprocess.run([FF, "-v", "error", "-i", SRC, "-map", "0:a:0", "-ac", "1", "-ar", str(SR), "-f", "f32le", "-"],
                     capture_output=True).stdout
m = np.frombuffer(raw, np.float32)
T0, T1 = (nums[2], nums[3]) if len(nums) >= 4 else (0.0, len(m) / SR)
w = int(SR * 0.003)
le = np.log(np.sqrt(np.convolve(m * m, np.ones(w) / w, mode="same")) + 1e-4)
k = int(0.006 * SR)
half = 0.2 * PER                                   # search this far on both sides of the grid position
rows = []
n0, n1 = int(np.ceil((T0 - BEAT0) / PER * 2)), int(np.floor((T1 - BEAT0) / PER * 2))
for h in range(n0, n1 + 1):
    tg = BEAT0 + h * PER / 2
    a, b = int((tg - half) * SR), int((tg + half) * SR)
    if a < 0 or b + k >= len(le):
        continue
    rise = le[a + k:b + k] - le[a:b]               # rise over 6 ms
    i = int(np.argmax(rise))
    seg = le[a + i:a + i + k]
    j = int(np.argmax(seg >= (seg[0] + seg[-1]) / 2))
    rows.append((h / 2, (a + i + j) / SR, ((a + i + j) / SR - tg) * 1000, float(rise[i])))
rows = np.array(rows)
strong = rows[rows[:, 3] >= max(1.0, np.percentile(rows[:, 3], 60))]
on = strong[np.abs(strong[:, 0] - np.round(strong[:, 0])) < 1e-6]          # hits on whole beats
use = on if len(on) >= 12 else strong
off = use[:, 2]
med = float(np.median(off))
core = use[np.abs(off - med) < 15]                                          # drop hits that belong to another subdivision
med = float(np.median(core[:, 2]))
print("%d half-beat positions, %d clear hits, %d on whole beats, %d agree within 15 ms" % (len(rows), len(strong), len(on), len(core)))
print("offset of the real onsets from the grid: median %+.1f ms, spread (std) %.1f ms" % (med, core[:, 2].std()))
span = core[:, 1].max() - core[:, 1].min()
if len(core) >= 30 and span >= 60:
    slope = np.polyfit(core[:, 1], core[:, 2], 1)[0]                        # ms per second
    print("drift: %+.2f ms per minute%s" % (slope * 60, "" if abs(slope * 60) < 4 else
                                            "  -> tempo is really %.3f bpm" % (BPM / (1 + slope / 1000))))
else:
    print("drift: not judged (needs 30 hits over a minute; run without T0 T1 to check the tempo on the whole track)")
print("=> BEAT0 = %.4f   (was %.4f)" % (BEAT0 + med / 1000, BEAT0))
print("strongest hits: track beat, time, offset ms, rise")
for r in sorted(core, key=lambda q: -q[3])[:24]:
    print("   beat %7.1f  %7.3fs  %+6.1f  %.2f" % tuple(r))
