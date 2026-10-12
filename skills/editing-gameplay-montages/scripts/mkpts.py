"""Write pts/<clip>.csv (the presentation time of every video frame) for the clips in src/, and report
what matters for smoothness: real frame rate, timestamp jitter, and gaps (frames the recorder dropped).

usage: python mkpts.py            every video file in src/
       python mkpts.py c1 c2      only these

Everything downstream addresses frames by INDEX through these tables (clipio.py); never by seeking to
a time and resampling with an fps filter."""
import glob, os, subprocess, sys
import numpy as np
from ff import FFPROBE
import clipio

VIDEO = (".mp4", ".mkv", ".mov", ".m4v", ".webm", ".avi")
names = sys.argv[1:] or sorted(os.path.splitext(os.path.basename(f))[0] for f in glob.glob("src/*") if f.lower().endswith(VIDEO))
os.makedirs("pts", exist_ok=True)
for c in names:
    p = clipio.path(c)
    info = subprocess.run([FFPROBE, "-v", "error", "-select_streams", "v:0", "-show_entries",
                           "stream=codec_name,width,height,r_frame_rate", "-of", "csv=p=0", p], capture_output=True, text=True).stdout.strip()
    out = subprocess.run([FFPROBE, "-v", "error", "-select_streams", "v:0", "-show_entries", "packet=pts_time,duration_time,flags",
                          "-of", "csv=p=0", p], capture_output=True, text=True).stdout
    rows = [l.strip() for l in out.splitlines() if l.strip() and l.split(",")[0].replace(".", "", 1).replace("-", "", 1).isdigit()]
    open(f"pts/{c}.csv", "w", newline="\n").write("\n".join(rows) + "\n")
    t = np.array(sorted(float(r.split(",")[0]) for r in rows))
    n = len(t)
    d = np.diff(t) * 1000
    rate = (n - 1) / (t[-1] - t[0])
    med = float(np.median(d))
    dev = (t - (t[0] + np.arange(n) / rate)) * 1000
    gaps = np.where(d > 1.5 * med)[0]
    print(f"{c}: {info} | {n} frames, {t[-1] - t[0]:.2f} s, first pts {t[0]:.4f}, real rate {rate:.4f} fps")
    print("    frame interval ms: min %.1f  median %.1f  max %.1f | drift from an even grid: %+.1f .. %+.1f ms"
          % (d.min(), med, d.max(), dev.min(), dev.max()))
    w = info.split(",")
    if len(w) >= 3 and (int(w[1]), int(w[2])) != (clipio.SW, clipio.SH):
        print(f"    WARNING: {w[1]}x{w[2]}, not the working format {clipio.SW}x{clipio.SH}: src/ was not made by ingest.py; run it")
    if abs(rate - 60) > 0.5:
        print("    WARNING: not 60 fps, not the working format: src/ was not made by ingest.py; run it")
    if len(gaps):
        print("    WARNING: %d gaps (dropped frames in the recording) at frame (time, ms): " % len(gaps)
              + ", ".join("%d (%.2fs, %.0f)" % (i, t[i], d[i]) for i in gaps[:20]))
