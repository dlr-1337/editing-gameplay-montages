#!/bin/bash
# Upload copy made from the master: same picture at a bit rate that suits TikTok / Reels / Shorts
# (about 16 Mbps, 74 MB for 37 s), sound encoded once, straight from mix.wav.
# usage: bash deliver.sh master.mp4 out.mp4          (needs mix.wav from run.sh in the current folder)
# Always encode the upload copy from the master, never from an earlier upload copy.
set -e
PY=${PY:-./venv311/Scripts/python}
FF=${FF:-$("$PY" ff.py | tr -d '\r')}
IN=${1:?usage: bash deliver.sh master.mp4 out.mp4}
OUT=${2:?usage: bash deliver.sh master.mp4 out.mp4}
[ -e "$OUT" ] && { echo "refusing to overwrite $OUT: deliver each version under a new name"; exit 1; }
"$FF" -v error -y -i "$IN" -i mix.wav -af "volume=2.36,alimiter=limit=0.82:attack=3:release=60:level=disabled" \
  -map 0:v -map 1:a -c:v libx264 -preset slow -crf 18 -maxrate 17M -bufsize 34M -g 60 \
  -x264-params "aq-mode=3:aq-strength=0.9" -pix_fmt yuv420p \
  -colorspace bt709 -color_primaries bt709 -color_trc bt709 -color_range tv \
  -c:a aac -b:a 320k -aac_pns 0 -aac_tns 0 -aac_is 0 -movflags +faststart "$OUT"
echo "done $OUT"
