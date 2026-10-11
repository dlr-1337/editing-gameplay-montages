#!/bin/bash
# Full render: three parallel parts, then sound, then mux -> a high-quality master (crf 14).
# usage: bash run.sh master.mp4          (about 15 minutes for 46 s of 1920x1080 video on a 6-core CPU; run it in the background)
# Python: $PY, default ./venv311/Scripts/python.  ffmpeg: $FF, default found by ff.py.
set -e
PY=${PY:-./venv311/Scripts/python}
FF=${FF:-$("$PY" ff.py | tr -d '\r')}
export FF
OUT=${1:?usage: bash run.sh master.mp4}
N=$("$PY" -c "import timeline as T; print(T.N_FRAMES)" | tr -d '\r')
A=$((N/3)); B=$((2*N/3))
export CVT=${CVT:-4}
"$PY" render.py 0 $A part_0.mp4 > part_0.log 2>&1 & p0=$!
"$PY" render.py $A $B part_1.mp4 > part_1.log 2>&1 & p1=$!
"$PY" render.py $B $N part_2.mp4 > part_2.log 2>&1 & p2=$!
wait $p0; wait $p1; wait $p2          # a failed part stops the script here (see part_N.log)
printf "file 'part_0.mp4'\nfile 'part_1.mp4'\nfile 'part_2.mp4'\n" > parts.txt
"$FF" -v error -y -f concat -safe 0 -i parts.txt -c copy video.mp4
"$PY" audio.py > audio.log 2>&1
# volume=1.475: mix.wav is written at 0.8 (headroom, see audio.py), 1.475 = 1.18 / 0.8, then the limiter.
# -aac_pns 0 etc.: ffmpeg's AAC encoder otherwise overshoots the limiter by up to 3 dB on kick transients (clipping)
"$FF" -v error -y -i video.mp4 -i mix.wav -af "volume=1.475,alimiter=limit=0.82:attack=3:release=60:level=disabled" \
  -map 0:v -map 1:a -c:v copy -c:a aac -b:a 320k -aac_pns 0 -aac_tns 0 -aac_is 0 -movflags +faststart "$OUT"
echo "done $OUT"
