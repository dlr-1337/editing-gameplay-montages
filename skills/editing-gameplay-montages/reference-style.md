# Reference-style edits ("faz com a MESMA EDICAO desse vídeo")

The reference decides the look; the user's rules in SKILL.md decide where the reference is not followed.
The machinery is the house pipeline: frames by index, measured beat grid, muzzle-flash frame on the
beat, sub-frame store, shutter integration.

Worked example: `scripts/refstyle/timeline_ref_example.py` (October 2026, "Teto - Paypal", 46 s, 62 kills,
delivered as v3; the project folder itself, with the footage, is not published).
Setup: pipeline.md, "Setup" (the standard scripts, then `scripts/refstyle/` over them, then
`cp timeline_ref_example.py timeline.py`). `scripts/refstyle/README.md` lists what in those scripts
belongs to that one project, and the standard tools this style does not use.

## Reading the reference (you cannot watch it)

In the project folder, with `FF=$("$PY" ff.py | tr -d '\r')` and `REF` = the reference file:

1. Contact sheets. The whole video at 4 fps:
   `"$FF" -v error -i "$REF" -vf "fps=4,scale=240:-2,tile=8x6" -q:v 3 ref_%02d.jpg`.
   Then EVERY frame of 0.8 s around the drop, one rapid series and the ending:
   `"$FF" -v error -ss T -t 0.8 -i "$REF" -vf "fps=60,scale=240:-2,tile=8x6" -frames:v 1 every_T.jpg`.
   Clip anatomy only shows frame by frame.
2. Cut list:
   `"$FF" -v error -i "$REF" -vf "select='gt(scene,0.25)',metadata=print:file=cuts.txt" -an -f null -`
   (the file name inside the filter must be relative: a drive path breaks it). Clip lengths in frames
   give the note values (11-12, 22-23 and 46 frames = 16th, 8th and quarter note at 79 BPM).
3. Cut-to-beat offset: the beat grid of the reference's own sound (`$PY music_tempo.py "$REF"`, then
   `$PY music_grid.py BPM BEAT0 0 30 "$REF"`; look at the half and double tempo candidates) against
   the cut list. The reference's cuts sat 28 ms before the hit.
4. Text, colour and overlays on ENLARGED crops:
   `"$FF" -v error -ss T -i "$REF" -frames:v 1 -vf "crop=1500:560:210:230,scale=900:-2" crop.jpg`.
   On small tiles the reference's see-through letters looked solid, and that mistake shipped.
5. Write the findings into a notes file before designing (the context gets summarised).

## The style and how it is built

| Element | In the reference | Built as |
|---|---|---|
| format | 1920x1080, 60 fps, full-frame gameplay with HUD | `W, H = 1920, 1080`; `clipio.CROP_X, CROP_W = 0, 1920`; no window, no backdrop. Anything else: "Another frame size or rate (not built)" below |
| zoom | none held; small pushes and punches | push-in 3.5 % over a take (10 % over the 7-beat bullet time, 8 % over one 4-beat take, 0 in the intro and on the final take), kill punch 1.6 / 2.6 / 4.5 % by level, a lean of 8.5 % on the last 2 frames before a cut, and the 5-frame zoom burst of a `bzoom` blur-in. Nothing else enlarges the picture |
| clip anatomy | hard cut, 3-4 blurred frames of compressed motion, sharp near-frozen slow motion, 1-2 frames of speed-up | `pre()`: 16 source frames in the 4 frames before the beat, last frame at real time; K on the beat; `post()`: real time 0.3 beat (until the feed row confirms the kill), slow motion 0.12-0.16x, 0.08 beat out. A half-beat clip runs on at real time |
| cut position | just before the hit | cut 0.15 beat (4 frames at 130 BPM) before the beat it lands on, so the flash is on the hit. Which beats: `CUTS_ON` (the user's choice in the briefing). `"bass"` (default; an editor's note: "as transições rolarem nos graves da música, não no snare"): only kicks / 808s, so a take starts on a kick and kills on snares or hats go inside a take (`M` entries) instead of right after a cut. `"kills"`: a cut before each kill, as in the delivered v3 (19 of its 57 cuts land on a kick, measured) |
| blur-in | horizontal whip with thin streaks, zoom burst with rays, rotated whip, red/cyan split | `blur_in()` and `streaks()` in render.py: post effects on the finished frame, strength `(1 - q/5)^2` |
| pacing | 16th-note runs, 8th and quarter-note clips | `"kills"` (as v3): sparse 808s: 2-beat clips; hats on every half beat: 1-beat clips with a few half-beat runs. `"bass"`: the kicks set the clip lengths, so sparse 808s give takes of 2 beats or more with the snare and hat kills inside them, and a dense kick pattern allows 1-beat clips. Both: breakdown: bullet time (`L` entry) into the best kill, which fires on the drop |
| lyric words | Impact caps, about 23 % of the frame height, letters pop in random order, see-through tinted fill, red in the intro | `textfx.py` (needs Impact, or `IMPACT_FONT` = a .ttf path; `render.py` imports it, so without the font nothing renders); see "Lyric words" |
| look | sharp, saturated, colour fringes at the edges | per-channel zoom `CA0 = 0.0011`, saturation 1.20, S-curve, `unsharp 0.55` at encode |
| intro | slow cinematic shots without HUD | the user has no HUD-free footage and rejects cropping: ability shots in slow motion at FULL FRAME, `shutter=2.2` to `2.6` output frames, `push=0`, `intro=True`, `mute=True`, soft whips, red words |
| ending | long slow-motion hold, luma fade (dark areas black first) | `T.LUMA_FADE`; the last take is `calm=True` (no zoom or shake on the ace) |
| watermark | the editor's tag | never copied, and nothing is put in its place |

Timeline entries (`E` in the example). The last element is always an options dict, `{}` when empty:
`("shot", start, clip, a, b, {})` no kill; `("K", beat, clip, K, {})` one kill; `("M", [(beat, K), ...],
clip, {})` kills of one continuous take; `("L", start, lead_anchors, beat, clip, K, {})` custom lead-in.
Each take ends where the next starts. Options:

| Option | Meaning |
|---|---|
| `lv` | kill level (default 1); for an `M` entry the level of the last kill, the others are 1 |
| `n`, `rate` | source frames squeezed into the 4 blur-in frames (default 16); slow-motion speed of `post()` (default 0.16) |
| `end` | beat where the take ends; default the start of the next entry (`R1` for the last). Only the last entry may differ from it: an assertion stops any other |
| `post` | list of anchors `[(beat, source frame), ...]` that replaces what `post()` would add after the kill (`K`, `M`: after the last kill's anchor; `L`: after the kill's anchor). Beats increase; the take lasts to the last anchor's beat, so end the list on the take's end. The example uses none |
| `tin` | how the take comes in: `("fade", 0)`, `("cut", 0)`, `("bwhip", 0, +1\|-1)`, `("bzoom", 0)`, `("broll", 0, +1\|-1)`. Default: the list `_FX` in the timeline, cycled by entry number (entry i gets `_FX[i % 8]`: bwhip +1, bzoom, bwhip -1, broll +1, bwhip +1, bzoom, bwhip -1, broll -1). Set `tin` on an intro take (`fade`) and wherever the cycle is wrong |
| `push`, `shutter`, `intro`, `mute`, `calm` | take options, documented at `S()` in the example |

## Another frame size or rate (not built)

Only 1920x1080 at 60 fps exists. What is fixed, before promising anything else:

- 1920x1080 is written into the refstyle `render.py` (`W, H` and the encoder line), `textfx.py`,
  `check.py` (bands, sheets), `cover.py` and `densify.py`. They must change together; none of it has run.
- `clipio.SW, SH` is the size of the SOURCE clips, not of the output.
- `FPS` in the timeline is the output rate and also the rate the anchors assume for the clips. A 30 fps
  reference does not change it: deliver 60 fps (stutter is this user's first complaint) and copy the
  reference's rhythm in beats.
- A vertical reference made from horizontal recordings fills the frame by cropping to a third of the
  game width: the standing zoom this user rejected ("voce deixou um zoom no video todo"). Their rule
  outranks the reference: frame the gameplay as in the house style (window over a blurred backdrop,
  edit-design.md) and take cuts, pacing, words and ending from the reference. No renderer does both yet
  (the house `render.py` has the window, the refstyle one the blur-in cuts and the words). Say in the
  report what was not copied and why.

## Music section and where the kills go

`M0`, `R0`, `R1`, `FADE_OUT` and how to pick the section: edit-design.md, "Music" (it holds for both
styles). In the delivered edit timeline beat 0 is the first 808 after the vocal intro (`M0 = 31`), the 16
beats before it are the intro (`R0 = -16`: slow shots, artist and title as words), the big drop is beat
32 and the video ends on a break (`R1 = 84.6`). `RISERS` end on beats 0 and 32.

Kills go on measured hits (`music_pulses.py`). In the delivered edit: 30 on kicks (every kick of the
section has one), 13 more on snares or claps, 19 on a loud hat (`high` 0.69 to 1.00) in the passages
where hats run on every half beat, none on a beat where nothing arrives. `music_pulses.py` lists 18 of
those 19 under "kills on a beat with neither kick nor snare": in this style check that each has a high
value; in the house style that list must be empty. With `CUTS_ON = "bass"`, cuts go on kicks only:
`music_pulses.py`'s line "transitions not on a kick / bass hit" must say "none" (with sparse 808s that means
fewer, longer takes holding several kills, not a cut before every kill). Levels: `lv=3` on the drop and on the final kill, `lv=2` on the
first kill and on kicks after the drop (16 kills), level 1 elsewhere. 62 kills in 37 s of gameplay.

## Finding kills in raw 2-minute recordings

Raw ShadowPlay recordings hold menus, deaths, other windows. Put EVERY recording in `clips.json` first
(`mykills.py` skips, and names, the files it cannot map), then scan them all:

1. **Kill feed** (1080p: x 1300-1916, y 84-384): the player's own row has a lime wedge on the left, a
   teal body and a red victim section. `detect_kills.py <clips folder> detect [name filter ...]` takes the
   folder of the raw recordings as its FIRST argument and scans the `.mp4` files lying directly in it (not
   `src/`; `SKIP_PREFIX` leaves files out, and a trimmed copy `name-HH.MM.SS.mmm-HH.MM.SS.mmm.mp4` is skipped
   when its raw file is in the folder); the second argument is where it writes one json per recording
   (a recording that already has one is skipped as "cached"); further arguments are name filters
   (substrings of the file name). It decodes each WHOLE recording, tracking rows by the x where the red
   starts: no time limit per clip; measured on this PC, 18 s for one 83.5 s recording (about 0.2 s per
   second of video; up to three recordings run at once). `kill_review.py <clips folder> detect review` makes
   review sheets and `review/index.json` (copy it to `detections.json`). 107 detections on 27 clips, 10 false:
   the player's own death, a teammate, the buy menu, duplicates.
2. **Shot frame K** = the frame where the HUD ammo counter (x 1262, y 998, 84x44) changes, 5 to 12
   frames before the feed row (usually 6 to 10): `mykills.py` writes `kills.json` and `gal_NN.jpg`.
   "guess" (counter unreadable) and "ammo-loose" (several bullets) need `strip.py clip a b`: every frame
   with feed and ammo pasted in. The K you confirm is typed into the timeline entry.
   `mykills.py` alone measures every detection not in its `BAD` set; `mykills.py 12,13` only the listed
   ids, in that order (for a second look). Both number the sheets from `gal_01.jpg` (7 kills per sheet), so a
   subset run overwrites the sheets of an earlier full run (higher-numbered old sheets stay, out of date),
   and both rewrite `kills.json`: the listed ids are recomputed from the ammo counter, the other entries are
   kept. The K in the timeline entry is the authoritative one: `kills.json` is only a record (it is read by
   `flick.py`, which has its own `KFIX` for hand-set values) and is regenerated, so a hand-set K lives only
   in the timeline entry.
3. A feed row 2 or 20 frames after the only ammo change means another bullet or another shooter killed:
   look, or drop the kill.
4. **Choosing.** The user's own trims (`name-HH.MM.SS.mmm-HH.MM.SS.mmm.mp4`: start and end inside the raw
   clip, so the detections whose time falls inside are their picks) mark favourites. Prefer single taps
   (`flick.py`: no earlier shot in 30 frames) in clear scenes. Reject on sight: the enemy filling the
   screen, an explosion or flash over the picture, a flat-colour screen, dark scenes, sprays.
   `flick.py`'s travel number ranked a point-blank kill with an explosion first; the user removed it.

The house tools `find_kills.py`, `kill_table.py` and `kill_lags.py` (banner badge, 1344 px crop) are not
used here; `kill_table.py` would overwrite `kills.json` with another layout.

## Lyric words

Procedure (in the project folder; `$PY` = the project venv; step 1 runs in the speech-recognition venv of
pipeline.md, "Setup"):

1. `transcribe.py`: set `LANG` (language code) and `PROMPT` (artist, title, genre) in the file, then
   `./venv_asr/Scripts/python transcribe.py src/music.flac lyrics_whisper.json large-v3 <t_end>`. The optional
   `t_end` limits recognition to the first `t_end` seconds of the track: give the track time where the edit
   ends (`T.beat_time(T.R1)`), not the whole song.
2. Read `lyrics_whisper.json` (the script also prints one line per segment): every word has `w`, `s`, `e`
   (seconds in the track) and `p` (probability).
3. Confirm each line against a lyrics page (first bullet below); keep only the confirmed lines.
4. Fill `LINES` in `lyrics_align.py`: a list of entries `(t0, [words])`. `t0` is the `s` time of the entry's
   first recognised word in `lyrics_whisper.json`; the script takes the recognised word nearest to it. The
   corrected words are mapped ONE TO ONE onto that many consecutive recognised words (across segments): word
   k takes its timing from the k-th of them. So the number of corrected words must equal the number of
   recognised words the entry spans, or everything after the mismatch takes its time from the wrong words.
   Where the recogniser split or merged a word, end the entry before the mismatch and start the next one,
   with its own `t0`, after it (each entry finds its own start; an entry need not be a whole lyric line).
5. `$PY lyrics_align.py` -> `lyric_cues.json` (`[beat_in, beat_out, "WORD", style]`) and a table: word,
   recognised beat, chosen beat, difference in ms. A word that moved by more than about 100 ms is looked at in
   step 6.
6. Where doubtful: `$PY cue_onsets.py` lists, for each recognised word, the vocal onsets within 0.14 s
   (beat, dB rise) and the nearest 16th. Then in `lyrics_align.py`:
   - `OVERRIDE = {("WORD", beat_from, beat_to): beat}` applies to a corrected word equal to WORD whose
     RECOGNISED beat (the table's second column) lies in the range. `beat` is where the cue starts to show;
     its onset counts as 0.04 beat later (`ADV`: the automatic choice shows every cue 0.04 beat before its
     onset), which is what the table then prints as "chosen". To put the onset on the beat B of the
     `cue_onsets.py` list, give `B - 0.04`.
   - `DROP = {("WORD", beat)}` leaves that word out of the cues. `beat` is the recognised beat rounded to ONE
     decimal (`round(b, 1)`: a table value of 12.34 is 12.3; at x.x5 check which way Python rounds). A dropped
     word still takes part in the timing of the others and still has its row in the table.
   - `RED = [(beat_from, beat_to), ...]`: cues starting inside a range are red, all others cycle gold, silver,
     white. The default is only the intro (before beat -0.5); a song's red breakdown goes in here.
   Run step 5 again.
7. `$PY text_test.py` (`text_test.jpg`), `$PY timeline.py` (the "words on screen" line), stills of a few words.

- **Right words only.** Speech recognition (`transcribe.py`: faster-whisper large-v3 in its own venv)
  gets about half of a trap verse wrong. Confirm each line against a lyrics page with yes/no questions
  through WebFetch (`letras.com.br`, `vagalume.com.br`; it will not quote lyrics, it does confirm
  phrases). Unconfirmed lines get no text. If nothing can be confirmed: no lyric words at all; artist and
  title over the intro are not recognised speech and may stay.
- **A new project has no cues** until `lyrics_align.py` writes `lyric_cues.json`; the intro words typed in the
  timeline (`_T`) do show, until you replace them. `$PY timeline.py` ends with the number of cues and the
  first words: read that line.
- **Timing.** `lyrics_align.py` (set `LINES` to the confirmed words): harmonic/percussive split (median
  filters), onset function = rise of the harmonic part in the vocal band, each word assigned to one onset
  near its recognised time, in order (dynamic programming, 16th grid as fallback). `cue_onsets.py` lists
  the plain onsets for hand overrides. Output `lyric_cues.json`, loaded into `T.TEXT`.
- **One word per cue.** A word of one or two letters rides with the next if it follows within 0.45 beat;
  words under 0.3 beat apart share a cue; no word shows more than 0.45 beat before it is sung. Cues start
  0.04 beat early, the whole word is there within 3 frames, and it leaves when the next one arrives (at
  most 1.1 beats).
- **Centre.** Each word on the exact middle of the frame: horizontally the visible ink (measured on the
  letter masks, not the advance widths), vertically the cap height on H/2 (`cy=0.5`). The reference sits
  slightly higher; the user wants the middle.
- **Translucent.** Blend on display values: overlay share 0.62 (0.50 for the red style) plus flat colour,
  at strength 0.62-0.80, small glow. Drawn before the blur-in, so a whip blurs the word with the footage.
  `duck()` dims it by 35 % while a shot fires. `$PY text_test.py` shows the first cue of each style present
  in `T.TEXT` on a flat background.
- A lyric that names what is on screen is worth building around ("através da parede" on a wallbang,
  then the victim's replay).

## Sound

The picture is in fast-forward or slow motion almost all the time, so the game sound must not follow the
time map. `audio.py` (refstyle) places one gunshot per kill at natural pitch with its onset on the beat.
It finds each shot's onset in the clip's own sound (0.4 to 2.8 frames after K) and ends with a count:

| It prints | Meaning | In v3 (62 kills) |
|---|---|---|
| placed on its own measured onset | the shot rises at least 8 dB by itself: on the beat by construction | 38 |
| placed with the clip offset | another sound covers this shot; the clip's usual offset was used. It can sit a frame or two off and was never verified by ear | 13 |
| no gunshot, mute=True | you muted the take (voice chat over it, an intro shot) | 4 |
| no gunshot, none found | no shot of that clip stands out (voice chat, constant loud sound) | 7 |

A clip with voice chat: set `mute=True` on each of its takes; do not rely on the automatic silence. The
mix is written at 0.8 and `run.sh` applies `volume=1.475` (the resampled track peaks above 1.0);
`audio.py` stops if the mix still exceeds full scale.

The cuts carry no whoosh. `audio.py` places one only for the `tin` kinds `whip`, `spin` and `zoom` (the house
style's transitions), and the blur-in cuts of this style (`bwhip`, `bzoom`, `broll`) are none of them, so the
sound of v3 is the music, the risers (`RISERS`) and the gunshots. To try whooshes, add the kinds to the tuple at the
top of the loop in `sfx()` (not tried).

## Slow motion at 0.06-0.16x

This style holds slow motion far below the house style's 0.28x, which exposed RIFE's dead zone
(pitfalls.md). `check.py` shows it as "motion stops for one frame" at whole source positions.
`rifeutil.Tween` builds new stores right; `fixends.py` repairs an old one on the GPU; `posmap.py`
measures where each sixteenth really sits and the refstyle `render.py` renders from that (run it after
every change of the store, and once before the first still: `render.py` stops without `posmap.json`; it
also covers a half-repaired store when the GPU is busy).

## Cover image

Needs a reference-style project (the tools use its renderer and lettering; the house style has none).

1. Put three beats just after clean kills into `cover_plates.py` (three different scenes) and run it:
   frames of the edit without words and without camera moves, in `cover/`.
2. `$PY cover.py cover/plate_X.png "../capa_<name>_1.jpg" red "TITLE"`, then `_2` and `_3` with other
   plates and other styles (`red`, `gold`, `silver`, `white`): three covers to choose from.

The plate is darkened and the title set in the video's lettering on the exact centre, in capitals, kept
inside the middle 800 px so a vertical centre crop keeps it (a long title shrinks: use the short form).
Title only: the song title unless the user names one. 1920x1080 JPG beside the clips. `cover.py` refuses
to overwrite an existing file.

## Costs (GTX 1650, Ryzen 5 5500)

1920x1080 store: 6.9 sub-frames per second, 0.55 MB each; about 23,500 files and 13 GB for 46 s.
Start `prep.py` as soon as the timeline passes; a second `prep.py` on a priority subset can run beside
it. Full render 15 minutes on an idle PC, 35 at below-normal priority while a game runs.

## What the user said, version by version (2026-10-11)

| After | Their words | Change |
|---|---|---|
| first render (watched in `_editor`) | "as letras estavam sem transparencia alguma 100% solidas, e no comeco aquele zoom ta mt feio" | translucent letters; intro at full frame instead of a 1.8-2.2x crop |
| v1 | "ta mt top so que vamos tirar ... aquela kill da raze, é muito feia e tentar sincronizar ao maximo as letras da tela" | kill replaced by a clean tap; one word per cue on vocal onsets |
| v2 | "tem que centralizar a letra no meio da tela, arruma isso e JA ERA" | ink centred on the middle of the frame; v3 is the accepted version |
| covers | "tira esse valorant edit da tela" | title only |

Not judged: gunshots on the beat (13 of them placed by clip offset, 11 kills silent), zoom-burst
transitions outside the intro, the song title as intro words.
