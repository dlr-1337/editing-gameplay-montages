"""Word-level transcription of the song (Portuguese) with faster-whisper.

usage: transcribe.py <audio> <out.json> [model] [t_end]
"""
import json
import sys

from faster_whisper import WhisperModel

src, out = sys.argv[1], sys.argv[2]
model_name = sys.argv[3] if len(sys.argv) > 3 else "large-v3"
t_end = float(sys.argv[4]) if len(sys.argv) > 4 else None

LANG = "pt"                                   # set per song
PROMPT = ""                                   # set per song, e.g. "Letra de trap brasileiro: <artista> - <música>."
model = WhisperModel(model_name, device="cpu", compute_type="int8", cpu_threads=10)
kw = dict(language=LANG, beam_size=5, word_timestamps=True, vad_filter=False,
          condition_on_previous_text=True, temperature=[0.0, 0.2, 0.4],
          initial_prompt=PROMPT or None)
if t_end:
    kw["clip_timestamps"] = [0.0, t_end]
# decode with ffmpeg ourselves (the bundled PyAV loader is incompatible with this faster-whisper)
import subprocess  # noqa: E402

import numpy as np  # noqa: E402

from ff import FF  # noqa: E402

raw = subprocess.run([FF, "-v", "error", "-i", src, "-map", "0:a:0", "-ac", "1", "-ar", "16000",
                      "-f", "f32le", "-"], capture_output=True).stdout
audio = np.frombuffer(raw, np.float32)
segments, info = model.transcribe(audio, **kw)
res = []
for s in segments:
    words = [{"w": w.word, "s": round(w.start, 3), "e": round(w.end, 3), "p": round(w.probability, 3)}
             for w in (s.words or [])]
    res.append({"s": round(s.start, 3), "e": round(s.end, 3), "text": s.text, "words": words,
                "avg_logprob": round(s.avg_logprob, 3), "no_speech": round(s.no_speech_prob, 3)})
    print(f"[{s.start:7.2f} - {s.end:7.2f}] {s.text}", flush=True)
json.dump(res, open(out, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
print("saved", out)
