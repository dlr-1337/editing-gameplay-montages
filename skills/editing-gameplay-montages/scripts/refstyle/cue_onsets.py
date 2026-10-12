"""For each lyric word (time from the speech recogniser, track seconds): the nearest vocal-band onsets
and the nearest 16th-note grid point, in timeline beats. Used to place the on-screen words by hand
(OVERRIDE in lyrics_align.py) where the automatic assignment is doubtful.

usage: python cue_onsets.py [lyrics_whisper.json]      prints the words that fall inside the video (R0..R1)
Needs timeline.py (MUSIC, BPM, BEAT0, M0, R0, R1). It uses the RECOGNISED words, so a line is read by its position
in lyrics_whisper.json, not by the corrected text.
How to read it: "whisper(s)" / "beat" = the recogniser's time for the word; the middle column lists up to three
onsets within +-0.14 s of it, strongest first, as beat(dB rise); the last column is the nearest 16th. A word whose
recognised beat has no onset beside it, or whose strongest onset lies on the neighbouring syllable, is the one to
pin: put the onset beat you trust into OVERRIDE minus 0.04 (see the comment at OVERRIDE in lyrics_align.py), or
leave the word out with DROP. (The onsets here come from a plain band-pass envelope, lyrics_align.py's from the
harmonic part of the spectrogram, so the two lists can differ.)"""
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
