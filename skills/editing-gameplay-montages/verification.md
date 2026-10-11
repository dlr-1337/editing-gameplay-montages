# Verifying an edit you cannot watch or hear

Two kinds of evidence: numbers, and pictures you read. A contact sheet read through the Read tool is
your eyes; a spectrogram is your ears. Sheets wider than about 2000 px are shrunk when you read them,
so keep tiles at 100 px or more with large labels (the scripts do).

## Before rendering video

| Check | Passes when |
|---|---|
| `$PY timeline.py` | prints every segment, no assertion, no "note:" you did not intend |
| `$PY ranges.py` | no ERROR (anchors inside the clips) |
| `$PY check_store.py` | `missing footage: 0` and no frame that copies its predecessor |
| gallery from `kill_table.py` (raw recordings: `gal_NN.jpg` from `mykills.py`) | for every kill: flash visible on tile `+0`, absent on `-1`; otherwise set K with `[banner, K]` (raw recordings: find it on `strip.py` and type it into the timeline entry) |
| `$PY render.py N N+1 x.jpg` on a kill, a transition middle, a slow-motion frame, the first and last second | framing right, window and backdrop as intended, nothing black, torn or doubled |
| `$PY render.py A B x.jpg 2` across a transition | both clips visible mid-way, smooth smear, no stepped copies |
| `$PY audio.py` | house style: each kill line near 0 ms (see "Sound"); `mix peak` up to 2.0 is fine, the files are written at half level. Reference style: read the closing count of measured, clip-offset and silent gunshots (reference-style.md, "Sound"); `mix peak` below 1.0 (v3: 0.94), the script stops above it |

Frame number of a beat: `round((beat - R0) * FPB)`.

## After rendering: `$PY check.py master.mp4 --sheets`

| Output | Reference (house v4) | Meaning |
|---|---|---|
| frames identical to the previous one | 0 | any hit is a bug in frame access or the store |
| frames where the motion stops for one frame | 1, a real pause of the aim | every other hit is stutter the user will feel; the rejected v3 had 20 |
| one-frame jumps not on a kill, accent, cut or transition | 1, a shot that did not kill | look at each with `peek.py`; a jump you cannot explain is a bug |
| overall judder index | 0.22 (v3: 0.34) | evenness of motion; compare versions of the same edit, not different edits |
| sound | -8.5 LUFS, true peak -0.2, decoded peak -0.7 dBFS | a decoded peak at or above 0 clips (v1 to v3 were at +3.0 to +3.2) |
| `sync_N.jpg` | flash absent on `-1`; first seen on `+0` for 19 kills (faint on 3) and on `+1` for 3, as the printed table says | one row per kill, frames -3 to +4 |
| `pv_NN.jpg` | | the whole video at two frames per beat: order, framing, slow-motion bars, transitions, fades |

A beat rarely falls on the centre of a frame. `check.py` prints, per kill, the exact frame position and
where the flash must first show: on `+0` (only faintly when just a few percent of that frame's
exposure lies after the shot), or on `+1` when the shot comes after the exposure of `+0`. Later than
that tile means K or the beat is wrong (or, in a slow lead-in, that the time map reaches the kill below real
speed: pitfalls.md, "Bullet time into a kill"). A level 3 kill shows its impact frame on `+0`: an inverted
monochrome picture (nearly black for a bright scene, nearly white for a dark one). That is the effect,
not a fault; judge its flash on the next tiles.

Run it again on the upload copy: that is the file the user gets.

### A stalled frame: what is it?

`check.py` names the beat, the clip and the source frame. Two cases need no further look:

- **The beat is the last frame before a cut, or lies in the opening fade**: false positive (the neighbours
  are transition frames or black).
- **A whole source position (`source frame 7379.0`) inside slow motion below about 0.2x**: RIFE's dead zone
  in a store built without `rifeutil.Tween`. `$PY fixends.py` (GPU), in the reference style then
  `$PY posmap.py`, render again (pitfalls.md, "Picture").

Otherwise `$PY cadence.py <clip> <frame-8> <frame+8> --detail`:

- **Every region drops to about 0 for one frame** between normally moving frames: the recorder
  duplicated a frame. `$PY repair.py clip:frame`, render again. (`prep.py` repairs these while building;
  `check_store.py` lists any left.)
- **The world slows over several frames, stops, starts again, while the weapon still moves a little**:
  the player paused the aim. Real footage; leave it. Say so if you report the number.
- **The source is fine**: the fault is in the pipeline. Is every frame read through `clipio`? Does
  `check_store.py` pass? Was the store built before an anchor change?

A duplicated source frame shown at real time does not produce a full stall (shutter integration
spreads it into a small unevenness), so do not rely on `check.py` alone: `check_store.py` is the gate.

## Reference style: extra checks

| Check | Passes when |
|---|---|
| crop of a still beside the same crop of the reference: `ffmpeg -ss T -i ref.mp4 -frames:v 1 -vf crop=1500:560:210:230 a.jpg`, the same crop of `render.py N N+1 still.jpg`, joined with `hstack` | letters as see-through and as large as in the reference; placement follows the user's rule (exact centre). Stills lack the encoder's `unsharp`, so do not judge crispness here |
| text centre: guide lines on a still, or `cue.ink` in `textfx.py` | ink centre 960 +/- 0.5 px, caps centred on y = 540, for every cue |
| `lyrics_align.py` table | every word within about 100 ms of its recognised time; overrides explained; unconfirmed lines absent |
| `posmap.py` | prints a measured position table per kind of grid, or says it uses the reference table for a kind the store does not contain; after `fixends.py` nearly every dense interval counts as fixed |
| `check.py` on the reference-style master | no stall at a whole source position inside slow motion |

Reference values (delivered v3, 46 s): identical frames 2 (the black opening fade), stalls 1 (the frame before
an intro cut: false positive), unexplained jumps 2 (a real flick at real time, a muzzle flash in a replay),
judder index 0.27, -9.3 LUFS, decoded sample peak -0.4 dBFS, true peak 0.0 dBFS; flash table: 42 kills on
`+0`, 8 faint on `+0`, 12 on `+1`. Its master reads 1 unexplained jump and judder 0.264. The first render
of the same edit had 2 real stalls at whole source positions (RIFE dead zone).

## Sound

- Reference style: `audio.py` places each gunshot by construction and ends with a count (reference-style.md,
  "Sound"). The shots "placed with the clip offset" are the ones to doubt; nothing measures them. Do not
  measure the finished stem: every shot fades in from silence 8 ms before its onset and neighbours overlap.
- House style: `audio.py` prints, per kill, where the loudest game-sound onset lands relative to the beat. Within
  a few ms of 0: the shot is on the beat. In v4 that held for 12 of 22 kills (within 7 ms). A value of +20 to +50 ms
  usually means a louder sound right after the shot (kill sound, the body of the gunshot) was picked,
  and slow-motion or voice-chat kills have no clean onset at all. Check those on the `kill_lags.py`
  strip instead of chasing the number.
- `$PY mix_spec.py r0 r1 ...`: a riser must end on its beat, the sweep must close and reopen where
  intended, whooshes must sit on transitions, the game stem must be silent in slow motion.
- `kill_lags.py` prints `K+2.75` (clear), `K~2.25` (found on a looser pass: look at the strip) or `K ?`.
  In v4 the looser pass agreed with the values read by eye for 4 of 5 game-sound kills within 0.05
  frame, and was meaningless on the clip with voice chat.
- Loudness has no pass mark. The first project's four deliveries measured -7.7 to -8.5 LUFS, the second
  project's -9.3, short test edits -8.2 and -9.3; the user never commented on loudness, and what the platform does with it is unknown.
  The decoded peak is the hard limit: below 0 dBFS.

## What no check tells you

How it feels in motion, whether the accents are too strong or too weak, the balance of music, shots
and effects, whether voice chat should stay. Say this in every report; the user's reaction is the only
measurement of taste.

Unverified: a vendor blog (ShortSync) says TikTok may convert 60 fps uploads to 30 fps unless "Allow
high-quality uploads" is on or the upload is made from a desktop browser. Not confirmed by an
official source. Mention it as unconfirmed, with the link, because it would undo the smoothness:
https://shortsync.app/resources/tiktok-upload-method-high-quality ,
https://www.shortsync.app/features/60fps-video-upload

## The report

Portuguese, informal, no questions. Shape that worked:

1. First sentence: the file path, length, size, and that it was checked by measurement but not watched.
2. The user's main complaint first: cause, fix, and the number before and after.
3. What changed, in a few bullets with plain words (no script names, no beat numbers).
4. What only they can judge, and anything left out or unconfirmed.
5. Where the project is kept and how much disk it uses.
