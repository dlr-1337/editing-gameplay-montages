"""Sound for the reference-style edit: the track, one gunshot per kill at natural pitch with its onset on the
beat (the takes are fast-forward or slow motion almost all the time, so the game sound does not follow the
time maps here), and the synthesised risers (T.RISERS).

usage: python audio.py      -> mix.wav (written at 0.8: run.sh makes it up) + stems; prints each kill's gunshot
                               offset and how it was found, then how many shots were placed on their own measured
                               onset, how many with the clip's usual offset, and which kills have no gunshot"""
import os, subprocess, sys, wave
import numpy as np
import timeline as T
import clipio
from ff import FF

SR = 48000
DUR = (T.R1 - T.R0) * T.PER
NS = int(round(DUR * SR))
tt = np.arange(NS) / SR
rr = T.R0 + tt / T.PER                      # beat position of every output sample


def decode(path):
    raw = subprocess.run([FF, "-v", "error", "-i", path, "-map", "0:a:0", "-ac", "2", "-ar", str(SR), "-f", "f32le", "-"],
                         capture_output=True).stdout
    assert len(raw), f"no sound decoded from {path}: is the file there? (python ingest.py creates src/)"
    return np.frombuffer(raw, np.float32).reshape(-1, 2)


def lowpass(x, fc, order=4):
    """Zero-phase Butterworth-shaped low-pass via FFT."""
    X = np.fft.rfft(x, axis=0)
    f = np.fft.rfftfreq(len(x), 1 / SR)
    return np.fft.irfft(X / np.sqrt(1 + (f / fc) ** (2 * order))[:, None], n=len(x), axis=0).astype(np.float32)


def highpass(x, fc, order=2):
    X = np.fft.rfft(x, axis=0)
    f = np.fft.rfftfreq(len(x), 1 / SR)
    g = (f / fc) ** order
    return np.fft.irfft(X * (g / np.sqrt(1 + g * g))[:, None], n=len(x), axis=0).astype(np.float32)


def smooth(x):
    x = np.clip(x, 0, 1)
    return x * x * (3 - 2 * x)


# ---------------------------------------------------------------- music
def music():
    m = decode(T.MUSIC)
    a = int(round(T.MUSIC_T0 * SR))
    y = m[a:a + NS].copy()
    if T.SWEEP:
        # close a low-pass over the music along T.SWEEP = [(beat, cutoff Hz), ...] and snap it open 4 ms before
        # the last point (in the v4 edit: through the bullet time, opening on the last kill)
        sb, sf = [q[0] for q in T.SWEEP], [q[1] for q in T.SWEEP]
        b0, b1 = np.searchsorted(rr, sb[0]), np.searchsorted(rr, sb[-1]) - int(0.004 * SR)
        pad = SR // 2
        ya, yb = max(0, b0 - pad), min(NS, b1 + pad)
        seg = y[ya:yb]
        cut = slice(b0 - ya, b1 - ya)
        r = rr[b0:b1]
        logfc = np.interp(r, sb, np.log2(sf))
        grid = np.log2([18000, 9000, 4500, 2400, 1400, 900, 620])      # cutoffs outside 620 Hz .. 18 kHz are clamped
        vers = [seg[cut]] + [lowpass(seg, 2 ** g)[cut] for g in grid[1:]]
        out = np.zeros_like(vers[0])
        pos = np.interp(logfc, grid[::-1], np.arange(len(grid))[::-1])
        for j in range(len(grid)):
            w = np.clip(1 - np.abs(pos - j), 0, 1).astype(np.float32)
            out += vers[j] * w[:, None]
        xf = int(0.003 * SR)
        out[-xf:] = out[-xf:] * np.linspace(1, 0, xf)[:, None] + y[b1 - xf:b1] * np.linspace(0, 1, xf)[:, None]
        y[b0:b1] = out
    fi = int(0.05 * SR)
    y[:fi] *= np.linspace(0, 1, fi)[:, None]
    y *= (1 - smooth((rr - T.FADE_OUT[0]) / (T.FADE_OUT[1] - T.FADE_OUT[0] - 0.05)))[:, None].astype(np.float32)
    return y


# ---------------------------------------------------------------- game sound
def wsola(x, pos, win=1440, tol=480):
    """Pitch-preserving time stretch (waveform-similarity overlap-add).
    x: (N, 2) source; pos: wanted source position (in samples) for every output sample."""
    hop = win // 2
    n_out = len(pos)
    pad = win + tol + 8
    xp = np.vstack([np.zeros((pad, 2), np.float32), x, np.zeros((pad, 2), np.float32)])
    mono = xp.mean(1)
    w = np.hanning(win + 1)[:win].astype(np.float32)        # periodic Hann: overlaps add up to 1
    out = np.zeros((n_out + 2 * win, 2), np.float32)
    prev = None
    for m in range(0, n_out + hop, hop):
        ideal = int(round(float(pos[min(m, n_out - 1)]))) + pad - hop
        if prev is None or abs(ideal - (prev + hop)) <= 2:
            start = ideal if prev is None else prev + hop   # real time: plain continuation, bit-exact
        else:
            target = mono[prev + hop: prev + hop + win]     # how the sound would naturally continue
            lo = ideal - tol
            region = mono[lo: lo + 2 * tol + win]
            c = np.correlate(region, target, mode="valid")
            cs = np.concatenate([[0.0], np.cumsum(region.astype(np.float64) ** 2)])
            en = np.sqrt(cs[win:] - cs[:-win]) + 1e-6
            start = lo + int(np.argmax(c / en[: len(c)]))
        out[m: m + win] += xp[start: start + win] * w[:, None]
        prev = start
    return out[hop: hop + n_out]


def game():
    """Reference-style edit: the takes run in fast-forward or slow motion almost all the time, so the game sound is
    not stretched along with the picture. Every kill gets its own gunshot at natural pitch, cut from the clip and
    placed so that its onset lands exactly on the beat. A kill whose clip has no clean gunshot stays silent
    (voice chat or other loud sound over it): the music hit carries it."""
    buf = np.zeros((NS, 2), np.float32)
    clips, report, pending, state = {}, [], [], {}
    n = 100                                              # 2.08 ms bins = 8 per source frame
    for i, s in enumerate(T.SEGS):
        c = s["clip"]
        for k, lv in s["kills"]:
            report.append((k, c))
            if s.get("mute"):
                state[(k, c)] = "muted"
                continue
            if c not in clips:
                clips[c] = decode(clipio.path(c))
            mono = clips[c].mean(1)
            K = float(s["map"](k)[0])
            a = int(clipio.n2t(c, K - 2) * SR)
            hp = np.diff(mono[a - 1:a + 64 * n + 1])[:64 * n]
            e = np.sqrt((hp.reshape(-1, n) ** 2).mean(1)) + 1e-7     # frames K-2 .. K+6
            best, bj = 0.0, None
            for j in range(14, 46):                      # K-0.25 .. K+3.75 frames
                rise = 20 * np.log10(e[j] / e[j - 6:j].mean())
                if rise > best and e[j] > 0.25 * e.max():
                    best, bj = rise, j
            pending.append((k, lv, c, K, (bj / 8.0 - 2.0) if bj is not None else None, best))
    med = {}                                             # per clip: the sound-to-picture offset of its clearly measured shots
    for c in set(p[2] for p in pending):
        v = [p[4] for p in pending if p[2] == c and p[4] is not None and p[5] >= 10.0]
        if v:
            med[c] = float(np.median(v))
    pre_s, sus, rel = 0.008, 0.19, 0.16
    L = int((pre_s + sus + rel) * SR)
    env = np.ones(L, np.float32)
    fi, ro = int(0.006 * SR), int(rel * SR)
    env[:fi] = np.linspace(0, 1, fi) ** 2
    env[-ro:] = 0.5 + 0.5 * np.cos(np.linspace(0, np.pi, ro))
    for k, lv, c, K, lag, rise in pending:
        how = "measured (+%.0f dB)" % rise
        ok = lag is not None and rise >= 8.0 and (c not in med or abs(lag - med[c]) <= 1.0)
        if not ok:
            if c not in med:
                print("  kill beat %5.1f %s: no clean gunshot -> silent" % (k, c))
                state[(k, c)] = "silent"
                continue
            lag, how = med[c], "clip offset"
        x = clips[c]
        a = int(round((float(clipio.n2t(c, K + lag)) - pre_s) * SR))
        seg = x[a:a + L].astype(np.float32) * env[:, None]
        g = min(2.5, max(0.5, 0.55 / (float(np.abs(seg).max()) + 1e-6))) * (1.25 if lv == 3 else 1.0)
        d = int(round((k - T.R0) * T.PER * SR)) - int(pre_s * SR)
        s0, s1 = max(0, d), min(NS, d + L)
        buf[s0:s1] += seg[s0 - d:s1 - d] * np.float32(g)
        print("  kill beat %5.1f %s: gunshot onset K%+.2f frames, %s, gain %.2f" % (k, c, lag, how, g))
        state[(k, c)] = "clip offset" if how == "clip offset" else "measured"
    buf = highpass(buf, 70.0)
    return buf, [(k, c, state[(k, c)]) for k, c in report]


# ---------------------------------------------------------------- synthesised effects
def noise_sweep(dur, fc_of_x, width_oct, seed):
    """Stereo noise whose band centre follows fc_of_x(x), x in 0..1 (STFT shaping, overlap-add)."""
    n = int(dur * SR)
    N, Hh = 2048, 512
    rng = np.random.default_rng(seed)
    win = np.sqrt(np.hanning(N + 1)[:N]).astype(np.float32)
    f = np.fft.rfftfreq(N, 1 / SR)
    lf = np.log2(np.maximum(f, 20.0))
    out = np.zeros((n + 2 * N, 2), np.float32)
    for ch in range(2):
        w = rng.standard_normal(n + 2 * N).astype(np.float32)
        for st in range(0, n + N, Hh):
            x = min(1.0, max(0.0, (st + N / 2 - N) / n))
            mask = np.exp(-0.5 * ((lf - math_log2(fc_of_x(x))) / width_oct) ** 2)
            out[st:st + N, ch] += np.fft.irfft(np.fft.rfft(w[st:st + N] * win) * mask, n=N).astype(np.float32) * win
    y = out[N:N + n]
    return y / (np.abs(y).max() + 1e-9)


def math_log2(v):
    return float(np.log2(v))


def place(buf, y, beat_end=None, beat_center=None):
    n = len(y)
    if beat_end is not None:
        a = int(round((beat_end - T.R0) * T.PER * SR)) - n
    else:
        a = int(round((beat_center - T.R0) * T.PER * SR)) - n // 2
    s0, s1 = max(0, a), min(NS, a + n)
    buf[s0:s1] += y[s0 - a:s1 - a]


def sfx():
    buf = np.zeros((NS, 2), np.float32)
    # risers: filtered noise that climbs in pitch and level and stops dead on a beat
    # (in the v4 edit: through the breakdown into the drop, and through the bullet time into the last kill)
    for q in T.RISERS:
        d = (q["b"] - q["a"]) * T.PER
        x = np.linspace(0, 1, int(d * SR))
        y = noise_sweep(d, lambda u, q=q: q["f0"] * (q["f1"] / q["f0"]) ** (u ** q["curve"]), q["width"], q["seed"])
        env = x ** q["power"]
        nc = int(q["cut"] * SR)
        env[-nc:] *= np.linspace(1, 0, nc)
        place(buf, y * (q["gain"] * env)[:, None].astype(np.float32), beat_end=q["b"])
    # whooshes on the clip changes
    for j, s in enumerate(T.SEGS):
        kind = s["tin"][0]
        if kind not in ("whip", "spin", "zoom"):
            continue
        d = 0.44
        x = np.linspace(0, 1, int(d * SR))
        y = noise_sweep(d, lambda q: 700 * (3400 / 700) ** (1 - abs(2 * q - 1.1) ** 1.5 if abs(2 * q - 1.1) < 1 else 0), 0.9, 10 + j)
        env = np.sin(np.pi * x) ** 2.2
        y = y * (0.085 * env)[:, None]
        if kind == "whip" and s["tin"][2][0] != 0:          # pan with the direction of the move
            pan = 0.5 + 0.38 * s["tin"][2][0] * (1 - 2 * x)
            y = np.stack([y[:, 0] * np.sqrt(1 - pan) * 1.41, y[:, 1] * np.sqrt(pan) * 1.41], 1)
        place(buf, y.astype(np.float32), beat_center=s["r0"])
    return buf


if __name__ == "__main__":
    m = music()
    g, rep = game()
    fx = sfx()
    mix = (0.84 * m + 0.60 * g + fx) * 0.8          # 0.8: headroom, the resampled track peaks above 1.0 (run.sh makes it up before the limiter)
    for name, x in (("stem_music", m), ("stem_game", g), ("stem_sfx", fx), ("mix", mix)):
        with wave.open(f"{name}.wav", "wb") as w:
            w.setnchannels(2); w.setsampwidth(2); w.setframerate(SR)
            w.writeframes((np.clip(x, -1, 1) * 32767).astype(np.int16).tobytes())
    print("mix peak %.3f  rms %.3f | music peak %.3f | game peak %.3f rms %.3f | sfx peak %.3f" % (
        np.abs(mix).max(), np.sqrt((mix ** 2).mean()), np.abs(m).max(), np.abs(g).max(), np.sqrt((g ** 2).mean()), np.abs(fx).max()))
    assert np.abs(mix).max() <= 1.0, "the mix exceeds full scale even at 0.8 (it would clip before the limiter): lower the levels"
    # How sure is each gunshot? A placed shot has its onset on the beat by construction; what can be wrong is the onset
    # that was found. (Measuring the finished stem tells nothing here: every shot fades in from silence 8 ms before its
    # onset, and shots less than a beat apart overlap.)
    n = {st: sum(1 for q in rep if q[2] == st) for st in ("measured", "clip offset", "muted", "silent")}
    print("gunshots: %d placed on their own measured onset; %d placed with their clip's usual offset because the shot itself does "
          "not stand out (can sit a frame or two off: not verified); %d kills without a gunshot (%d mute=True, %d not found)"
          % (n["measured"], n["clip offset"], n["muted"] + n["silent"], n["muted"], n["silent"]))
    for st, label in (("clip offset", "placed with the clip offset"), ("muted", "no gunshot, mute=True"), ("silent", "no gunshot, none found")):
        ks = ["%g %s" % (k, c) for k, c, q in rep if q == st]
        if ks:
            print("  %s: %s" % (label, ", ".join(ks)))
