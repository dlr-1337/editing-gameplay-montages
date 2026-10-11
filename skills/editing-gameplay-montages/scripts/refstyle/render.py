"""Montage renderer, reference style: horizontal 1920x1080, full-frame gameplay, lyric words, hard cuts
with a blur-in (whip / zoom burst / roll + colour split + streak lines), smooth slow motion, luma fade.

Footage comes from the sub-frame store (real frames + RIFE in-betweens). Every output frame integrates the
footage over its shutter interval (exact time sampling + real motion blur), so nothing steps.
All compositing is done in linear light.

usage: python render.py n0 n1 out.mp4            frames n0..n1-1 as video (no sound)
       python render.py n0 n1 out.jpg [step]     stills for inspection (one frame: full size; several: contact sheet)"""
import os, sys, math, glob, json, subprocess
from collections import OrderedDict
import numpy as np
import cv2
import timeline as T
import textfx
from ff import FF

W, H = 1920, 1080
SRC_W, SRC_H = 1920, 1080
SHUTTER = 0.65                       # default footage shutter, fraction of the output frame interval (takes can override)
GAMMA = 2.2
DR = 1.0 / T.FPB                     # beats per output frame
LIN = ((np.arange(256) / 255.0) ** GAMMA).astype(np.float32)
SEGS = T.SEGS
C = np.array([W / 2.0, H / 2.0])
CA0 = 0.0011                         # lens colour fringing towards the frame edges, always on (as in the reference)
ACC = {1: (0.016, 3.0, 0.28), 2: (0.026, 5.0, 0.42), 3: (0.045, 9.0, 0.80)}     # kill: zoom punch, shake px, exposure pop
BLUR_IN = 5                          # frames a blur-in lasts
if not os.path.exists("posmap.json"):
    sys.exit("posmap.json is missing: run  python posmap.py  first (it also works while prep.py is still building the store)")
POSMAP = json.load(open("posmap.json"))        # measured position of every stored sixteenth (posmap.py)
CUTF = [int(math.ceil((s["r0"] - T.R0) * T.FPB - 1e-6)) for s in SEGS]          # first output frame of every take


# ---------------------------------------------------------------- footage
class Store:
    def __init__(self, cache=40):
        self.keys, self.cache, self.max = {}, OrderedDict(), cache

    def avail(self, clip):
        """(positions in sixteenths of a frame, store keys), sorted by position. RIFE does not put a sub-frame
        where its time step says (dead zone at both ends, see rifeutil.Tween), so posmap.json (posmap.py)
        holds the measured position of every sixteenth, for the old grid and for the grid fixends.py rebuilt."""
        if clip not in self.keys:
            ks = sorted(int(os.path.basename(f)[:-4]) for f in glob.glob(f"store/{clip}/*.jpg"))
            fixed = set(POSMAP["fixed"].get(clip, []))
            pos, key = [], []
            for k in ks:
                j, s_ = divmod(k, 16)
                p = float(s_) if s_ == 0 else POSMAP["tables"]["fixed" if j in fixed else "old"][s_]
                if p >= 0:
                    pos.append(j * 16 + p)
                    key.append(k)
            o = np.argsort(pos)
            self.keys[clip] = (np.array(pos)[o], np.array(key)[o])
        return self.keys[clip]

    def frame(self, clip, key):
        k = (clip, int(key))
        if k in self.cache:
            self.cache.move_to_end(k)
            return self.cache[k]
        img = cv2.imread(f"store/{clip}/{int(key):08d}.jpg", cv2.IMREAD_COLOR)
        lin = LIN[img[:, :, ::-1]]                           # RGB, linear light, float32
        self.cache[k] = lin
        if len(self.cache) > self.max:
            self.cache.popitem(last=False)
        return lin

    def sample(self, clip, p0, p1):
        """Footage averaged over the source-frame interval [p0, p1] (box shutter over the
        piecewise-linear interpolation of the stored sub-frames)."""
        keys, names = self.avail(clip)
        P0, P1 = p0 * 16.0, p1 * 16.0
        i0 = max(0, int(np.searchsorted(keys, P0, side="right")) - 1)
        i1 = min(len(keys) - 1, int(np.searchsorted(keys, P1, side="left")))
        ks = keys[i0:i1 + 1].astype(float)
        nm = names[i0:i1 + 1]
        if len(ks) == 1:
            return self.frame(clip, nm[0])
        assert np.diff(ks).max() <= 4.75, (clip, p0, p1, "footage not in the store")
        w = np.zeros(len(ks))
        if P1 - P0 < 1e-3:
            x = min(max((P0 + P1) / 2, ks[0]), ks[-1])
            j = min(len(ks) - 2, int(np.searchsorted(ks, x, side="right")) - 1)
            f = (x - ks[j]) / (ks[j + 1] - ks[j])
            w[j], w[j + 1] = 1 - f, f
        else:
            for j in range(len(ks) - 1):
                xa, xb = ks[j], ks[j + 1]
                a, b = max(P0, xa), min(P1, xb)
                if b <= a:
                    continue
                L = xb - xa
                w[j] += ((xb - a) ** 2 - (xb - b) ** 2) / (2 * L)
                w[j + 1] += ((b - xa) ** 2 - (a - xa) ** 2) / (2 * L)
        w /= w.sum()
        acc = None
        for key, wj in zip(nm, w):
            if wj < 0.004:
                continue
            f = self.frame(clip, key)
            acc = f * np.float32(wj) if acc is None else cv2.scaleAdd(f, float(wj), acc)
        return acc


# ---------------------------------------------------------------- camera
def cam(i, u):
    """Zoom / offset (source px) / roll (deg) of the virtual camera over take i at beat u."""
    s = SEGS[i]
    vz, vx, vy = s["view"]
    if s.get("calm"):
        return vz, vx, vy, 0.0
    z = s["push"] * min(1.0, max(0.0, (u - s["r0"]) / max(1e-6, s["r1"] - s["r0"])))     # slow push-in over the take
    ox = oy = th = 0.0
    for k, lv in s["kills"]:
        d = u - k
        if 0 <= d < 2.5:
            A, amp, _ = ACC[lv]
            env = (1 - math.exp(-d / 0.03)) * math.exp(-d / 0.22)                         # damped, never random
            ox += amp * env * math.sin(2 * math.pi * 2.7 * d + 1.7 * k)
            oy += 0.7 * amp * env * math.cos(2 * math.pi * 3.3 * d + 2.3 * k)
            th += 0.05 * amp * env * math.sin(2 * math.pi * 2.2 * d + k)
            z += A * T.punch(d, 0.05, 0.35)
    return vz * (1.0 + z), vx + ox, vy + oy, th


def look(i, r):
    """Exposure pop and extra colour fringing from the kills of take i."""
    expo, ca = 1.0, CA0
    for k, lv in SEGS[i]["kills"]:
        d = r - k
        if d >= -0.02:
            d = max(d, 0.0)
            expo += ACC[lv][2] * math.exp(-d / 0.10)
            ca += (0.0025, 0.0035, 0.006)[lv - 1] * math.exp(-d / 0.25)
    return expo, ca


def rot(deg):
    c, s = math.cos(math.radians(deg)), math.sin(math.radians(deg))
    return np.array([[c, -s], [s, c]])


def warp(S, z, ox, oy, th, ca):
    """Source image -> canvas. Colour fringing by per-channel zoom (grows towards the edges)."""
    R = rot(th)
    sc = np.array([SRC_W / 2 + ox, SRC_H / 2 + oy])
    chans = []
    for ci, dz in enumerate((1 + ca, 1.0, 1 - ca)):
        A = (1.0 / (z * dz)) * R
        M = np.hstack([A, (sc - A @ C)[:, None]]).astype(np.float64)
        chans.append(cv2.warpAffine(S[:, :, ci], M, (W, H), flags=cv2.INTER_CUBIC | cv2.WARP_INVERSE_MAP,
                                    borderMode=cv2.BORDER_REFLECT_101))
    return cv2.merge(chans)


def affine(img, zoom=1.0, deg=0.0, dx=0.0, dy=0.0, interp=cv2.INTER_LINEAR):
    """Zoom / rotate about the centre and shift a finished frame (reflecting borders)."""
    A = rot(deg) / zoom
    M = np.hstack([A, (C - A @ (C + np.array([dx, dy])))[:, None]]).astype(np.float64)
    return cv2.warpAffine(img, M, (W, H), flags=interp | cv2.WARP_INVERSE_MAP, borderMode=cv2.BORDER_REFLECT_101)


def split_rgb(img, px):
    """Red and blue pushed apart horizontally by px pixels."""
    px = int(round(px))
    if px < 1:
        return img
    out = img.copy()
    out[:, px:, 0] = img[:, :-px, 0]
    out[:, :-px, 2] = img[:, px:, 2]
    return out


def blur_in(img, kind, q, seed):
    """The first frames after a cut: the new clip arrives through a whip, a zoom burst or a roll.
    q = frames since the cut. Works on the finished frame, so the lyric word blurs with the footage."""
    w = (1.0 - q / float(BLUR_IN)) ** 2
    if kind[0] == "bwhip":
        d = kind[2]
        L = int(260 * w) | 1
        img = affine(img, 1.0 + 0.05 * w, 0.0, d * 330 * w ** 1.25, 0.0)
        if L > 2:
            img = cv2.blur(img, (L, 1), borderType=cv2.BORDER_REFLECT_101)
        img = split_rgb(img, 20 * w)
    elif kind[0] == "bzoom":
        n = 14 if w > 0.05 else 1
        acc = np.zeros_like(img)
        for j in range(n):
            acc += affine(img, 1.0 + 0.22 * w + 0.30 * w * (j / max(1, n - 1)))
        img = acc * np.float32(1.0 / n)
        r, g, b = cv2.split(img)
        img = cv2.merge([affine(r, 1 + 0.016 * w), g, affine(b, 1 - 0.016 * w)])
    elif kind[0] == "broll":
        d = kind[2]
        n = 12 if w > 0.05 else 1
        acc = np.zeros_like(img)
        for j in range(n):
            acc += affine(img, 1.0 + 0.32 * w, d * (10.0 * w + 3.0 * w * (j / max(1, n - 1) - 0.5)))
        img = acc * np.float32(1.0 / n)
        L = int(70 * w) | 1
        if L > 2:
            img = cv2.blur(img, (L, 1), borderType=cv2.BORDER_REFLECT_101)
        img = split_rgb(img, 14 * w)
    return img


def streaks(img, kind, q, seed):
    """Thin light streaks left behind by the transition; they linger a few frames while fading."""
    life = 9.0
    if q >= life or kind[0] not in ("bwhip", "bzoom"):
        return img
    a = (1.0 - q / life) ** 1.6
    rng = np.random.default_rng(seed)
    lay = np.zeros((H, W), np.float32)
    if kind[0] == "bwhip":
        d = kind[2]
        for _ in range(7):
            y = int(rng.uniform(0.08, 0.92) * H)
            ln = rng.uniform(260, 900)
            x = rng.uniform(-200, W) - d * (q * rng.uniform(90, 170))
            cv2.line(lay, (int(x), y), (int(x + ln), y), float(rng.uniform(0.5, 1.0)), 1 if rng.random() < 0.6 else 2, cv2.LINE_AA)
        lay = cv2.blur(lay, (41, 1))
    else:
        for _ in range(11):
            ang = rng.uniform(0, 2 * math.pi)
            r0 = rng.uniform(140, 320) + q * 26
            r1 = r0 + rng.uniform(220, 620)
            p0 = (int(W / 2 + r0 * math.cos(ang)), int(H / 2 + r0 * math.sin(ang)))
            p1 = (int(W / 2 + r1 * math.cos(ang)), int(H / 2 + r1 * math.sin(ang)))
            cv2.line(lay, p0, p1, float(rng.uniform(0.45, 1.0)), 1 if rng.random() < 0.7 else 2, cv2.LINE_AA)
        lay = cv2.GaussianBlur(lay, (0, 0), 0.8)
    img += lay[:, :, None] * (np.array([0.85, 0.97, 1.0], np.float32) * np.float32(0.62 * a))
    return img


# ---------------------------------------------------------------- finishing
yy, xx = np.mgrid[0:H, 0:W].astype(np.float32)
_v = np.clip(((xx - W / 2) / (W * 0.74)) ** 2 + ((yy - H / 2) / (H * 0.80)) ** 2, 0, 1) ** 1.3
VIG = (1.0 - 0.20 * _v)[:, :, None].astype(np.float32)
VIG_INTRO = (1.0 - 0.46 * _v)[:, :, None].astype(np.float32)
del yy, xx, _v
_x = np.linspace(0, 1, 4096)
_g = _x ** (1 / GAMMA)
_g = np.clip(_g + 0.040 * np.sin(2 * math.pi * (_g - 0.5)), 0, 1)             # S-curve: deeper shadows, brighter highlights
OUT_LUT = (_g * 255).astype(np.float32)
_rng = np.random.default_rng(11)
NOISE = [_rng.uniform(-0.5, 0.5, (H, W)).astype(np.float32)[:, :, None] for _ in range(8)]


def render_frame(n, store):
    r = T.frame_beat(n)
    i = T.active(r)[0]
    s = SEGS[i]
    h = s["shutter"] * DR / 2
    mp = s["map"]
    S = store.sample(s["clip"], float(mp(r - h)[0]), float(mp(r + h)[0]))
    z, ox, oy, th = cam(i, r)
    expo, ca = look(i, r)
    img = warp(S, z, ox, oy, th, ca)
    if expo != 1.0:
        img *= np.float32(expo)
    if s["intro"]:
        img *= np.float32(0.90)
    np.maximum(img, 0, out=img)

    textfx.draw(img, n, r)                                             # lyric words (under the transition blur)

    q = n - CUTF[i]                                                    # frames since this take came in
    kind = s["tin"]
    if kind[0] in ("bwhip", "bzoom", "broll"):
        if q < BLUR_IN:
            img = blur_in(img, kind, q, i)
        img = streaks(img, kind, q, 7 + i)
    if i + 1 < len(SEGS) and not s["intro"]:                          # the last 2 frames before a cut lean into it (not in the calm intro)
        left = CUTF[i + 1] - n
        if left in (1, 2):
            e = 0.085 if left == 1 else 0.035
            acc = np.zeros_like(img)
            for j in range(6):
                acc += affine(img, 1.0 + e * j / 5.0)
            img = split_rgb(acc * np.float32(1 / 6.0), 5 if left == 1 else 2)

    # bloom, saturation, vignette
    small = cv2.resize(img, (W // 8, H // 8), interpolation=cv2.INTER_AREA)
    bloom = cv2.GaussianBlur(np.maximum(small - 0.60, 0), (0, 0), 7)
    img += cv2.resize(bloom, (W, H), interpolation=cv2.INTER_LINEAR) * np.float32(0.16 if s["intro"] else 0.09)
    lum = (0.2126 * img[:, :, 0] + 0.7152 * img[:, :, 1] + 0.0722 * img[:, :, 2])[:, :, None]
    img = lum + (img - lum) * np.float32(1.10 if s["intro"] else 1.20)
    img *= VIG_INTRO if s["intro"] else VIG
    if s["tin"][0] == "fade" and r < s["r0"] + 0.9:                    # the video opens from black
        img *= np.float32(T.ease((r - s["r0"]) / 0.9) ** GAMMA)
    idx = np.clip(img * 4095.0, 0, 4095).astype(np.uint16)
    disp = OUT_LUT[idx]
    # ending: luma fade (dark areas go black first, the bright HUD last), as in the reference
    lf = (r - T.LUMA_FADE[0]) / (T.LUMA_FADE[1] - T.LUMA_FADE[0])
    if lf > 0:
        if lf >= 1:
            return np.zeros((H, W, 3), np.uint8)
        t = T.ease(lf)
        disp = (disp - np.float32(255.0 * 1.04 * t)) * np.float32(1.0 - 0.35 * t)
    disp += NOISE[(n * 7) % len(NOISE)]
    return np.clip(disp + 0.5, 0, 255).astype(np.uint8)


def encoder(path):
    return subprocess.Popen(
        [FF, "-v", "error", "-y", "-f", "rawvideo", "-pix_fmt", "rgb24", "-s", f"{W}x{H}", "-r", str(T.FPS), "-i", "-",
         "-vf", "unsharp=5:5:0.55:5:5:0.0,scale=out_color_matrix=bt709:out_range=tv,format=yuv420p",
         "-c:v", "libx264", "-preset", "slow", "-crf", "14", "-g", "60", "-x264-params", "aq-mode=3:aq-strength=0.9", "-colorspace", "bt709", "-color_primaries", "bt709",
         "-color_trc", "bt709", "-color_range", "tv", path], stdin=subprocess.PIPE)


if __name__ == "__main__":
    n0, n1, out = int(sys.argv[1]), int(sys.argv[2]), sys.argv[3]
    cv2.setNumThreads(int(os.environ.get("CVT", "4")))
    store = Store()
    if out.endswith(".jpg") or out.endswith(".png"):              # still(s) for inspection
        step = int(sys.argv[4]) if len(sys.argv) > 4 else 1
        ns = list(range(n0, n1, step))
        frames = [render_frame(n, store) for n in ns]
        if len(frames) == 1:
            sheet = frames[0]
        else:
            cols = min(len(frames), 6)
            rows = (len(frames) + cols - 1) // cols
            tw, th_ = 480, 270
            sheet = np.zeros((rows * th_, cols * tw, 3), np.uint8)
            for q, f in enumerate(frames):
                t = cv2.resize(f, (tw, th_), interpolation=cv2.INTER_AREA)
                cv2.rectangle(t, (0, 0), (150, 20), (0, 0, 0), -1)
                cv2.putText(t, "%d b%.2f" % (ns[q], T.frame_beat(ns[q])), (3, 15), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (255, 255, 0), 1)
                sheet[(q // cols) * th_:(q // cols + 1) * th_, (q % cols) * tw:(q % cols + 1) * tw] = t
        cv2.imwrite(out, cv2.cvtColor(sheet, cv2.COLOR_RGB2BGR), [cv2.IMWRITE_JPEG_QUALITY, 90])
    else:
        enc = encoder(out)
        for n in range(n0, n1):
            enc.stdin.write(render_frame(n, store).tobytes())
            if (n - n0) % 100 == 0:
                print(f"{out}: frame {n} ({n - n0}/{n1 - n0})", flush=True)
        enc.stdin.close()
        enc.wait()
        print("done", out, flush=True)
