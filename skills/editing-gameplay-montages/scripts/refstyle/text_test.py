"""Lyric text on a flat background: the first cue of every style in timeline.TEXT at three ages (to judge the
look and the letter reveal without footage).

usage: python text_test.py     -> text_test.jpg, one row per style; label = cue start beat and frames since it started"""
import numpy as np, cv2
import timeline as T, textfx
W, H = 1920, 1080


def fr(beat, off=0):
    n = textfx.frame_of(beat) + off
    yy = np.linspace(0, 1, H, dtype=np.float32)[:, None, None]
    xx = np.linspace(0, 1, W, dtype=np.float32)[None, :, None]
    can = np.zeros((H, W, 3), np.float32) + 0.05 + 0.25 * xx * np.array([0.9, 0.6, 0.4], np.float32) + 0.2 * yy * np.array([0.2, 0.5, 0.9], np.float32)
    textfx.draw(can, n, T.frame_beat(n))
    d = (np.clip(can, 0, 1) ** (1 / 2.2) * 255).astype(np.uint8)
    t = cv2.resize(d, (640, 360), interpolation=cv2.INTER_AREA)
    cv2.putText(t, "beat %.2f %+d" % (beat, off), (6, 20), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (255, 255, 0), 2)
    return t


assert T.TEXT, "timeline.TEXT is empty: no words to show"
rows, seen = [], set()
for a, b, w, st in T.TEXT:
    if st in seen:
        continue
    seen.add(st)
    last = max(1, int((b - a) * T.FPB) - 2)             # stay inside the cue
    rows.append([fr(a, 1), fr(a, min(4, last)), fr(a, min(20, last))])
cv2.imwrite("text_test.jpg", cv2.cvtColor(np.vstack([np.hstack(r) for r in rows]), cv2.COLOR_RGB2BGR), [cv2.IMWRITE_JPEG_QUALITY, 90])
print("text_test.jpg: %d styles (%s)" % (len(rows), ", ".join(sorted(seen))))
