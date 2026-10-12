"""Word-by-word lyric cues placed on measured vocal onsets (the user: "sincronizar ao maximo as letras da tela").

1. The song is split into harmonic and percussive parts (median filtering of the spectrogram), so drum hits
   do not count as syllables. The onset function is the rise of the harmonic part in the vocal band.
2. Each recognised word (lyrics_whisper.json, only the lines confirmed against the published lyrics) is
   assigned to one onset near its recognised time, in order (dynamic programming). A word without a clear
   onset falls back to the nearest 16th note.
3. Words of one or two letters ride with the next word; words less than 0.3 beat apart are shown together.
4. Each cue is tinted: "red" inside the beat ranges of RED (default: the intro, before beat -0.5), otherwise gold,
   silver and white in turn.

usage: python lyrics_align.py        -> lyric_cues.json [[beat_in, beat_out, "WORD", style], ...] and a printed table
Needs timeline.py (MUSIC, BPM, BEAT0, M0) and lyrics_whisper.json (transcribe.py), and LINES filled in below.
How to read the table: one row per word, "recognised" = the beat of the recogniser's time, "chosen" = the beat
of the onset the word was put on (hence the DROP key: that "recognised" beat rounded to 1 decimal), difference in
ms. A word that moved by more than about 100 ms needs a look at cue_onsets.py; OVERRIDE / DROP are explained at
their definitions below."""
import json, subprocess, sys
import numpy as np
from scipy import signal, ndimage
import timeline as T
from ff import FF

SR = 22050
raw = subprocess.run([FF, "-v", "error", "-i", T.MUSIC, "-map", "0:a:0", "-ac", "1", "-ar", str(SR), "-f", "f32le", "-"],
                     capture_output=True).stdout
x = np.frombuffer(raw, np.float32).astype(np.float64)
HOP, NFFT = 110, 1024                                   # 5 ms hop
f, t, Z = signal.stft(x, SR, nperseg=NFFT, noverlap=NFFT - HOP, boundary=None, padded=False)
S = np.abs(Z)
Hm = ndimage.median_filter(S, size=(1, 31))             # smooth along time  -> harmonic (voice, melody)
Pm = ndimage.median_filter(S, size=(31, 1))             # smooth along frequency -> percussive (drums)
Hpart = S * (Hm ** 2 / (Hm ** 2 + Pm ** 2 + 1e-9))
band = (f >= 250) & (f <= 3800)
L = np.log1p(60 * Hpart[band])
flux = np.maximum(L[:, 4:] - L[:, :-4], 0).sum(0)        # rise over 20 ms
flux = np.concatenate([np.zeros(2), flux, np.zeros(2)])
flux /= np.percentile(flux, 99)
pk, pr = signal.find_peaks(flux, height=0.12, distance=int(0.07 * SR / HOP))
pt, ph = t[pk], pr["peak_heights"]


def beat(sec):
    return (sec - T.BEAT0) / T.PER - T.M0


pb = beat(pt)
W = json.load(open("lyrics_whisper.json", encoding="utf-8"))
# confirmed lines, set per song: (t0, corrected words), e.g.
#   LINES = [(14.18, ["PRIMEIRA", "LINHA", "CONFIRMADA"]), (15.88, ["SEGUNDA", "LINHA"])]
# t0 = the "s" time (seconds) of the line's first recognised word in lyrics_whisper.json; the recognised word nearest
# to t0 is the line's first word. The corrected words are mapped ONE TO ONE onto that many consecutive recognised words
# (across segment borders): the timing of word k comes from the k-th recognised word after the first. So the number of
# corrected words must equal the number of recognised words the line spans; if the recogniser split or merged a word,
# the timing of everything after it in the entry comes from the wrong words: end the entry before the mismatch and start
# the next one, with its own t0, after it. A line that runs past the last recognised word stops with an IndexError.
# Only lines confirmed against a published lyrics page (reference-style.md, "Lyric words").
LINES = []
if not LINES:
    sys.exit("lyrics_align.py: LINES is empty. Fill it with this song's confirmed lines first (no lines = no lyric words).")
allw = [w for s in W for w in s["words"]]
ADV = 0.04          # beats (18 ms): the word starts to appear just before the vowel, never after it
# set per song: {("WORD", beat_from, beat_to): beat}. Applies to a corrected word equal to WORD whose RECOGNISED beat
# (the "recognised" column of the table) lies in beat_from..beat_to. `beat` is the beat at which the word's cue starts
# to show; the onset it stands for is ADV (0.04 beat) later, which is what the table prints as "chosen". To put the
# onset on a beat B read from cue_onsets.py, give B - 0.04 (the automatic choice shows its cue ADV before the onset).
OVERRIDE = {}
# set per song: {("WORD", beat)}: the corrected word equal to WORD whose recognised beat, ROUNDED TO ONE DECIMAL
# (round(beat, 1): the table prints two decimals, so check x.x5 values), equals `beat` is not shown. The word still takes
# part in the assignment of the other words; only the cue is left out.
DROP = set()
# set per song: beat ranges (beat_from, beat_to) whose cues are tinted red (as the intro of the delivered edit and its
# breakdown, (27.5, 31.5)); every other cue cycles gold, silver, white. Default: only the intro, before beat -0.5.
RED = [(-1e9, -0.5)]
cues, table = [], []
for t0, words in LINES:
    i0 = min(range(len(allw)), key=lambda i: abs(allw[i]["s"] - t0))
    tw = [beat(allw[i0 + k]["s"]) for k in range(len(words))]
    # candidates per word: (beat, cost)
    cands = []
    for b in tw:
        c = [(float(pb[j]), abs(pb[j] - b) * 4.0 - min(ph[j], 1.0)) for j in range(len(pb)) if abs(pb[j] - b) <= 0.26]
        g = round(b * 4) / 4.0
        c.append((g, abs(g - b) * 4.0 + 0.55))            # fallback: the 16th-note grid
        cands.append(sorted(c))
    # dynamic programming: increasing times, at least 0.10 beat apart
    best = [{j: (c[1], None) for j, c in enumerate(cands[0])}]
    for i in range(1, len(words)):
        cur = {}
        for j, (b, cost) in enumerate(cands[i]):
            opts = [(v[0], pj) for pj, v in best[i - 1].items() if cands[i - 1][pj][0] <= b - 0.10]
            if opts:
                m = min(opts)
                cur[j] = (m[0] + cost, m[1])
        if not cur:                                       # cannot keep the order: fall back to recognised times
            cur = {len(cands[i]) - 1: (min(v[0] for v in best[i - 1].values()) + 5, min(best[i - 1], key=lambda q: best[i - 1][q][0]))}
        best.append(cur)
    j = min(best[-1], key=lambda q: best[-1][q][0])
    sel = [None] * len(words)
    for i in range(len(words) - 1, -1, -1):
        sel[i] = cands[i][j][0]
        j = best[i][j][1]
    for k_, (wd, b) in enumerate(zip(words, tw)):
        for (w_, lo, hi), v in OVERRIDE.items():           # places checked by hand against the plain onset list
            if wd == w_ and lo <= b <= hi:
                sel[k_] = v + ADV
        table.append((wd, b, sel[k_]))
    keep = [q for q in range(len(words)) if (words[q], round(tw[q], 1)) not in DROP]
    words, sel = [words[q] for q in keep], [sel[q] for q in keep]
    # group: 1-2 letter words ride with the next word; words closer than 0.3 beat are shown together
    groups = []
    k = 0
    while k < len(words):
        g = [k]
        while g[-1] + 1 < len(words) and len(" ".join(words[q] for q in g + [g[-1] + 1])) <= 11 and (
                sel[g[-1] + 1] - sel[g[-1]] < 0.30 or (len(words[g[-1]]) <= 2 and sel[g[-1] + 1] - sel[g[-1]] <= 0.45)) and (
                sel[g[-1] + 1] - sel[g[0]] <= 0.45):          # never show a word more than 0.45 beat before it is sung
            g.append(g[-1] + 1)
        groups.append(g)
        k = g[-1] + 1
    for gi, g in enumerate(groups):
        a = sel[g[0]]
        nxt = sel[groups[gi + 1][0]] if gi + 1 < len(groups) else None
        txt = " ".join(words[q] for q in g)
        cues.append([round(a - ADV, 3), None if nxt is not None else round(a + 0.9, 3), txt])
cues.sort(key=lambda c: c[0])
for i, c in enumerate(cues):                              # a word leaves when the next one arrives
    nxt = cues[i + 1][0] if i + 1 < len(cues) else None
    if c[1] is None or (nxt is not None and c[1] > nxt - 0.04):
        c[1] = round(nxt - 0.04, 3)
cyc = ["gold", "silver", "white"]
for i, c in enumerate(cues):                              # red inside the RED beat ranges, metallic tints elsewhere
    c.append("red" if any(lo < c[0] < hi for lo, hi in RED) else cyc[i % 3])
json.dump(cues, open("lyric_cues.json", "w", encoding="utf-8"), ensure_ascii=False)
print("word            recognised  chosen   (difference in ms)")
for wd, b, s_ in table:
    print("%-12s %8.2f %8.2f   %+5.0f" % (wd, b, s_, (s_ - b) * T.PER * 1000))
print()
print("cues:", " | ".join("%.2f-%.2f %s" % tuple(c[:3]) for c in cues))
