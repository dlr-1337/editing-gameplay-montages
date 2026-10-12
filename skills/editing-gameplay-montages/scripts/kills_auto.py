"""Find your kills in any shooter: the kill-feed row that appears, the shot frame K behind it, and review sheets.

usage: python kills_auto.py valorant              every clip in src/
       python kills_auto.py cs2 c1 c3             only these clips
       python kills_auto.py generic c2            untuned fallback: feed top right, every row, no ammo
       python kills_auto.py valorant --regions c2 1500    draw the profile's regions on frame 1500 -> regions.jpg
       python kills_auto.py valorant c2 --drop 12,15      remove rejected ids from kills.json

<game> is games/<game>.json (or a path to a profile). Coordinates in a profile are in the 1920x1080 working frame
(src/ is 1920x1080, 60 fps, ingest.py). Frames are read through clipio, by index.

What it does for each clip
  1. KILL-FEED ROWS. The feed region is decoded once. A row is a band of about `row_h` pixels that, within a few
     frames, turns into something different from the frames before it AND then stays still (rows are static, the
     scene behind moves). That finds the row appearing even when the whole region changes, and a fade-in as well
     as a pop-in. With an `own` rule in the profile (colour tests, e.g. Valorant's lime accent + teal body, CS2's
     red outline) only the rows that pass are kept. Without one (generic) EVERY row is kept: teammates' and
     enemies' kills too; the sheets show which are yours.
  2. SHOT FRAME K. The gunshots of the clip's own audio (sudden rise of the high-frequency level) in the window
     where the shot must lie before the row (profile lag.feed_frames), refined on the picture: the muzzle flash
     (newly bright pixels in the profile's weapon region) and, if the profile has an ammo region, the frame where
     the ammo digits change (mykills.py's rule). Candidates are scored by how many of the three agree; the best wins.
     With several shots in the window (a spray) the one nearest the usual feed latency (lag.typical) is taken.
  3. OUTPUT.
       kills.json       {id: {clip, K, feed, conf, method, changes, ...}}: K = shot frame (flash visible on K, absent on
                        K-1), feed = first frame of the row appearing, conf = high | medium | low | guess,
                        method = the signals that agreed (ammo, flash, audio) or "feed-lag" for a pure guess,
                        changes = earlier shots (ammo/flash frames) in the 30 frames before K (flick.py reads it).
                        Runs replace the entries of the clips they process and keep the others.
       autokill_NN.jpg  review sheets, 5 kills per sheet. Per row: the feed at the event | weapon zoom K-1, K, K+1 |
                        full frames K-8, K, K+8. READ THEM. Confirm each row: it is a kill of yours, the flash is on
                        tile K and not on K-1. Wrong K: edit kills.json (or --drop the id). Rows with conf low or
                        guess need the closest look.

Reading the console: per clip the number of feed rows found, how many passed the own rule, then one line per kill:
  id, K, feed, feed-K lag, conf, signals, audio offset (frames after K; 1.4 to 3.3 is normal, it varies per recording).
A clip whose own sound is voice chat or music gives no audio support: K then rests on the picture alone.

Profile fields (games/valorant.json is the reference, "notes" says where every number comes from):
  feed.region [x,y,w,h]   where the rows live; feed.row_h  height of one row; feed.row_min_w  width of the shortest row;
  feed.align right|left   which edge the rows hug; feed.own  null or {"masks": [{"name","hue":[[lo,hi]],"s_min","v_min",
  "min_px"}]}: the row is yours when EVERY colour mask has at least min_px pixels inside the row band (OpenCV hue 0-179);
  weapon.region           where the muzzle flash shows (also the zoom tiles); ammo {"region","digit_min"} or null;
  lag.feed_frames [lo,hi] frames from K to the row appearing; lag.typical; lag.audio_frames [lo,hi] and
  lag.audio_typical: frames from the flash to the gunshot in the audio; validated false = nobody checked it on footage.

Calibrating a profile for a new game: --regions on a frame with a kill on screen; fix the rectangles; run on a clip
with known kills and read the sheets. Everything is measured, nothing is read from the profile as truth."""
import argparse, glob, json, os, subprocess, sys
import numpy as np
import cv2
import clipio
from ff import FF

HERE = os.path.dirname(os.path.abspath(__file__))
SR = 48000
VIDEO = (".mp4", ".mkv", ".mov", ".m4v", ".webm", ".avi")
LOOK = 12            # frames from "before the row" to "row finished": slide-in or fade-in is over by then
HOLD = 6             # frames the finished row must stay still
CHANGED = 40         # max-channel level change that counts as "a pixel changed"
STILL = 10           # ... and as "a pixel did not move"


def load_profile(game):
    p = game if game.lower().endswith(".json") else os.path.join(HERE, "games", game + ".json")
    if not os.path.exists(p):
        have = sorted(os.path.splitext(os.path.basename(f))[0] for f in glob.glob(os.path.join(HERE, "games", "*.json")))
        sys.exit(f"no profile {p}. Profiles available: {', '.join(have)}. Start from generic.json: copy it to games/<game>.json.")
    prof = json.load(open(p, encoding="utf-8"))
    prof["_name"] = os.path.splitext(os.path.basename(p))[0]
    return prof


# ---------------------------------------------------------------------------------------------- frames
def read(clip, a, b):
    """Frames a..b (inclusive) of the clip, uint8 (N, 1080, 1920, 3) RGB: the same pixels as clipio.read_frames(crop=False),
    but ffmpeg stops after the last frame (read_frames lets it decode the rest of the file: seconds per call)."""
    raw = subprocess.run([FF, "-v", "error"] + clipio.frame_args(clip, a, b, "scale=in_range=tv:out_range=pc,format=rgb24")
                         + ["-frames:v", str(b - a + 1), "-f", "rawvideo", "-"], capture_output=True).stdout
    arr = np.frombuffer(raw, np.uint8).reshape(-1, clipio.SH, clipio.SW, 3)
    assert len(arr) == b - a + 1, (clip, a, b, len(arr))
    return arr


# ---------------------------------------------------------------------------------------------- feed rows
def stream(clip, x, y, w, h):
    """Every frame of the clip, cropped to the region, RGB (colour conversion identical to clipio.read_frames)."""
    vf = f"crop={w}:{h}:{x}:{y},scale=in_range=tv:out_range=pc,format=rgb24"
    p = subprocess.Popen([FF, "-v", "error", "-i", clipio.path(clip), "-map", "0:v:0", "-vf", vf, "-fps_mode", "passthrough",
                          "-f", "rawvideo", "-"], stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, bufsize=w * h * 3 * 8)
    size = w * h * 3
    while True:
        buf = p.stdout.read(size)
        if len(buf) < size:
            break
        yield np.frombuffer(buf, np.uint8).reshape(h, w, 3)
    p.wait()


def color_counts(rgb, own):
    """Pixels per colour mask of the profile's own rule inside rgb (h, w, 3)."""
    hsv = cv2.cvtColor(np.ascontiguousarray(rgb), cv2.COLOR_RGB2HSV)
    hh, ss, vv = hsv[..., 0], hsv[..., 1], hsv[..., 2]
    out = {}
    for m in own["masks"]:
        hm = np.zeros(hh.shape, bool)
        for lo, hi in m["hue"]:
            hm |= (hh >= lo) & (hh <= hi)
        out[m["name"]] = int((hm & (ss >= m.get("s_min", 0)) & (vv >= m.get("v_min", 0)) & (vv <= m.get("v_max", 255))).sum())
    return out


def line_runs(mask):
    """[(a, b)) of consecutive True lines."""
    idx = np.flatnonzero(np.diff(np.r_[0, mask.astype(np.int8), 0]))
    return list(zip(idx[::2], idx[1::2]))


def scan_feed(clip, prof, trace=None):
    """Rows appearing in the feed region: [{onset, y0, y1, own, counts}] (y in frame pixels, onset = frame index).
    trace: a list that receives (frame, y0, y1, reason, ...) for every candidate band that was thrown out (diagnostics)."""
    trace = [] if trace is None else trace
    fx, fy, fw, fh = prof["feed"]["region"]
    row_h, min_w = prof["feed"]["row_h"], prof["feed"]["row_min_w"]
    right = prof["feed"].get("align", "right") == "right"
    own = prof["feed"].get("own")
    look = prof["feed"].get("settle_frames", LOOK)
    cw = max(8, min_w // 2)
    lo_h, hi_h = max(4, int(0.6 * row_h / 2)), int(1.6 * row_h / 2) + 1
    full, small, still = {}, {}, {}
    state = {"runs": [], "events": [], "last": -1}

    def get(k):
        return min(k, state["last"])

    def process(j):
        pre, post = small[j - 2], small[get(j + look)]
        cov = (np.abs(post - pre).max(2) > CHANGED).mean(1)
        calm = np.mean([still[k] for k in range(get(j + look) - 2, get(j + look + HOLD) + 1)], axis=0)
        for a, b in line_runs((cov >= 0.5) & (calm >= 0.85)):       # changed AND now still: lines of a finished row, even
            if not lo_h <= b - a <= hi_h:                            # when the whole scene behind it moved
                continue
            for r in state["runs"]:                      # same band as a run that is still open?
                ov = min(b, r["b"]) - max(a, r["a"])
                if ov >= 0.5 * min(b - a, r["b"] - r["a"]) and j - r["j1"] <= 3:
                    r["j1"], r["a"], r["b"] = j, a, b
                    break
            else:
                state["runs"].append({"j0": j, "j1": j, "a": a, "b": b})

    def finish(r, newest):
        a, b, j = r["a"], r["b"], r["j1"]
        pre = small[j - 2]
        rows = slice(max(0, 2 * a - 2), 2 * b + 2)
        tex = lambda s: float(np.abs(s[:, 1:] - s[:, :-1]).max(2).mean())
        t_pre, t_post = tex(pre[a:b]), tex(small[get(j + look)][a:b])
        if not own and t_post < 0.8 * t_pre:
            trace.append((j, fy + 2 * a, fy + 2 * b, "flatter", round(t_pre, 1), round(t_post, 1)))
            return                                                  # no own rule: a band that got flatter is a row going away
        if own and all(color_counts(full[max(0, r["j0"] - 2)][rows], own)[m["name"]] >= m["min_px"] for m in own["masks"]):
            trace.append((j, fy + 2 * a, fy + 2 * b, "own row there before"))
            return                                                  # an own row was already there before the change: it is leaving
        onset = j
        for t in range(j - 1, min(newest, j + look) + 1):          # first frame where the band no longer looks like before
            if (np.abs(small[t][a:b] - pre[a:b]).max(2) > CHANGED).mean() >= 0.4:
                onset = t
                break
        ev = {"onset": int(onset), "y0": int(fy + 2 * a), "y1": int(fy + 2 * b), "own": None, "counts": None}
        if own:
            best = None
            for t in range(onset + 1, min(newest, onset + 26) + 1):
                cnt = color_counts(full[t][rows], own)
                ok = all(cnt[m["name"]] >= m["min_px"] for m in own["masks"])
                score = sum(min(1.0, cnt[m["name"]] / m["min_px"]) for m in own["masks"])
                if best is None or (ok, score) > (best[0], best[1]):
                    best = (ok, score, cnt, t)
            if best:
                ev["own"], ev["counts"], ev["t_own"] = bool(best[0]), best[2], int(best[3])
        state["events"].append(ev)

    def flush(newest, final=False):
        keep = []
        for r in state["runs"]:
            if final or newest - look - HOLD - r["j1"] > 3:
                finish(r, newest)
            else:
                keep.append(r)
        state["runs"] = keep

    n = 0
    for i, f in enumerate(stream(clip, fx, fy, fw, fh)):
        n = i + 1
        state["last"] = i
        full[i] = f
        s = cv2.resize(f, (fw // 2, fh // 2), interpolation=cv2.INTER_AREA).astype(np.int16)
        s = s[:, -cw:] if right else s[:, :cw]
        small[i] = s
        still[i] = (np.abs(s - small[i - 1]).max(2) <= STILL).mean(1) if i else np.ones(s.shape[0])
        j = i - (look + HOLD)
        if j >= 2:
            process(j)
        flush(i)
        for k in [k for k in small if k < i - 80]:
            full.pop(k, None), small.pop(k), still.pop(k)
    last = state["last"]
    for j in range(max(2, last - (look + HOLD) + 1), last - 1):      # the tail: the "row finished" frame is clamped to the end
        process(j)
    flush(last, final=True)
    if n != clipio.n_frames(clip):
        print(f"  WARNING {clip}: decoded {n} frames but pts/{clip}.csv has {clipio.n_frames(clip)}: frame indices may be off")
    events = []
    for e in sorted(state["events"], key=lambda e: e["onset"]):      # one row seen twice (two bands, same frame): keep the first
        if not events or e["onset"] - events[-1]["onset"] > 2:
            events.append(e)
        elif (e["own"], sum((e["counts"] or {}).values())) > (events[-1]["own"], sum((events[-1]["counts"] or {}).values())):
            events[-1] = e
    return events


# ---------------------------------------------------------------------------------------------- audio
def audio_onsets(clip):
    """Gunshot-like onsets of the clip's own audio: [(frame (float), strength)]. A sudden rise of the level of the
    highs (first difference), 2 ms bins, against the 24 ms before it."""
    raw = subprocess.run([FF, "-v", "error", "-i", clipio.path(clip), "-map", "0:a:0", "-ac", "1", "-ar", str(SR), "-f", "f32le", "-"],
                         capture_output=True).stdout
    x = np.frombuffer(raw, np.float32)
    if len(x) < SR:
        return []
    hp = np.diff(x, prepend=0.0)
    nb = len(hp) // 96
    e = np.sqrt((hp[:nb * 96].reshape(nb, 96) ** 2).mean(1)) + 1e-6
    csum = np.r_[0, np.cumsum(e)]
    base = np.empty(nb)
    base[12:] = (csum[12:nb] - csum[0:nb - 12]) / 12          # mean of the 12 bins before bin j
    base[:12] = e[:12].mean()
    peak = np.maximum.reduce([e[k:nb - 3 + k] for k in range(4)])
    peak = np.r_[peak, np.full(3, e[-1])]
    floor = np.percentile(e, 30)
    hit = (peak > 2.4 * base) & (peak > 4 * floor) & (e > 1.6 * base)
    out, last = [], -100
    p = clipio.pts(clip)
    for j in np.flatnonzero(hit):
        if j - last < 10:                                     # one onset per 20 ms
            continue
        last = j
        t = (j + 0.5) * 96 / SR
        out.append((float(np.interp(t, p, np.arange(len(p)))), float(peak[j] / base[j])))
    return out


# ---------------------------------------------------------------------------------------------- shot frame
def rising_runs(score, floor, ratio):
    """Frames where a series jumps: at least `floor` and `ratio` times the mean of the 4 frames before it."""
    out = []
    for k in range(4, len(score)):
        if score[k] >= floor and score[k] >= ratio * (score[k - 4:k].mean() + 1) and score[k] >= score[k - 1]:
            if not out or k - out[-1] > 1:
                out.append(k)
    return out


def shot_signals(clip, a, b, prof):
    """Picture signals on frames a..b: {'flash': [frames], 'ammo': [frames]} (absolute frame indices)."""
    fr = read(clip, a, b)
    wx, wy, ww, wh = prof["weapon"]["region"]
    V = fr[:, wy:wy + wh, wx:wx + ww].max(3).astype(np.int16)
    new = np.r_[0, ((V[1:] - V[:-1] > 50) & (V[1:] > 200)).sum((1, 2))].astype(float)
    flash = [a + k for k in rising_runs(new, 0.0023 * ww * wh, 3.0)]
    ammo = []
    if prof.get("ammo"):
        ax, ay, aw, ah = prof["ammo"]["region"]
        masks = [fr[i, ay:ay + ah, ax:ax + aw].min(axis=2) > prof["ammo"].get("digit_min", 205) for i in range(len(fr))]
        chg = np.zeros(len(fr))
        for i in range(1, len(fr)):
            chg[i] = (masks[i] ^ masks[i - 1]).sum() / max((masks[i] | masks[i - 1]).sum(), 40)
        ammo = [a + i for i in range(3, len(fr) - 3)
                if chg[i] > 0.28 and max(chg[i + 1], chg[i + 2], chg[i - 1], chg[i - 2]) < 0.15 and masks[i].sum() > 60]
    return {"flash": flash, "ammo": ammo}


def find_shot(clip, ev, prof, onsets):
    """K for one feed event. Returns the dict that goes to kills.json."""
    lag = prof["lag"]
    feed = ev["onset"]
    lo, hi = lag["feed_frames"]
    typical = lag["typical"]
    alo, ahi = lag["audio_frames"]
    atyp = lag["audio_typical"]
    n = clipio.n_frames(clip)
    a = max(0, feed - hi - 10)
    b = min(n - 1, feed - lo + 3)
    sig = shot_signals(clip, a, b, prof)
    aud = [(o, s) for o, s in onsets if a <= o <= b + ahi + 1]
    pool = {}
    for kind in ("ammo", "flash"):
        for f in sig[kind]:
            if feed - hi <= f <= feed - lo:
                for g in pool:                                 # merge candidates within one frame
                    if abs(g - f) <= 1:
                        pool[g].append((kind, f))
                        break
                else:
                    pool[f] = [(kind, f)]
    best = None
    for g, items in pool.items():
        kinds = {k for k, _ in items}
        pic = min((f for k, f in items if k == "ammo"), default=min(f for _, f in items))
        sup = [o - pic for o, _ in aud if alo <= o - pic <= ahi]
        score = 3 * ("ammo" in kinds) + 2 * ("flash" in kinds) + 2 * bool(sup) - 0.15 * abs(feed - pic - typical)
        if best is None or score > best["score"]:
            best = {"score": score, "K": int(pic), "kinds": sorted(kinds), "audio": min(sup, key=lambda d: abs(d - atyp)) if sup else None}
    all_shots = sorted({f for kind in ("ammo", "flash") for f in sig[kind]})
    if best:
        method = "+".join(best["kinds"] + (["audio"] if best["audio"] is not None else []))
        nk = len(best["kinds"]) + (best["audio"] is not None)
        conf = "high" if ("ammo" in best["kinds"] and nk >= 2) or nk == 3 else ("medium" if nk >= 2 or "ammo" in best["kinds"] else "low")
        K, au = best["K"], best["audio"]
    else:
        cand = [(o, s) for o, s in aud if feed - hi <= o - atyp <= feed - lo]
        if cand:
            o = min(cand, key=lambda q: abs(feed - (q[0] - atyp) - typical))[0]
            K, au, method, conf = int(round(o - atyp)), atyp, "audio", "low"
        else:
            K, au, method, conf = feed - typical, None, "feed-lag", "guess"
    return {"K": int(K), "feed": int(feed), "conf": conf, "method": method,
            "audio_after_K": None if au is None else round(float(au), 2),
            "changes": [int(f) for f in all_shots if K - 30 <= f < K]}


# ---------------------------------------------------------------------------------------------- sheets
def label(img, text, x, y, scale=1.0, color=(0, 255, 255)):
    (w, h), base = cv2.getTextSize(text, cv2.FONT_HERSHEY_SIMPLEX, scale, 2)
    cv2.rectangle(img, (x, y), (x + w + 8, y + h + base + 6), (0, 0, 0), -1)
    cv2.putText(img, text, (x + 4, y + h + 3), cv2.FONT_HERSHEY_SIMPLEX, scale, color, 2, cv2.LINE_AA)


TW, TH = 320, 180


def fit(rgb, tw, th):
    h, w = rgb.shape[:2]
    s = min(tw / w, th / h)
    im = cv2.resize(rgb, (max(1, int(w * s)), max(1, int(h * s))), interpolation=cv2.INTER_AREA)
    out = np.zeros((th, tw, 3), np.uint8)
    out[:im.shape[0], :im.shape[1]] = im
    return out


def review_row(kid, k, ev, prof):
    c, K = k["clip"], k["K"]
    n = clipio.n_frames(c)
    a, b = max(0, K - 8), min(n - 1, K + 8)
    fr = read(c, a, b)
    at = lambda f: fr[min(max(f, a), b) - a]
    fx, fy, fw, fh = prof["feed"]["region"]
    y0 = max(fy, ev["y0"] - int(0.6 * prof["feed"]["row_h"]))
    y1 = min(fy + fh, ev["y1"] + int(0.6 * prof["feed"]["row_h"]))
    feed_tile = np.zeros((TH, 480, 3), np.uint8)
    for q, (off, name) in enumerate(((-3, "feed before"), (10, "feed +10"))):
        f = min(n - 1, max(0, ev["onset"] + off))
        crop = fit(read(c, f, f)[0][y0:y1, fx:fx + fw], 480, 88)
        label(crop, name, 0, 0, 0.7)
        feed_tile[q * 90:q * 90 + 88] = crop
    tiles = [feed_tile]
    wx, wy, ww, wh = prof["weapon"]["region"]
    for off in (-1, 0, 1):
        t = fit(at(K + off)[wy:wy + wh, wx:wx + ww], TW, TH)
        label(t, "K%+d" % off if off else "K", 0, TH - 34, 1.0, (0, 255, 255) if off else (0, 255, 0))
        tiles.append(t)
    for off in (-8, 0, 8):
        t = fit(at(K + off), TW, TH)
        label(t, "K%+d" % off if off else "K", 0, TH - 34, 1.0)
        tiles.append(t)
    row = np.hstack(tiles)
    own = {None: "all rows", True: "own", False: "NOT own"}[ev.get("own")]
    head = np.zeros((34, row.shape[1], 3), np.uint8)
    label(head, "#%s  %s  K=%d  feed=%d  %s  %s  (%s)" % (kid, c, K, k["feed"], k["conf"].upper(), k["method"], own), 0, 0, 1.0, (0, 255, 255))
    return cv2.cvtColor(np.vstack([head, row]), cv2.COLOR_RGB2BGR)


def write_sheets(rows, per=5):
    for f in glob.glob("autokill_*.jpg"):
        os.remove(f)
    names = []
    for s in range(0, len(rows), per):
        name = "autokill_%02d.jpg" % (s // per + 1)
        cv2.imwrite(name, np.vstack(rows[s:s + per]), [cv2.IMWRITE_JPEG_QUALITY, 88])
        names.append(name)
    return names


# ---------------------------------------------------------------------------------------------- regions
def draw_regions(prof, clip, frame):
    fr = read(clip, frame, frame)[0].copy()
    big = fr.copy()
    f = prof["feed"]
    x, y, w, h = f["region"]
    cv2.rectangle(big, (x, y), (x + w - 1, y + h - 1), (255, 255, 0), 3)
    y_first, pitch = f.get("first_row_y", y), f.get("row_pitch", f["row_h"])
    mw = f["row_min_w"]
    xx = x + w - mw if f.get("align", "right") == "right" else x
    k = 0
    while y_first + pitch * k + f["row_h"] <= y + h:        # one slot per row: the rows must sit in these slots
        ys = y_first + pitch * k
        cv2.rectangle(big, (xx, ys), (xx + mw - 1, ys + f["row_h"] - 1), (255, 128, 0), 2 if k == 0 else 1)
        k += 1
    wx, wy, ww, wh = prof["weapon"]["region"]
    cv2.rectangle(big, (wx, wy), (wx + ww - 1, wy + wh - 1), (0, 255, 255), 3)
    parts = [("feed", prof["feed"]["region"], (255, 255, 0)), ("weapon", prof["weapon"]["region"], (0, 255, 255))]
    if prof.get("ammo"):
        ax, ay, aw, ah = prof["ammo"]["region"]
        cv2.rectangle(big, (ax, ay), (ax + aw - 1, ay + ah - 1), (0, 255, 0), 3)
        parts.append(("ammo", prof["ammo"]["region"], (0, 255, 0)))
    big = cv2.cvtColor(cv2.resize(big, (1600, 900), interpolation=cv2.INTER_AREA), cv2.COLOR_RGB2BGR)
    for name, (rx, ry, rw, rh), col in parts:
        label(big, name, int(rx * 1600 / 1920), max(0, int(ry * 900 / 1080) - 30), 0.9, (col[2], col[1], col[0]))
    label(big, "%s  %s frame %d  validated=%s  (orange = one row slot, as wide as the shortest row)" % (
        prof["_name"], clip, frame, prof.get("validated")), 0, 0, 0.9)
    crops = []
    for name, (rx, ry, rw, rh), col in parts:
        if name == "weapon":
            continue
        cr = fit(fr[ry:ry + rh, rx:rx + rw], 500, 250 if name == "feed" else 120)
        cr = cv2.cvtColor(cr, cv2.COLOR_RGB2BGR)
        label(cr, name + " region, zoomed", 0, 0, 0.8)
        crops.append(cr)
    strip = np.zeros((max(c.shape[0] for c in crops), 1600, 3), np.uint8)
    x0 = 0
    for cr in crops:
        strip[:cr.shape[0], x0:x0 + cr.shape[1]] = cr
        x0 += cr.shape[1] + 10
    cv2.imwrite("regions.jpg", np.vstack([big, strip]), [cv2.IMWRITE_JPEG_QUALITY, 90])
    print("regions.jpg written: %s frame %d. Check: the YELLOW feed box holds every row with room to spare; each ORANGE slot "
          "sits on a row (same top edge, no wider than the row); the CYAN weapon box holds the muzzle flash; the GREEN ammo "
          "box holds the digits and nothing else." % (clip, frame))


# ---------------------------------------------------------------------------------------------- main
def clip_names():
    names = sorted(os.path.splitext(os.path.basename(f))[0] for f in glob.glob("src/*") if f.lower().endswith(VIDEO))
    return names


def analyze(clip, prof, verbose=True):
    """All own-kill (or, without an own rule, all) feed events of a clip with their shot frames."""
    if not os.path.exists(f"pts/{clip}.csv"):
        sys.exit(f"pts/{clip}.csv missing: run mkpts.py first")
    rows = scan_feed(clip, prof)
    keep = [e for e in rows if e["own"] is not False]
    if verbose:
        print(f"{clip}: {len(rows)} feed rows appeared, {len(keep)} kept" + (" (own rule: %d rejected)" % (len(rows) - len(keep)) if prof["feed"].get("own") else " (no own rule: every row)"), flush=True)
    onsets = audio_onsets(clip)
    out = []
    for ev in keep:
        k = find_shot(clip, ev, prof, onsets)
        k["clip"] = clip
        out.append((ev, k))
        if verbose:
            au = k["audio_after_K"]
            print("  K=%-6d feed=%-6d lag %-3d %-6s %-18s audio %s" % (k["K"], k["feed"], k["feed"] - k["K"], k["conf"], k["method"],
                                                                      "-" if au is None else "%+.1f" % au), flush=True)
    return out


def main():
    ap = argparse.ArgumentParser(description="find your kills: feed rows, shot frames, review sheets", add_help=True)
    ap.add_argument("game", help="profile name in games/ (valorant, cs2, generic) or a path to a profile json")
    ap.add_argument("clips", nargs="*", help="clip names in src/ (default: all)")
    ap.add_argument("--regions", nargs=2, metavar=("CLIP", "FRAME"), help="draw the profile's regions on one frame -> regions.jpg")
    ap.add_argument("--drop", help="ids to remove from kills.json (comma separated), then exit")
    ap.add_argument("--no-sheets", action="store_true")
    args = ap.parse_args()
    prof = load_profile(args.game)
    if not prof.get("validated"):
        print(f"NOTE: profile '{prof['_name']}' is not validated on footage ({prof.get('notes', '')[:160]}...): check it with --regions first.")
    if args.regions:
        clip, frame = args.regions[0], int(args.regions[1])
        draw_regions(prof, clip, frame)
        return
    if args.drop:
        kills = json.load(open("kills.json"))
        for i in args.drop.split(","):
            print("dropped", i, kills.pop(i.strip(), "(not there)"))
        json.dump(kills, open("kills.json", "w"), indent=1)
        return
    clips = args.clips or clip_names()
    kills = json.load(open("kills.json", encoding="utf-8")) if os.path.exists("kills.json") else {}
    kills = {i: k for i, k in kills.items() if k.get("clip") not in clips}
    nxt = max([int(i) for i in kills] + [-1]) + 1
    sheets, evs = [], []
    for c in clips:
        for ev, k in analyze(c, prof):
            kills[str(nxt)] = k
            evs.append((str(nxt), k, ev))
            nxt += 1
    json.dump(dict(sorted(kills.items(), key=lambda q: int(q[0]))), open("kills.json", "w"), indent=1)
    print(f"kills.json: {len(kills)} kills ({len(evs)} from this run)")
    if not args.no_sheets and evs:
        rows = [review_row(kid, k, ev, prof) for kid, k, ev in evs]
        print("sheets:", ", ".join(write_sheets(rows)), "- 5 kills each: feed | weapon K-1, K, K+1 | full K-8, K, K+8")
    if not prof["feed"].get("own"):
        print("NOTE: this profile has no own-kill rule: every kill-feed row is listed, teammates' and enemies' kills included. Delete the rows that are not yours (--drop).")


if __name__ == "__main__":
    main()
