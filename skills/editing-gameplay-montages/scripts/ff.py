"""Locate ffmpeg / ffprobe: $FF if set, else PATH, else the winget install on Windows.
`python ff.py` prints the path (run.sh uses it)."""
import glob, os, shutil


def _find():
    p = os.environ.get("FF")
    if p and os.path.exists(p):
        return p
    p = shutil.which("ffmpeg")
    if p:
        return p
    hits = glob.glob(os.path.join(os.environ.get("LOCALAPPDATA", ""), "Microsoft", "WinGet", "Packages",
                                  "Gyan.FFmpeg*", "*", "bin", "ffmpeg.exe"))
    if hits:
        return sorted(hits)[-1]
    raise SystemExit("ffmpeg not found: set FF to its full path, or install it (winget install Gyan.FFmpeg)")


FF = _find()
FFPROBE = os.path.join(os.path.dirname(FF), "ffprobe" + os.path.splitext(FF)[1])

if __name__ == "__main__":
    print(FF)
