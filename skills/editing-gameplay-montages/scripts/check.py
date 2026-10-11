"""Objective checks of a rendered montage, for an editor who cannot watch or hear it.

usage: python check.py video.mp4 [--sheets]

 1. smoothness   frames identical to the previous one; frames where the motion stops for one frame
                 (each mapped back to the clip and source frame it shows); one-frame jumps that no
                 kill, accent, cut or transition explains; judder index
 2. sync_N.jpg   8 frames around every kill: the muzzle flash must be absent on -1 and start on +0
                 (faintly when the beat falls late inside that frame), or on +1 when the beat falls
                 after frame +0's exposure; a printed table says which. A level 3 kill shows its
                 impact frame (an inverted monochrome picture) on +0, which is correct
 3. --sheets     pv_NN.jpg: the whole video, two frames per beat, labelled with the beat
 4. sound        loudness, true peak, and the decoded sample peak (must stay below 0 dBFS)

Reference values:              identical   stalled   judder index   decoded peak
  v4 (delivered, smooth)            0          1*         0.22          -0.7 dBFS
  v3 ("quedas de fps")             1         20          0.34          +3.0 dBFS (clipping)
  * a real pause of the aim in the source, not a fault. Any other stalled frame is a bug to fix."""
import re, subprocess, sys
import numpy as np
import cv2
import timeline as T
from ff import FF

VID = sys.argv[1]
SHEETS = "--sheets" in sys.argv
WIN_Y, WIN_H = 470, 912                 # the gameplay window: FG_Y, FG_H in render.py
Wd, Hd = 270, 228


def frame_of(beat):
    return int(round((beat - T.R0) * T.FPB))


def where(n):
    r = T.frame_beat(n)
    a, b, p, tin = T.active(r)
    s = T.SEGS[a]
    src, v = s["map"](r)
    txt = "beat %6.2f  %s source frame %.1f at %.2fx" % (r, s["clip"], float(src), float(v))
    if b is not None:
        txt += "  (%s transition into %s)" % (tin[0], T.SEGS[b]["clip"])
    return txt


# ---------------------------------------------------------------- 1. smoothness
raw = subprocess.run([FF, "-v", "error", "-i", VID, "-vf", f"crop=1000:{WIN_H - 212}:40:{WIN_Y + 90},scale={Wd}:{Hd}",
                      "-pix_fmt", "gray", "-f", "rawvideo", "-"], capture_output=True).stdout
f = np.frombuffer(raw, np.uint8).reshape(-1, Hd, Wd).astype(np.int16)
d = np.abs(np.diff(f, axis=0)).mean((1, 2))          # d[i] = motion between frame i and frame i+1
print("frames", len(f), "(timeline expects %d)" % T.N_FRAMES)
last = frame_of(T.FADE_OUT[1] - 1.0)
exact = [i + 1 for i in range(len(d)) if d[i] < 0.03 and i + 1 < last]
print("frames identical to the previous one (outside the final fade):", len(exact))
for n in exact:
    print("   frame %4d  %s" % (n, where(n)))
lum = f.mean((1, 2))
stalls, jumps = [], []
for i in range(2, len(d) - 2):
    if lum[i + 1] < 12:                               # fade to or from black: no motion to measure
        continue
    nb = np.median([d[i - 2], d[i - 1], d[i + 1], d[i + 2]])
    if nb > 0.6 and d[i] < 0.12 * nb:
        stalls.append((i + 1, d[i], nb))
    elif nb > 0.8 and d[i] > 2.6 * nb and d[i] > 3.0:
        jumps.append((i + 1, d[i], nb))
print("frames where the motion stops for one frame (stutter unless the source really pauses there):", len(stalls))
for n, v, nb in stalls:
    print("   frame %4d  t=%6.2fs  motion %.2f vs %.2f around it | %s" % (n, n / T.FPS, v, nb, where(n)))
if stalls:
    print("   -> look at the source: python cadence.py <clip> <frame-8> <frame+8> --detail")
# one-frame jumps are normal on a kill (flash, impact frame), on an accent (exposure pop), on a cut and
# inside a transition; what is left is usually a shot that did not kill, a flick or an ability
kills = [frame_of(k) for k, lv, i in T.KILLS]
pulses = [frame_of(k) for k, wt in T.PULSES]
spans = []
for j in range(1, len(T.SEGS)):
    r0, dlen = T.SEGS[j]["r0"], T.SEGS[j]["tin"][1]
    spans.append((frame_of(r0 - dlen / 2) - 2, frame_of(r0 + dlen / 2) + 2))
odd = [(n, v, nb) for n, v, nb in jumps
       if not any(-3 <= n - k <= 12 for k in kills) and not any(-1 <= n - k <= 3 for k in pulses)
       and not any(a <= n <= b for a, b in spans)]
print("one-frame jumps: %d, of which %d are not on a kill, an accent, a cut or a transition (peek.py shows what they are)"
      % (len(jumps), len(odd)))
for n, v, nb in odd:
    print("   frame %4d  t=%6.2fs  motion %.2f vs %.2f around it | %s" % (n, n / T.FPS, v, nb, where(n)))
r = np.abs(np.log((d[1:] + 0.3) / (d[:-1] + 0.3)))
print("judder index per half second (mean |log ratio| of consecutive motions):")
print(" ".join("%.2f" % r[i:i + 30].mean() for i in range(0, len(r) - 30, 30)))
print("overall judder index %.3f" % r[:int(len(r) * 0.95)].mean())

# ---------------------------------------------------------------- 2. kill strips
cap = cv2.VideoCapture(VID)
tiles = []
for k, lv, i in T.KILLS:
    cap.set(cv2.CAP_PROP_POS_FRAMES, frame_of(k) - 3)
    row = []
    for j in range(8):
        ok, fr = cap.read()
        if not ok:
            break
        crop = cv2.resize(fr[WIN_Y:WIN_Y + WIN_H], (240, 203), interpolation=cv2.INTER_AREA)
        cv2.rectangle(crop, (0, 0), (78, 20), (0, 0, 0), -1)
        cv2.putText(crop, f"{k:g} {j - 3:+d}", (4, 15), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 255, 255), 1)
        row.append(crop)
    if len(row) == 8:
        tiles.append(np.hstack(row))
for s in range(0, len(tiles), 7):
    cv2.imwrite(f"sync_{s // 7}.jpg", np.vstack(tiles[s:s + 7]), [cv2.IMWRITE_JPEG_QUALITY, 86])
print("kill strips: sync_0.jpg .. sync_%d.jpg (%d kills, 7 per sheet). Where the flash must first show:" % ((len(tiles) + 6) // 7 - 1, len(tiles)))
sh = float(re.search(r"^SHUTTER = ([0-9.]+)", open("render.py", encoding="utf-8").read(), re.M).group(1))
for k, lv, i in T.KILLS:
    x = (k - T.R0) * T.FPB                            # the beat in output frames; frame +0 is round(x)
    part = min(1.0, max(0.0, (round(x) + sh / 2 - x) / sh))     # share of frame +0's exposure that lies after the shot
    tile = "+1 (the shot comes after frame +0's exposure)" if part <= 0 else \
           "+0" if part >= 0.25 else "+0, faint (only %d %% of its exposure is after the shot), full on +1" % max(1, round(100 * part))
    print("   beat %6g  frame %8.2f  -> %s%s" % (k, x, tile, "   | level 3: +0 is the impact frame" if lv == 3 else ""))

# ---------------------------------------------------------------- 3. overview sheets
if SHEETS:
    beats = np.arange(np.ceil(T.R0 * 2) / 2, T.R1, 0.5)
    thumbs = []
    for b in beats:
        cap.set(cv2.CAP_PROP_POS_FRAMES, min(len(f) - 1, frame_of(b)))
        ok, fr = cap.read()
        if not ok:
            break
        t = cv2.resize(fr, (216, 384), interpolation=cv2.INTER_AREA)
        cv2.rectangle(t, (0, 0), (74, 30), (0, 0, 0), -1)
        cv2.putText(t, "%g" % b, (4, 22), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 255, 255), 2)
        thumbs.append(t)
    per = 14 * 3
    for s in range(0, len(thumbs), per):
        chunk = thumbs[s:s + per]
        sheet = np.zeros((384 * ((len(chunk) + 13) // 14), 216 * 14, 3), np.uint8)
        for q, t in enumerate(chunk):
            sheet[384 * (q // 14):384 * (q // 14 + 1), 216 * (q % 14):216 * (q % 14 + 1)] = t
        cv2.imwrite("pv_%02d.jpg" % (s // per + 1), sheet, [cv2.IMWRITE_JPEG_QUALITY, 85])
    print("overview: pv_01.jpg .. pv_%02d.jpg (two frames per beat)" % ((len(thumbs) + per - 1) // per))

# ---------------------------------------------------------------- 4. sound
def null(af):
    return subprocess.run([FF, "-hide_banner", "-nostats", "-i", VID, "-vn", "-af", af, "-f", "null", "-"],
                          capture_output=True, text=True, encoding="utf-8", errors="replace").stderr


e = null("ebur128=peak=true:framelog=quiet")
e = e[e.rfind("Summary:"):] if "Summary:" in e else ""
lufs, tp = re.search(r"I:\s+(-?[\d.]+) LUFS", e), re.search(r"Peak:\s+(-?[\d.]+) dBFS", e)
pk = re.search(r"Peak level dB:\s+(-?[\d.]+)", null("aformat=sample_fmts=flt,astats=measure_overall=Peak_level:measure_perchannel=none"))
if lufs and pk:
    print("sound: integrated loudness %s LUFS, true peak %s dBFS, decoded sample peak %s dBFS"
          % (lufs.group(1), tp.group(1) if tp else "?", pk.group(1)))
    if float(pk.group(1)) >= 0.0:
        print("   WARNING: the decoded sound exceeds 0 dBFS (clipping). Encode AAC with -aac_pns 0 -aac_tns 0 -aac_is 0 after the limiter.")
else:
    print("sound: no audio stream found")
