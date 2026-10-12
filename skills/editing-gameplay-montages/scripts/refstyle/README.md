# scripts/refstyle

Files for the reference style (../../reference-style.md). Copy the standard set first, then these over it
(the whole setup with the venv: ../../pipeline.md, "Setup"):

```bash
cp "$SK"/scripts/*.* . && cp -r "$SK"/scripts/games "$SK"/models . && cp "$SK"/scripts/refstyle/*.* . && cp timeline_ref_example.py timeline.py
```

Replace the standard file of the same name:

| File | Difference |
|---|---|
| `render.py` | horizontal full-frame renderer: blur-in cuts, streaks, colour split, lyric words, luma fade; reads `posmap.json` |
| `audio.py` | one gunshot per kill at natural pitch on the beat; mix written at 0.8 |
| `check.py` | 1920x1080; motion measured in two bands above and below the words |
| `clipio.py` | full-width frames; frame/time conversion through the real time table (recordings with gaps) |
| `densify.py` | 1920 px scale; only footage shown near real time (0.75 to 2.2x) |
| `run.sh`, `deliver.sh` | `volume=1.475` for the 0.8 mix; upload copy up to 22 Mbps |

Added:

| File | What it does |
|---|---|
| `timeline_ref_example.py` | the delivered edit: entry list `E`, `pre()` / `post()`, `TEXT`, `LUMA_FADE`. Its lyric cues are not published (song lyrics); a project gets its own from `lyrics_align.py` |
| `textfx.py`, `text_test.py` | lyric words: Impact (Windows font folder, or `IMPACT_FONT`), random letter reveal, translucent tinted fill, ink centred on the frame; `$PY text_test.py` shows the first cue of every style on a flat background |
| `detect_kills.py`, `kill_review.py` | `$PY detect_kills.py <clips folder> detect` scans raw recordings for the player's kills on the kill feed; `$PY kill_review.py <clips folder> detect review` writes review sheets and `review/index.json` (copy to `detections.json`) |
| `mykills.py`, `strip.py`, `flick.py` | shot frame K from the ammo counter with galleries (`gal_NN.jpg`: flash on tile `+0`, absent on `-1`): `$PY mykills.py` for every detection not in `BAD`, `$PY mykills.py 12,13` for those ids only (it numbers the sheets from `gal_01.jpg` again, so it overwrites the sheets of a full run, and it rewrites `kills.json`); per-frame strips to set K by hand; camera travel and earlier shots per kill. The K typed into the timeline entry is the authoritative one: `kills.json` is a regenerated record, read by `flick.py` |
| `introcand.py` | candidate shots as sheets: `$PY introcand.py 1 c22:6600:6800:10` (zoom 1: the HUD-hiding crop it was written for is what the user rejected) |
| `transcribe.py`, `cue_onsets.py`, `lyrics_align.py` | recognised words (own venv with faster-whisper); plain vocal onsets per word; one cue per word on its onset |
| `cover_plates.py`, `cover.py` | cover image: clean frames of the edit, title only, centred |

Values that belong to the delivered project and must be replaced:

| File | What |
|---|---|
| the timeline | the whole music block (`MUSIC` with its extension, `BPM`, `BEAT0`, `M0`, `R0`, `R1`, `FADE_OUT`, `LUMA_FADE`, the `RISERS` beats), the entry list `E`, the intro words `_T` and the `-1.5` beat that separates them from lyric words. `CUT = 0.15` and the `hold` of `post()` are 4 and 8 frames at 130 BPM: at another tempo use `4 / FPB` and `8 / FPB` |
| `detect_kills.py` | `SKIP_PREFIX` (file names to leave out); it scans `.mp4` only |
| `mykills.py` | `BAD` (rejected detections) |
| `flick.py` | `KFIX` (hand-set shot frames: detection id -> K) and `SKIP` (detection ids to leave out): they act in `flick.py` only, `mykills.py` has neither |
| `lyrics_align.py` | `LINES` (the confirmed words), `OVERRIDE`, `DROP`, `RED` (beat ranges whose words are red; default: only the intro, before beat -0.5: the delivered edit also had its breakdown, beats 27.5 to 31.5) |
| `transcribe.py` | `LANG` (language code) and `PROMPT` |
| `cover_plates.py` | the three beats |

Standard tools not used in this style: `find_kills.py`, `kill_table.py`, `kill_lags.py` (banner method on
the 1344 px crop; `kill_table.py` would overwrite `kills.json` with another layout). `peek.py` shows the whole
frame here.
