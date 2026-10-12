"""Bring the source files into the working format and give them short names in src/.

Working format (what clipio.py, mkpts.py, prep.py and everything downstream assume): every video in src/ is
1920x1080, 60 fps constant frame rate, frame n at t0 + n/60 on the original clock, tv-range bt709 yuv420p.

usage: python ingest.py [clips.json] [--only c1,c2] [--exact | --fast] [--aspect stretch|crop|pad] [--force] [--convert]

clips.json:  {"c1": "C:/path/4k TOPPP.mp4", "c2": "C:/path/cs2 stretched.mp4", "music": "C:/path/song.flac"}
Keep clips.json: it is the only record of which original file each short name stands for.

What happens to each entry (one table line each: original size @ measured frame rate -> action, time taken):
  * a 1920x1080 video whose frames come every 1/60 s (median frame interval, within 0.5 fps; --convert converts it
    anyway), and every non-video file: hard link
    (same drive, no extra disk space) or copy (other drive): src/c1.mp4, src/music.flac. Nothing is decoded.
    A 60 fps recording with dropped frames (average rate a little under 60) is linked too: its frame indices stay the
    original's, which the Valorant raw-recording tools (refstyle/detect_kills.py, mykills.py) rely on; mkpts.py lists
    its gaps. Converting it would cost minutes and shift every frame index after the first gap.
  * any other video (other size, 4:3, 21:9, 120 / 144 / 165 / 240 fps, 30 fps, variable frame rate): a converted
    working copy src/c1.mkv: x264 (fast, crf 9) yuv420p tv-range bt709 (render.py's colour tags) + the clip's audio
    as FLAC, 24 bit.

Geometry. An aspect narrower than 16:9 (4:3, 5:4, 16:10: CS2 "stretched") is STRETCHED to 16:9, which is what the
player saw; a wider one (21:9, 32:9) is cropped at the centre; --aspect crop|pad|stretch overrides (pad = letter /
pillarbox, black bars). Scaling is lanczos. Colour is decoded exactly as clipio.py does it
(scale=in_range=tv:out_range=pc,format=rgb24), so a conforming source that is forced through the conversion
comes back with the same pixels up to the x264 rounding.

Time. Output frame n is the picture the source had at t = t0 + n/60, t0 = the first video pts; the source pts
(packet pts, as in mkpts.py) are used, so variable frame rate and any source rate are handled. A source frame
within 1.5 ms of t is used UNCHANGED (120 / 240 fps and any 60 fps source with its ~1 ms timestamp jitter: exact picks,
no interpolation). Otherwise:
  --exact  (default for clips up to 90 s) the two frames around t are interpolated at the exact fraction
           with RIFE (rifeutil.Tween, on the GPU).
  --fast   (default for longer clips) the nearest source frame, at most half a source frame (3.5 ms at 144 fps)
           off in time; where taking the nearest would repeat a frame of the source (a rate just under 60 fps) that
           one frame is interpolated instead. The manifest marks the clip "fast"; upgrade it later with
           `python ingest.py --exact --only c1` (same frame grid, so kill frames and timeline anchors stay valid).
  A source below 59.5 fps is always interpolated exactly, whatever the clip length: repeated frames are the stutter.
  Frames are NEVER passed through an ffmpeg fps filter. A hole of more than 0.25 s in the source timestamps (a
  recorder pause), or two frames with one timestamp, is not interpolated: the nearest frame is held there and the line says so.

Audio. The first audio stream, FLAC, shifted so that a sound at original time T plays at T - t0 in the working copy
(silence is added when the audio starts after the video, the head is cut when it starts before), i.e. the file
reads like a clip of the original: video frame n and audio sample n/60*rate belong together.

Output. src/ingest.json records per entry: original path, width, height, measured fps, method (linked | copied |
exact | fast), aspect policy, t0 (first video pts of the original), and for conversions the frame counts
(picked / nearest / interpolated / held, rife calls, largest time error of a non-interpolated frame).
Existing entries are kept. --force re-ingests the selected entries; --exact re-ingests the entries that were made
with --fast. A re-ingested entry has the same frame grid but other pictures: delete store/<clip>, re-run prep.py and
mkpts.py (the script says so). A script run that loaded RIFE ends through rifeutil.finish() (exit code 0)."""
import argparse, glob, json, os, queue, shutil, subprocess, sys, threading, time
import numpy as np
from ff import FF, FFPROBE

SW, SH, FPS = 1920, 1080, 60
VIDEO = (".mp4", ".mkv", ".mov", ".m4v", ".webm", ".avi", ".ts", ".flv", ".wmv")
TOL = 0.0015                # s: a source frame this close to the wanted time is used unchanged
MAXGAP = 0.25               # s: a bigger hole between two source timestamps is not interpolated
EXACT_MAX_S = 90            # clips up to this length default to --exact
CONFORM_FPS = 0.5           # |rate - 60| below this and 1920x1080: link, do not convert
MIN_FPS_FAST = 59.5         # below this --fast is not allowed (it would repeat frames)
RIFE_CALLS = 0


def probe(p):
    """-> (video stream dict or None, audio stream dict or None)"""
    out = subprocess.run([FFPROBE, "-v", "error", "-show_streams", "-of", "json", p], capture_output=True, text=True)
    st = json.loads(out.stdout or "{}").get("streams", [])
    v = next((s for s in st if s.get("codec_type") == "video" and not s.get("disposition", {}).get("attached_pic")), None)
    a = next((s for s in st if s.get("codec_type") == "audio"), None)
    return v, a


def packet_pts(p):
    out = subprocess.run([FFPROBE, "-v", "error", "-select_streams", "v:0", "-show_entries", "packet=pts_time",
                          "-of", "csv=p=0", p], capture_output=True, text=True).stdout
    vals = []
    for l in out.splitlines():
        l = l.split(",")[0].strip()
        try:
            vals.append(float(l))
        except ValueError:
            pass
    return np.array(sorted(vals))


def fnum(s, default=None):
    try:
        return float(s)
    except (TypeError, ValueError):
        return default


def sar_of(v):
    s = v.get("sample_aspect_ratio", "1:1")
    try:
        a, b = s.split(":")
        return float(a) / float(b) if float(b) and float(a) else 1.0
    except ValueError:
        return 1.0


def geometry(w, h, sar, policy):
    """-> (policy actually applied, text, filter chain up to the scale, pad filter or None, resamples?)"""
    target = SW / SH
    ar = w * sar / h
    resize = f"scale={SW}:{SH}"
    if abs(ar / target - 1) < 0.005:
        return "none", ("scale to 1920x1080" if (w, h) != (SW, SH) else "no resize"), [resize], None, (w, h) != (SW, SH)
    if policy == "auto":
        policy = "stretch" if ar < target else "crop"
    if policy == "stretch":
        return "stretch", f"stretch {w}x{h} to 16:9", [resize], None, True
    if policy == "crop":
        if ar > target:
            cw, ch = int(h * target / sar) // 2 * 2, h
        else:
            cw, ch = w, int(w * sar / target) // 2 * 2
        x, y = (w - cw) // 4 * 2, (h - ch) // 4 * 2
        return "crop", f"crop centre {cw}x{ch}", [f"crop={cw}:{ch}:{x}:{y}", resize], None, True
    if ar > target:
        sw, sh = SW, int(round(SW / ar / 2)) * 2
    else:
        sw, sh = int(round(SH * ar / 2)) * 2, SH
    return "pad", f"pad {sw}x{sh} in 16:9", [f"scale={sw}:{sh}"], f"pad={SW}:{SH}:{(SW - sw) // 2}:{(SH - sh) // 2}:black", True


def decode_filter(v, policy):
    w, h = int(v["width"]), int(v["height"])
    used, text, chain, pad, resample = geometry(w, h, sar_of(v), policy)
    rng = "pc" if v.get("color_range") == "pc" else "tv"
    flags = ":flags=lanczos+accurate_rnd+full_chroma_int" if resample else ""
    mat = "" if v.get("color_space") in ("bt709", "bt470bg", "smpte170m", "bt2020nc") else \
        f":in_color_matrix={'bt709' if h >= 720 else 'bt601'}"
    chain = chain[:-1] + [chain[-1] + flags + f":in_range={rng}:out_range=pc" + mat, "format=rgb24"]
    if pad:
        chain.append(pad)
    return ",".join(chain), used, text


def make_plan(ts, fast):
    """Per output frame n: src (source index of the picture or the first of the pair), frac (0 = a source picture;
    otherwise the interpolation fraction towards src + 1), kind. The same grid in both modes."""
    n_src, t0 = len(ts), ts[0]
    N = int(np.floor((ts[-1] - t0 + TOL) * FPS)) + 1
    tn = t0 + np.arange(N) / FPS
    j = np.clip(np.searchsorted(ts, tn, side="right") - 1, 0, n_src - 2)
    lo, hi = ts[j], ts[j + 1]
    near = np.where(tn - lo <= hi - tn, j, j + 1)
    err = np.abs(tn - ts[near])
    gap = ((hi - lo) > MAXGAP) | ((hi - lo) < 1e-6)       # a hole, or two frames with the same timestamp
    frac = np.clip((tn - lo) / np.maximum(hi - lo, 1e-6), 0, 1)
    pick = err <= TOL
    kind = np.empty(N, "U7")                      # pick | nearest | interp | held
    if fast:
        dup = np.zeros(N, bool)
        dup[1:] = near[1:] == near[:-1]
        interp = dup & ~gap & ~pick
        kind[:] = np.where(pick, "pick", np.where(gap, "held", "nearest"))
        kind[interp] = "interp"
    else:
        kind[:] = np.where(pick, "pick", np.where(gap, "held", "interp"))
    src = np.where(kind == "interp", j, near)
    frac = np.where(kind == "interp", frac, 0.0)
    return N, src, frac, kind, err


class Counting:
    """Counts the calls RIFE gets (rifeutil.Tween calls process_cv2 once or twice)."""

    def __init__(self, rife):
        self.rife = rife

    def process_cv2(self, a, b, t):
        global RIFE_CALLS
        RIFE_CALLS += 1
        return self.rife.process_cv2(a, b, t)


def convert(name, path, v, a, ts, mode, policy):
    """Write src/<name>.mkv. -> manifest fields."""
    import rifeutil
    rate = (len(ts) - 1) / (ts[-1] - ts[0])
    dur = ts[-1] - ts[0]
    if mode is None:
        mode = "exact" if dur <= EXACT_MAX_S else "fast"
    forced = ""
    if mode == "fast" and rate < MIN_FPS_FAST:
        mode, forced = "exact", " (below 60 fps: always exact)"
    N, src, frac, kind, err = make_plan(ts, mode == "fast")
    n_interp = int((kind == "interp").sum())
    vf, used, text = decode_filter(v, policy)
    w, h = int(v["width"]), int(v["height"])

    af = None
    if a is not None:
        sr = int(a.get("sample_rate", 48000))
        a0, t0 = fnum(a.get("start_time"), ts[0]), ts[0]
        shift = int(round((a0 - t0) * sr))
        if shift > 0:
            af = f"adelay=delays={shift}S:all=1,"
        elif shift < 0:
            af = f"atrim=start_sample={-shift},"
        else:
            af = ""
        af += "asetpts=N/SR/TB"
    dst = os.path.join("src", name + ".mkv")
    part = os.path.join("src", "_" + name + ".part")
    dec = subprocess.Popen([FF, "-v", "error", "-i", path, "-map", "0:v:0", "-vf", vf, "-fps_mode", "passthrough",
                            "-f", "rawvideo", "-pix_fmt", "rgb24", "-"], stdout=subprocess.PIPE)
    enc_cmd = [FF, "-v", "error", "-y", "-f", "rawvideo", "-pix_fmt", "rgb24", "-s", f"{SW}x{SH}", "-framerate", str(FPS), "-i", "-"]
    if af is not None:
        enc_cmd += ["-i", path]
    enc_cmd += ["-map", "0:v:0"] + (["-map", "1:a:0", "-af", af, "-c:a", "flac", "-sample_fmt", "s32"] if af is not None else []) + [
        "-map_metadata", "-1", "-map_chapters", "-1",
        "-vf", "scale=out_color_matrix=bt709:out_range=tv,setparams=colorspace=bt709:color_primaries=bt709:color_trc=bt709:range=tv,format=yuv420p",
        "-c:v", "libx264", "-preset", "fast", "-crf", "9", "-g", "60",
        "-f", "matroska", part]
    enc = subprocess.Popen(enc_cmd, stdin=subprocess.PIPE)

    frames_q, out_q = queue.Queue(maxsize=6), queue.Queue(maxsize=6)

    def reader():
        for _ in range(len(ts)):
            buf = np.empty((SH, SW, 3), np.uint8)
            mv, got = memoryview(buf).cast("B"), 0
            while got < len(mv):
                k = dec.stdout.readinto(mv[got:])
                if not k:
                    break
                got += k
            if got < len(mv):
                frames_q.put(None)
                return
            frames_q.put(buf)
        frames_q.put(None)

    def writer():
        ok = True
        while True:
            img = out_q.get()
            if img is None:
                return
            if ok:
                try:
                    enc.stdin.write(img)
                except OSError:
                    ok = False                            # the encoder died (reported below); keep draining so nothing blocks

    threading.Thread(target=reader, daemon=True).start()
    wt = threading.Thread(target=writer, daemon=True)
    wt.start()

    cache, loaded = {}, -1
    tween = None
    rife_loaded = False

    def get(i):
        nonlocal loaded
        while loaded < i:
            f = frames_q.get()
            if f is None:
                raise SystemExit(f"{name}: ffmpeg decoded only {loaded + 1} of the {len(ts)} frames that the packet table lists "
                                 f"(a broken start or end?): cannot index frames; re-encode the source or trim it first")
            loaded += 1
            cache[loaded] = f
        return cache[i]

    t_start = time.time()
    try:
        for n in range(N):
            i = int(src[n])
            for k in [k for k in cache if k < i]:
                del cache[k]
            if kind[n] == "interp":
                if tween is None:
                    tween = rifeutil.Tween(Counting(rifeutil.load()))
                    rife_loaded = True
                img = tween(get(i), get(i + 1), float(frac[n]), tag=i)
            else:
                img = get(i)
            out_q.put(np.ascontiguousarray(img))
            if sys.stderr.isatty() and n % 60 == 0:
                sys.stderr.write(f"\r  {name}: {n}/{N} frames, {(n + 1) / (time.time() - t_start):.1f} fps ")
        out_q.put(None)
        wt.join()
        try:
            enc.stdin.close()
        except OSError:
            pass                                          # the encoder died: its exit code is checked below
        # the reader may be ahead of the last frame used: drain its queue so the decoder can end
        while frames_q.get() is not None:
            pass
    except BaseException:
        dec.kill()
        enc.kill()
        if os.path.exists(part):
            try:
                os.remove(part)
            except OSError:
                pass
        raise
    dec.stdout.close()
    dec.wait()
    rc = enc.wait()
    if sys.stderr.isatty():
        sys.stderr.write("\r" + " " * 70 + "\r")
    if rc != 0:
        if os.path.exists(part):
            os.remove(part)
        raise SystemExit(f"{name}: the ffmpeg encoder failed (exit code {rc})")
    for old in glob.glob(os.path.join("src", name + ".*")):
        os.remove(old)
    os.replace(part, dst)
    fixed = ~np.isin(kind, ["interp"])
    return dst, dict(
        method=mode, aspect=used, frames=N, picked=int((kind == "pick").sum()), nearest=int((kind == "nearest").sum()),
        interpolated=n_interp, held=int((kind == "held").sum()), rife_calls=RIFE_CALLS,
        max_error_ms=round(float(err[fixed].max() * 1000), 3) if fixed.any() else 0.0), \
        f"converted: {text}, {mode}{forced}: {int((kind == 'pick').sum())} picked, {int((kind == 'nearest').sum())} nearest, " \
        f"{n_interp} interpolated" + (f", {int((kind == 'held').sum())} held across a hole or repeated timestamps" if (kind == "held").any() else ""), \
        N, rife_loaded


def link(p, dst):
    try:
        os.link(p, dst)
        return "linked"
    except OSError:
        shutil.copy2(p, dst)
        return "copied"


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0], formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("clips", nargs="?", default="clips.json")
    ap.add_argument("--only", help="comma separated names")
    g = ap.add_mutually_exclusive_group()
    g.add_argument("--exact", action="store_true", help="interpolate frames that fall between source frames (default up to 90 s)")
    g.add_argument("--fast", action="store_true", help="nearest source frame instead (default for longer clips)")
    ap.add_argument("--aspect", choices=("stretch", "crop", "pad"), default="auto",
                    help="stretch (default for narrower than 16:9), crop (default for wider), pad")
    ap.add_argument("--convert", action="store_true", help="also convert a 1920x1080 ~60 fps source instead of linking it (testing)")
    ap.add_argument("--force", action="store_true", help="re-ingest entries that already exist")
    args = ap.parse_args()

    spec = json.load(open(args.clips, encoding="utf-8-sig"))      # utf-8-sig: PowerShell writes a BOM
    names = list(spec)
    if args.only:
        want = [x.strip() for x in args.only.split(",") if x.strip()]
        bad = [x for x in want if x not in spec]
        if bad:
            raise SystemExit(f"--only: not in {args.clips}: {', '.join(bad)}")
        names = [x for x in names if x in want]
    mode = "exact" if args.exact else "fast" if args.fast else None
    os.makedirs("src", exist_ok=True)
    mf_path = os.path.join("src", "ingest.json")
    manifest = json.load(open(mf_path, encoding="utf-8")) if os.path.exists(mf_path) else {}
    global RIFE_CALLS
    rife_used = False
    redo = []
    for name in names:
        p = spec[name]
        t_in = time.time()
        have = sorted(glob.glob(os.path.join("src", name + ".*")))
        old = manifest.get(name)
        if have and not args.force and not (args.exact and old and old.get("method") == "fast"):
            print(f"{name}: kept {have[0]}" + (f" ({old['method']})" if old else ""))
            continue
        if not os.path.exists(p):
            print(f"{name}: MISSING original {p}")
            continue
        v, a = probe(p) if os.path.splitext(p)[1].lower() in VIDEO else (None, None)
        if v is None:
            dst = os.path.join("src", name + os.path.splitext(p)[1].lower())
            for o in have:
                os.remove(o)
            how = link(p, dst)
            manifest[name] = dict(original=p, method=how)
            print(f"{name}: not a video -> {how} {dst}  ({time.time() - t_in:.1f} s)")
        else:
            ts = packet_pts(p)
            if len(ts) < 2:
                print(f"{name}: no video packets in {p}")
                continue
            w, h = int(v["width"]), int(v["height"])
            rate = (len(ts) - 1) / (ts[-1] - ts[0])
            k = min(30, len(ts) - 1)                         # the recorder's frame rate, unaffected by dropped frames: median
            mrate = 1.0 / float(np.median((ts[k:] - ts[:-k]) / k))   # over 30-frame spans (pts are rounded to ms: 16/17/17)
            desc = f"{w}x{h} @ {rate:.3f} fps"
            ent = dict(original=p, width=w, height=h, fps=round(rate, 4), t0=round(float(ts[0]), 6))
            if v.get("color_transfer") in ("smpte2084", "arib-std-b67"):
                print(f"{name}: WARNING HDR source ({v['color_transfer']}): colours are not tone mapped; record SDR")
            if (w, h) == (SW, SH) and abs(mrate - FPS) < CONFORM_FPS and not args.convert:
                for o in have:
                    os.remove(o)
                dst = os.path.join("src", name + os.path.splitext(p)[1].lower())
                how = link(p, dst)
                ent.update(method=how, aspect="none")
                manifest[name] = ent
                gap = "" if abs(rate - FPS) < CONFORM_FPS else f"; 60 fps with dropped frames ({rate:.3f} on average): see mkpts.py"
                print(f"{name}: {desc} -> {how} {dst}{gap}  ({time.time() - t_in:.1f} s)")
            else:
                RIFE_CALLS = 0
                dst, info, text, nfr, used_rife = convert(name, p, v, a, ts, mode, args.aspect)
                rife_used |= used_rife
                ent.update(info)
                manifest[name] = ent
                el = time.time() - t_in
                print(f"{name}: {desc} -> {text}  ({el:.1f} s, {nfr / el:.1f} frames/s)")
        if have and v is not None:
            redo.append(name)
        json.dump(manifest, open(mf_path, "w", encoding="utf-8"), indent=1)
    for name in redo:
        todo = f"delete store/{name}, re-run mkpts.py {name} and prep.py" if os.path.isdir(os.path.join("store", name)) else f"re-run mkpts.py {name}"
        print(f"{name}: re-ingested (same frame grid, other pictures): {todo}")
    if rife_used:
        import rifeutil
        rifeutil.finish()


if __name__ == "__main__":
    main()
