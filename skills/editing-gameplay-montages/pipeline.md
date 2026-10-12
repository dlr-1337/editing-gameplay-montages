# Pipeline reference

Everything runs from one project folder with the scripts copied into it (they import each other and
`timeline.py` from the current directory). Shell: Git Bash (the Bash tool). `PY=./venv311/Scripts/python`.
Each Bash call is a fresh shell: start every command with `cd "$P" && PY=./venv311/Scripts/python &&`
(written out, since `$P` is gone too). If a shell refuses the relative path ("command not found"), use the
absolute one, `PY="$PWD/venv311/Scripts/python.exe"`, and export it: `run.sh` and `deliver.sh` read `$PY`.

## Project layout

```
<project>/
  clips.json            short name -> original file            you write it
  src/                  c1.mp4 / c1.mkv ... music.flac          ingest.py (links, or converted working copies)
  src/ingest.json       per clip: original size, fps, method     ingest.py
  pts/c1.csv ...        presentation time of every frame        mkpts.py
  banners.json          banner frame of every kill              you, from find_kills.py
  kills.json            kill frame K (+ feed frame, confidence)  kills_auto.py (Valorant alternatives: kill_table.py, mykills.py; each rewrites it)
  timeline.py           THE EDIT                                you, from timeline_example.py
  ranges.json           footage the edit needs                  ranges.py
  store/<clip>/<key>.jpg  real frames + in-betweens             prep.py, densify.py, repair.py
  models/rife-v4.25/    interpolation network                   copied from the skill
  venv311/              Python 3.11                             uv
  part_N.mp4, video.mp4, mix.wav, stem_*.wav, master.mp4        run.sh
```

Where to put it: next to the user's clips as `<clips folder>/_editor/` (same drive, so `src/` costs no
space, and the project survives the session). If that folder already holds another video's project,
use `_editor_<name>/`; never mix two videos in one project folder. `store/` takes 0.4 MB per sub-frame: about 7 GB for a
37 s edit. Tell the user it is there and that it can be deleted (it rebuilds in about 30 minutes).
`src/` holds hard links for sources already in the working format: while they exist, deleting the original
clips frees no disk space. Say so in the report and in `LEIAME.md`; do not remove `src/` yourself (once the
user has deleted an original, the link is the last copy of that clip). `ingest.py` recreates the links
instantly while the originals exist. A converted working copy (`.mkv`, x264 crf 9 + FLAC) is a new, large
file: put its size in the disk report.

The numbers in this skill come from two delivered projects (not included: they hold the author's footage):
- house style: v4, vertical, 37 s, 22 kills (`scripts/timeline_example.py` is its timeline);
- reference style: v3, horizontal, lyric words, 46 s, 62 kills (`scripts/refstyle/timeline_ref_example.py`). Its extra files:
  `detections.json`, `detect/`, `kills.json`, `lyric_cues.json`, `lyrics_whisper.json`, `posmap.json`, `cover/`.

## Setup

```bash
SK=~/.claude/skills/editing-gameplay-montages
P="/c/Users/<you>/Videos/<clips folder>/_editor"    # one project folder per video (_editor_<name> if _editor is taken)
mkdir -p "$P" && cd "$P"
cp "$SK"/scripts/*.* . && cp -r "$SK"/scripts/games "$SK"/models . && cp timeline_example.py timeline.py     # *.* = files only (a bare * also hits the refstyle folder and cp fails); games/ = kill-finder profiles
# reference style, in addition (its render.py, audio.py, check.py, clipio.py, densify.py, run.sh, deliver.sh replace the
# house ones on purpose: one project folder is one style; a second style for the same clips = a second _editor_<name>/):
#   cp "$SK"/scripts/refstyle/*.* . && cp timeline_ref_example.py timeline.py
uv venv --python 3.11 venv311                       # 3.11: the RIFE binding has no wheels for 3.14
uv pip install --python venv311/Scripts/python.exe -r requirements.txt
PY=./venv311/Scripts/python
# lyric words only: speech recognition in its own environment, not venv311. Tested with Python 3.14 and
# faster-whisper 1.2.1 (in a venv outside the project; the project-folder form below was not run exactly as written):
# large-v3 on the CPU takes about 4 min per minute of song, and its 3 GB download happens on first use.
#   uv venv --python 3.14 venv_asr && uv pip install --python venv_asr/Scripts/python.exe faster-whisper numpy
#   ./venv_asr/Scripts/python transcribe.py src/music.flac lyrics_whisper.json large-v3 <t_end seconds>
```

`clips.json` (forward slashes; written with PowerShell it gets a BOM, which the scripts accept):

```json
{"c1": "C:/Users/<you>/Videos/valorant/4k TOPPP.mp4",
 "music": "C:/Users/<you>/Videos/valorant/01 - Artist - Song.flac"}
```

`$PY ingest.py && $PY mkpts.py`. `ingest.py` brings every source into the working format that everything
downstream assumes: 1920x1080, 60 fps constant, frame n at t0 + n/60 on the original clock. A source already
in that format (1920x1080, the recorder's rate within 0.5 fps of 60) is hard-linked untouched, and so is a
1080p60 recording with dropped frames: its frame indices stay the original's (the Valorant raw-recording tools
rely on that), `mkpts.py` lists the gaps and `clipio.py` follows the real time table across them. Anything
else (1440p, 4K, 720p, 4:3 stretched, 21:9, 120 / 144 / 165 / 240 fps, 30 fps, variable frame rate) becomes a
converted `src/<name>.mkv`; the Valorant raw-recording tools read the original file, so for a converted clip find
the kills with `kills_auto.py`, which reads `src/`:

- Size: narrower than 16:9 (4:3, 16:10: CS2 "stretched") is stretched to 16:9, which is what the player saw;
  wider (21:9, 32:9) is cropped at the centre; `--aspect stretch|crop|pad` overrides.
- Time: a source frame within 1.5 ms of the wanted instant is used unchanged (120 / 240 fps are exact picks).
  Otherwise `--exact` (default for clips up to 90 s) interpolates the two frames around the instant with RIFE
  at the exact fraction; `--fast` (default for longer raw recordings) takes the nearest frame, at most half a
  source frame off (3.5 ms at 144 fps). Below 60 fps it always interpolates: a repeated frame is a stutter.
  Once the timeline uses a `fast` clip, upgrade it with `$PY ingest.py --exact --only c3`, delete `store/c3`
  and run `mkpts.py`, `prep.py` and `densify.py` again: the frame grid is the same, so K values and anchors stay.
- Sound: the clip's audio as FLAC, aligned so that frame n and its sound belong together (measured: 0.000 ms
  offset on a forced conversion, and with audio starting 0.35 s after or 0.3 s before the video).

Measured on a GTX 1650 against a real 1080p60 recording: forced conversion of the same clip 41 to 45 dB per
frame (x264 rounding only); 120 fps source, 0 interpolations; 144 fps and 2560x1440 built from 60 fps,
motion evenness as the original (no repeated frame, no extra jumps); 30 fps: no repeated frame, but every
other frame is invented (25.9 dB on average against a real 60 fps recording, weak on fast flicks), so ask for
60 fps or more. Speed: 48 frames per second when frames are only picked, about 10 with `--exact` on 144 fps.

`mkpts.py` then reports frame rate, jitter and gaps of the working copies (gaps: frames the recorder dropped).

ffmpeg is found by `ff.py`: `$FF`, then PATH, then the winget install
(`%LOCALAPPDATA%\Microsoft\WinGet\Packages\Gyan.FFmpeg*`). Install with `winget install Gyan.FFmpeg`;
a shell opened before the install does not have it on PATH, which is why `ff.py` looks it up.

Machine these numbers come from: Windows 11, Ryzen 5 5500 (6 cores), 16 GB RAM, GTX 1650 4 GB.

Two settings that depend on the PC:
- GPU index: `rifeutil.load()` uses Vulkan device `RIFE_GPU` (environment variable, default 0). On a PC with two GPUs
  (integrated and dedicated) the dedicated one may not be 0: `export RIFE_GPU=1` before `prep.py` / `densify.py`, and
  check with the GPU command under "Handling jobs on this PC" that the 3D load is on the dedicated GPU.
- CPU threads: `render.py` gives OpenCV `CVT` threads (environment variable, default 4) in each of the three
  processes `run.sh` starts (both styles): `CVT=2 bash run.sh master.mp4` on a 4-core CPU.
- Lyric font (reference style): `textfx.py` uses Impact from the Windows font folder, or `IMPACT_FONT` (path to a
  .ttf); it stops with that message when the font is missing.

## Scripts

| Script | What it does | Call |
|---|---|---|
| `ingest.py` | working copies in `src/` (any size and frame rate -> 1920x1080 60 fps), `src/ingest.json` | `$PY ingest.py`, `--only c3 --exact` to upgrade a `fast` clip |
| `mkpts.py` | frame time tables, source warnings | `$PY mkpts.py` |
| `peek.py` | contact sheet of real frames (how you watch a clip) | `$PY peek.py c3 0 1320 30` overview, `$PY peek.py c3 268 300` every frame |
| `kills_auto.py` | ANY game: kill-feed rows -> shot frame K (gunshot in the audio, muzzle flash, ammo counter) -> `kills.json` + review sheets `autokill_NN.jpg`; profiles in `games/` (`valorant`, `cs2` not yet checked on footage, `generic`) | `$PY kills_auto.py valorant`, `$PY kills_auto.py cs2 c1 c3`, `$PY kills_auto.py cs2 --regions c1 1500` to check a profile's rectangles on a frame |
| `find_kills.py` | kill-banner sheets + candidate frames (Valorant HUD) | `$PY find_kills.py c3` or `c1 82 97` (seconds) |
| `kill_table.py` | per kill: frame K for the beat, gunshot, lag, gallery | `$PY kill_table.py` (reads `banners.json`; an entry `[banner, K]` fixes K by hand) |
| `cadence.py` | duplicated frames / real pauses in a source clip | `$PY cadence.py c1 5290 5725`, add `--detail` on a short range |
| `music_tempo.py` | BPM, provisional phase, loud sections, kick pattern, candidate drops | `$PY music_tempo.py` |
| `music_grid.py` | exact first-beat time `BEAT0`, tempo drift | `$PY music_grid.py 130 0.423 27 72` |
| `music_spec.py` | spectrogram labelled in timeline beats | `$PY music_spec.py [r0 r1]` |
| `music_pulses.py` | kick / snare / hat strength on every half beat | `$PY music_pulses.py` |
| `timeline.py` | the edit; run it to print and self-check | `$PY timeline.py` |
| `ranges.py` | footage needed by the timeline -> `ranges.json` | `$PY ranges.py` |
| `prep.py` | builds the sub-frame store with RIFE (resumable) | `$PY prep.py ranges.json` |
| `densify.py` | more in-betweens where the picture moves fast | `$PY densify.py run 12 28`; `plan 12 28` only prints. Both take the two thresholds (output pixels of travel per frame that trigger 8x and 16x) |
| `repair.py` | rebuilds a duplicated source frame in the store | `$PY repair.py c3:125` |
| `fixends.py` | rebuilds the sub-frames next to every real frame in a store built without `rifeutil.Tween` (RIFE dead zone, see pitfalls.md); a store built by the bundled `prep.py` does not need it | `$PY fixends.py` |
| `posmap.py` | measures where every stored sixteenth really sits (`posmap.json`, read by the refstyle `render.py`) | `$PY posmap.py` after any change of the store |
| `check_store.py` | store covers the timeline; no duplicates left | `$PY check_store.py` |
| `render.py` | frames -> video part, or stills | `$PY render.py 0 742 part.mp4`, `$PY render.py 116 117 k.jpg`, `$PY render.py 100 140 s.jpg 4` |
| `kill_lags.py` | gunshot onset relative to K for every kill | `$PY kill_lags.py` |
| `audio.py` | `mix.wav` + stems, and where each shot lands | `$PY audio.py` |
| `mix_spec.py` | spectrogram of mix and stems in beats | `$PY mix_spec.py -5.2 5 59 72` |
| `run.sh` | 3 parallel parts + sound + mux -> master | `bash run.sh master.mp4` (the mux applies `volume=2.36` in the house `run.sh`, `volume=1.475` in `scripts/refstyle/run.sh`: the mixes are written at different levels, see "How the sound is made (audio.py)") |
| `check.py` | smoothness, kill strips, overview, loudness | `$PY check.py master.mp4 --sheets` |
| `deliver.sh` | upload copy from the master | `bash deliver.sh master.mp4 out.mp4` (house: crf 18, max 17 Mbps; `scripts/refstyle/deliver.sh`: crf 17, max 22 Mbps, and its own `volume=1.475`) |
| `rife_compare.py` | objective comparison of RIFE models | `$PY rife_compare.py rife-v4.25 rife-v4.26`: only `rife-v4.25` ships; download any other version from github.com/TNTwise/rife-ncnn-vulkan (folder `models/`) into `models/<name>/` (it must hold `flownet.bin`; the name must keep the version) |

`scripts/refstyle/` holds the files that replace or extend these for the reference style (its README.md
lists them): renderer, lyric text, kill finding in raw recordings, word alignment, per-kill gunshots, cover.

Each script starts with a docstring that explains its output and how to read it. Shared modules:
`ff.py` (finds ffmpeg and ffprobe), `clipio.py` (frame access by index), `rifeutil.py` (loads the
interpolation model).

## What costs time

| Step | Time | Notes |
|---|---|---|
| `prep.py`, `densify.py` | 6 to 10 sub-frames per second | about 30 min and 7 GB for the whole 37 s edit; only missing files are built |
| `render.py` | 0.3 to 5 s per frame | slow motion and transitions are the slow frames; a log line every 25 frames (reference style: every 100) |
| `run.sh` | 12 to 16 min for 2226 frames (house), 15 min for 2786 (reference), 5 min for 510 | uses the whole CPU; always in the background. Short edits cost more per frame |
| `peek.py` | 1.3 s per tile when stepping | a one-per-second overview of a 17 s clip takes 25 s |
| `audio.py`, `deliver.sh` | 5 s, 1 min | |
| `check.py` | 1 min | decodes the whole video |
| reference style, 1920x1080 | prep 6.9 sub-frames/s, 0.55 MB each; 46 s = 23,500 files, 13 GB, about 55 min; render 15 min | with a game running on the PC: interpolation 8x slower, render 35 min at BelowNormal priority |

Start `prep.py` in the background as soon as the anchors are roughly right and keep working (sound,
stills of finished ranges; in the reference style run `$PY posmap.py` once before the first still, it works
on a partial store). Poll with short commands; never block on one long wait. `ranges.py` prints the size
and time to expect for the store (it knows the wider reference-style frames).

## What to re-run after a change

| Changed | Re-run |
|---|---|
| anchors, kills, segments | `timeline.py`, `ranges.py`, `prep.py`, `densify.py`, `check_store.py`, stills, `run.sh` |
| `lag`, `voice`, `SWEEP`, `RISERS`, mix levels | `audio.py`, then only the last (mux) command of `run.sh` |
| effect values in `render.py`, transitions, `PULSES`, `bars`, `push` | stills, `run.sh` |
| one third of the video | `$PY render.py A B part_1.mp4`, then the concat and mux commands of `run.sh` (parts split at N/3 and 2N/3) |
| upload bit rate | `deliver.sh` |
| the store itself (`prep.py`, `densify.py`, `fixends.py`, `repair.py`) | reference style: `posmap.py`; then `check_store.py`, stills, `run.sh` |
| lyric cues (`lyric_cues.json`, `T.TEXT`), `textfx.py` | stills of a few words, `run.sh` |

## Handling jobs on this PC

All of these were run as written, in Git Bash. A PowerShell `$` is written `\$` there (bash would expand
`$_` and `$PID` itself).

```bash
# long job: start it with run_in_background and a log. The harness tells you when the command exits: read the log then.
$PY prep.py ranges.json > prep.log 2>&1 ; tail -3 prep.log
#   a finished job ends with:  prep.py "total NNNs" | densify.py "done N" | fixends.py "done: rebuilt N sub-frames" | run.sh, deliver.sh "done <file>"
#   run.sh without "done": a render part failed (its traceback is in part_N.log) and the other two parts may still be
#   running: list them and stop them by ID before starting again
#   a job you cannot be notified about: wait in a background command, never in the foreground (cut after 10 min):
#   until grep -q "^total\|^done\|Traceback\|Error" prep.log; do sleep 10; done; tail -2 prep.log

# is a game using the GPU? Tens of percent on a process that is not mine = a game (idle desktop: under 5 %)
powershell -NoProfile -Command "(Get-Counter '\GPU Engine(*engtype_3D)\Utilization Percentage').CounterSamples | Sort-Object CookedValue -Descending | Select-Object -First 3 | ForEach-Object { \$id = [int](\$_.InstanceName -replace '^pid_(\d+)_.*', '\$1'); '{0,5:N1} %  {1}  (pid {2})' -f \$_.CookedValue, (Get-Process -Id \$id -ErrorAction SilentlyContinue).ProcessName, \$id }"

# what is running. Other sessions run their own python on this PC (seen: another project's tests);
# mine have this project's scripts in the command line (render.py, prep.py, densify.py, fixends.py, part_N.mp4)
powershell -NoProfile -Command "Get-CimInstance Win32_Process | Where-Object { \$_.Name -match 'python|ffmpeg' } | Select-Object ProcessId, Name, CommandLine | Format-List | Out-String -Width 300"

# stop a job: TaskStop on its background task, list again, then stop what is left BY ID. Never by a
# command-line pattern (it also matches the shell that carries the command) and never by name (other sessions).
# The venv python is a launcher: each job shows as two python.exe with the same arguments, stop both.
powershell -NoProfile -Command "Stop-Process -Id 1234, 5678 -Force"

# a game is only detected and the render must go on: lower the priority of my render processes
powershell -NoProfile -Command "Get-CimInstance Win32_Process | Where-Object { \$_.Name -match 'python|ffmpeg' -and \$_.CommandLine -match 'render\.py|part_\d\.mp4' } | ForEach-Object { (Get-Process -Id \$_.ProcessId).PriorityClass = 'BelowNormal' }"

# after stopping a job that writes the store (prep, densify, fixends, repair write the files in place): the newest
# files must end with FF D9. This removes the truncated ones; then $PY prep.py ranges.json and
# $PY densify.py run 12 28 (each builds only what is missing), and after them the stopped job if it was fixends.py or repair.py
$PY -c "import glob,os;[(print('removed incomplete',f),os.remove(f)) for f in sorted(glob.glob('store/*/*.jpg'),key=os.path.getmtime)[-40:] if open(f,'rb').read()[-2:]!=b'\xff\xd9']"
```

Do not delete `store/`, `src/`, masters or earlier versions yourself: report their sizes and where they are.
Deleting is the user's call.

## How the picture is made (render.py)

The house `render.py`; `scripts/refstyle/render.py` shares the store, time map and shutter integration but has no
window or backdrop and a different set of effects (reference-style.md, "The style and how it is built").

- **Store**: `store/<clip>/<key>.jpg`, key = frame index x 16 + sixteenths, JPEG quality 95 4:4:4, the
  1344x1080 middle of the 1920x1080 frame (reference style: the whole 1920x1080 frame). A 4x grid (240 fps) everywhere, 16x (960 fps) where the edit
  runs slower than 0.7x, and 8x or 16x where the picture travels more than 12 or 28 output pixels per frame.
- **Time**: `timeline.TimeMap` is a monotone cubic through the anchors (beat -> source frame), so every
  speed change is eased. `lead()` and `tail()` build the usual shapes.
- **Shutter integration**: an output frame is the average of the stored sub-frames over its shutter
  interval (`SHUTTER = 0.65` of the frame time, box filter over the piecewise-linear interpolation).
  This gives exact time sampling at any speed and physically right motion blur. It is the reason the
  video does not judder.
- **Camera**: `cam()` returns zoom, offset and roll per beat (kill zooms, shake, pushes, cuts with zoom).
  Camera and transition moves are supersampled the same way: up to 40 sub-samples, at most 4 px of
  travel each (`CAM_SHUTTER = 0.85`), so a whip or spin smears instead of stepping.
- **Compositing** in linear light (gamma 2.2): blurred backdrop, window with rounded mask, stroke, halo
  and shadow, bloom and streaks, saturation, vignette, S-curve, then dither and grain (without them the
  smooth backdrop bands after encoding).
- **Encode**: x264 `-preset slow -crf 14 -g 60 aq-mode=3`, bt709 tags, light unsharp. Source frames are
  converted `tv -> pc` range on the way in and back on the way out.

Since October 2026 `prep.py`, `densify.py` and `repair.py` interpolate through `rifeutil.Tween` (no time
step near 0 or 1, see pitfalls.md), so a store rebuilt today differs slightly from the one behind the first
project's v4 master.

`render.py` is deterministic: the same store and timeline give the same bytes. The master's picture is
bit-reproducible; the upload copy is not (x264 with a bit-rate cap and threads differs run to run by
about 0.1 %, harmless).

The scripts that load RIFE (`prep.py`, `densify.py`, `repair.py`, `rife_compare.py`) end with
`rifeutil.finish()`: without it the process crashes while unloading (exit code 139) after the work is
done. Any new script that calls `rifeutil.load()` must end the same way.

## How the sound is made (audio.py)

House style. The reference style's `scripts/refstyle/audio.py` places one gunshot per kill at natural pitch and
no whooshes, and writes the mix at 0.8 (reference-style.md, "Sound").

- **Music**: cut at `T.MUSIC_T0`, optional low-pass sweep (`T.SWEEP`), fade out over `T.FADE_OUT`.
- **Game sound**: follows the same time maps as the picture, shifted by `lag` frames so the gunshot lands
  on the beat. It fades out between 0.7x and 0.25x and between 1.3x and 1.8x (no pitched-down or
  chipmunk sound); kills of level 2 and 3 stay audible. `voice=` and `stretch=True` use a pitch-preserving
  stretch (WSOLA) instead of resampling. High-pass at 70 Hz so it does not fight the bass.
- **Effects**: risers from `T.RISERS`, a whoosh on every whip, spin and zoom transition (panned with
  the whip direction).
- **Mix**: `0.84 * music + 0.60 * game + effects`, all three faded out over `T.FADE_OUT`. The mix peaks
  above full scale (1.29 in v4: a loud master plus shots), so `mix.wav` and the stems are written at
  half level; `run.sh` gives the level back (house: `volume=2.36` = 1.18 x 2; the reference style writes
  0.8 and uses `volume=1.475` = 1.18 / 0.8), limits at 0.82, and encodes
  AAC 320k with PNS, TNS and intensity stereo off. Result: -8.5 LUFS, decoded peak -0.7 dBFS (house v4).
  (v4 itself was mixed through a full-level 16-bit file: same loudness and peak, but 0.05 % of its
  samples were flattened for up to 0.4 ms before the limiter.)

## Other games, other formats

- Kill detection for any game: `kills_auto.py` with a profile in `games/` (SKILL.md, step 3). The Valorant-only tools
  (`find_kills.py`, `kill_table.py`: the banner badge at x 935, y 841, 50x50; `refstyle/detect_kills.py`, `mykills.py`:
  kill feed and ammo counter of the raw file) stay for Valorant 1080p60 recordings linked by `ingest.py`.
- Horizontal full-frame output: use `scripts/refstyle/` (render.py, check.py and clipio.py are already adapted).
