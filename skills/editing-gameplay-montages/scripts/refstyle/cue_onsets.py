"""For each lyric word (time from the speech recogniser, track seconds): the nearest vocal-band onsets
and the nearest 16th-note grid point, in timeline beats. Used to place the on-screen words by hand
(OVERRIDE in lyrics_align.py) where the automatic assignment is doubtful.

usage: python cue_onsets.py [lyrics_whisper.json]      prints the words that fall inside the video (R0..R1)"""
import json, subprocess, sys
import numpy as np
from scipy import signal
from ff import FF
import timeline as T
BPM, BEAT0, M0 = T.BPM, T.BEAT0, T.M0
PER = 60.0 / BPM
SR = 22050
raw = subprocess.run([FF, "-v", "error", "-i", T.MUSIC, "-map", "0:a:0", "-ac", "1", "-ar", str(SR), "-f", "f32le", "-"], capture_output=True).stdout
x = np.frombuffer(raw, np.float32).astype(np.float64)
sos = signal.butter(4, [350, 4000], "band", fs=SR, output="sos")
y = signal.sosfiltfilt(sos, x)
w = int(0.008 * SR)
env = np.sqrt(np.convolve(y * y, np.ones(w) / w, mode="same")) + 1e-5
le = 20 * np.log10(env)
d = int(0.03 * SR)
rise = np.zeros_like(le); rise[d // 2:-(d - d // 2)] = le[d:] - le[:-d]
pk, pr = signal.find_peaks(rise, height=5.0, distance=int(0.06 * SR))
pt = pk / SR
W = json.load(open(sys.argv[1] if len(sys.argv) > 1 else "lyrics_whisper.json", encoding="utf-8"))      # from transcribe.py
beat = lambda t: (t - BEAT0) / PER - M0
t_lo, t_hi = T.beat_time(T.R0), T.beat_time(T.R1)          # the part of the track the video uses
print("word            whisper(s)  beat   | vocal onsets within +-0.14 s (beat, dB rise)        | nearest 16th")
for s in W:
    if s["s"] < t_lo - 1.0 or s["s"] > t_hi:
        continue
    for wd in s["words"]:
        t = wd["s"]
        near = [(pt[i], pr["peak_heights"][i]) for i in range(len(pt)) if abs(pt[i] - t) <= 0.14]
        near.sort(key=lambda q: -q[1])
        g = round(beat(t) * 4) / 4
        print("%-15s %7.2f  %6.2f | %-52s | %6.2f" % (wd["w"].strip()[:15], t, beat(t), "  ".join("%.2f(%.0f)" % (beat(a), b) for a, b in near[:3]), g))
