"""First look at a track: tempo, a provisional beat phase, where the loud / bass-heavy sections are,
and the kick pattern bar by bar. Use it to choose the BPM and the section of the song.

usage: python music_tempo.py [file]         default: src/music.*

The phase printed here is only provisional: spectral flux fires before the audible attack, so the grid
comes out tens of milliseconds early (38 ms on the first project). ALWAYS refine it with music_grid.py
before placing anything on a beat. Check the tempo candidates too: half or double tempo can win.
The last block lists bass re-entries: the usual place for the first kill ("the drop"). With the drop on
track beat D, M0 = D + 1 makes it timeline beat -1 and the next bar start at beat 0."""
import glob, subprocess, sys
import numpy as np
from ff import FF

SRC = sys.argv[1] if len(sys.argv) > 1 else sorted(glob.glob("src/music.*"))[0]
SR = 22050
raw = subprocess.run([FF, "-v", "error", "-i", SRC, "-map", "0:a:0", "-ac", "1", "-ar", str(SR), "-f", "f32le", "-"],
                     capture_output=True).stdout
x = np.frombuffer(raw, dtype=np.float32)
N, H = 1024, 256
fps = SR / H
nfr = 1 + (len(x) - N) // H
win = np.hanning(N).astype(np.float32)
idx = np.arange(N)[None, :] + H * np.arange(nfr)[:, None]
S = np.abs(np.fft.rfft(x[idx] * win, axis=1))
freqs = np.fft.rfftfreq(N, 1 / SR)
L = np.log1p(50 * S)
flux = np.maximum(L[1:] - L[:-1], 0)
on_all = flux.sum(1)
on_low = flux[:, freqs < 150].sum(1)
rms = np.sqrt((S ** 2).mean(1))
low_rms = np.sqrt((S[:, freqs < 150] ** 2).mean(1))


def norm(v):
    v = v - np.convolve(v, np.ones(43) / 43, mode="same")
    v = np.maximum(v, 0)
    return v / (v.std() + 1e-9)


o = norm(on_all)
# tempo by autocorrelation, 70..180 bpm
ac = np.correlate(o, o, mode="full")[len(o) - 1:]
lags = np.arange(len(ac))
bpm = 60 * fps / np.maximum(lags, 1)
mask = (bpm >= 70) & (bpm <= 180)
cands = sorted(zip(ac[mask], bpm[mask]), reverse=True)[:8]
print("track %.1f s | tempo candidates (bpm, score):" % (len(x) / SR), [(round(float(b), 2), round(float(a))) for a, b in cands])

# refine tempo + phase with a comb over a fine grid
best = None
for b in np.arange(70, 180, 0.02):
    per = 60 * fps / b
    k = np.arange(int(len(o) / per) - 1)
    for ph in np.linspace(0, per, 24, endpoint=False):
        p = np.round(ph + k * per).astype(int)
        p = p[p < len(o)]
        sc = o[p].sum() / np.sqrt(len(p))
        if best is None or sc > best[0]:
            best = (sc, b, ph)
sc, b, ph = best
per = 60 * fps / b
print("best fit: %.2f bpm, first beat at %.3f s (provisional: refine with  python music_grid.py %.2f %.3f)" % (b, ph / fps, b, ph / fps))
beats = (ph + np.arange(int(len(o) / per)) * per) / fps

# loudness / bass per second, to find the strongest section
sec = int(len(rms) / fps)
e = [float(rms[int(i * fps):int((i + 1) * fps)].mean()) for i in range(sec)]
lb = [float(low_rms[int(i * fps):int((i + 1) * fps)].mean()) for i in range(sec)]
em, lm = max(e), max(lb)
print("second: loudness / bass, one digit per second (0-9)")
for i in range(0, sec, 10):
    print("%4d  %s   %s" % (i, "".join(str(min(9, int(10 * v / em))) for v in e[i:i + 10]),
                            "".join(str(min(9, int(10 * v / lm))) for v in lb[i:i + 10])))
# kick strength on every beat, four bars per line: drops and breakdowns show up as dense / empty rows
ol = norm(on_low)
kick = np.array([float(ol[max(0, int(t * fps) - 3):int(t * fps) + 4].max()) for t in beats])
km = np.percentile(kick, 98)
print("beat  time   bass onset on each beat, bars of 4 (0-9)")
for i in range(0, len(kick) - 3, 16):
    print("%4d %6.2fs  %s" % (i, beats[i], " ".join("".join(str(min(9, int(9 * v / km))) for v in kick[j:j + 4])
                                                   for j in range(i, min(i + 16, len(kick) - 3), 4))))
# candidate drops: beats where the bass comes back after at least four beats of little bass
lowb = np.array([float(low_rms[int(beats[i] * fps):int(beats[i + 1] * fps)].mean()) for i in range(len(beats) - 1)])
ref = np.percentile(lowb, 90)
cand = []
for i in range(4, len(lowb) - 8):
    before, after = lowb[i - 4:i].max(), lowb[i:i + 8].mean()
    if before < 0.25 * ref and lowb[i] > 0.6 * ref:
        cand.append((after / (before + 1e-6), i))
print("bass re-entries after a gap (candidate drops): track beat, time, bass over the next 8 beats (0-9)")
for sc, i in sorted(cand, reverse=True)[:8]:
    print("   beat %4d  %6.2fs  %s" % (i, beats[i], "".join(str(min(9, int(9 * v / ref))) for v in lowb[i:i + 8])))
print("(beat numbers stay valid after music_grid.py, which only shifts the grid by a few ms)")
