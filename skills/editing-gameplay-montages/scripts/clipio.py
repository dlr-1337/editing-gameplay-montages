"""Exact, index-based access to the source clips.

Frame n of a clip is the n-th frame in presentation order; its time is pts[n] (the clips are
60 fps with ~1 ms timestamp jitter). Frames are always fetched by index, never through an fps
filter, so nothing is duplicated or dropped."""
import glob, subprocess
import numpy as np
from ff import FF

SW, SH = 1920, 1080                     # size of the source clips
CROP_X, CROP_W = 288, 1344              # region of the source that the montage can ever show (render.py SRC_W)
_pts = {}


def path(clip):
    """src/<clip>.<any extension>"""
    hits = sorted(glob.glob(f"src/{clip}.*"))
    assert hits, f"no file src/{clip}.*"
    return hits[0]


def pts(clip):
    if clip not in _pts:
        _pts[clip] = np.array(sorted(float(l.split(",")[0]) for l in open(f"pts/{clip}.csv") if l.strip()))
    return _pts[clip]


def n_frames(clip):
    return len(pts(clip))


def t2n(clip, t):
    """Source time (seconds, same clock as the audio) -> fractional frame index.
    Uses the real time table: a recording linked by ingest.py may have dropped frames (gaps of up to 0.6 s),
    so an even grid over the whole clip would be off by that much after the first gap."""
    p = pts(clip)
    return np.interp(t, p, np.arange(len(p)))


def n2t(clip, n):
    p = pts(clip)
    return np.interp(n, np.arange(len(p)), p)


def frame_args(clip, a, b, vf=None):
    """ffmpeg arguments that output exactly frames a..b (inclusive) of the clip."""
    p = pts(clip)
    sel = f"select='between(t\\,{p[a] - 0.004:.4f}\\,{p[b] + 0.004:.4f})'"
    return ["-copyts", "-ss", f"{max(0.0, p[a] - 0.5):.4f}", "-i", path(clip), "-map", "0:v:0",
            "-vf", sel + ("," + vf if vf else ""), "-fps_mode", "passthrough"]


def read_frames(clip, a, b, crop=True):
    """Frames a..b as a uint8 array (N, H, W, 3), RGB, converted with the clip's own colour matrix."""
    w = CROP_W if crop else SW
    vf = (f"crop={CROP_W}:{SH}:{CROP_X}:0," if crop else "") + "scale=in_range=tv:out_range=pc,format=rgb24"
    raw = subprocess.run([FF, "-v", "error"] + frame_args(clip, a, b, vf) + ["-f", "rawvideo", "-"],
                         capture_output=True).stdout
    arr = np.frombuffer(raw, np.uint8).reshape(-1, SH, w, 3)
    assert len(arr) == b - a + 1, (clip, a, b, len(arr))
    return arr
