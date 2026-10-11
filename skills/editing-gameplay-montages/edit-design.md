# Designing the edit (`timeline.py`): house style

For a copy of a reference video read reference-style.md; from this file it uses only "Music" (choosing the
section, `M0`, `R0`, `R1`). The user's rules that hold in both styles (no standing zoom, smoothness, kills on
the beat, no zoom on the ace) are in SKILL.md.

The worked example is `scripts/timeline_example.py`: v4, the delivered montage (37 s, 7 clips, 22 kills,
130 BPM). The user called v3 "PERFEITO, mas ..."; v4 answers the "mas" and drew no further comment. Every number below comes from it or from `render.py` / `audio.py`.

## The brief, in the user's words

| After | The user said | What answered it |
|---|---|---|
| request | "highlight montage para postar no tiktok", "zoom nas skills, slow motion e transicoes", "faça a edit bem top" | vertical, beat-synced, accents on kills and abilities |
| v1 (full-height centre crop) | "voce deixou um zoom no video todo sabe ? ai fica estranho", "o slow motion ta bem travadinho", "as transicoes e bumps nas kills ta legal só aprimorar tudo" | windowed layout; AI-interpolated slow motion |
| v2 | "da pra sincronizar melhor e fazer transicoes melhores e tudo mais suave, no fim nao de um zoom no ace apenas deixe a tela escurecer, e uns zoons mais naturais" | re-measured beat grid; both clips move in a transition; eased zooms; fade-only ending |
| during v3 | "o clip 4 topppp ficou travado na edit parece que ta com pouco fps" | every speed change interpolated |
| v3 | "PERFEITO, mas ... escolher qual seja a melhor sequencia, arrumar problemas de interpolacao que ainda sinto umas quedas de fps ... efeitos intensos e fodas" | index-exact frames, shutter integration, new sequence, impact frames, sound design |

Not yet judged by the user: how v4 feels in motion, the strength of the accents, the mix, the voice
chat left under the music in one clip.

## Material

- The best material is one clip per play with a few seconds of margin, but take what the user gives and
  do not ask: raw two-minute recordings are scanned for kills (reference-style.md, "Finding kills"). 8 to 15 clips give 30 to 45 s.
- Watch everything first (`peek.py` overviews, `find_kills.py` sheets). Note per clip: agent, weapon,
  kills and their spacing, abilities on screen (dash, fireball, dismiss), anything ugly (a death, a
  menu, a whiff).
- Check each clip's own sound: one clip of the first project carried voice chat instead of game sound
  (`kill_lags.py` shows no clean onsets there). Such a clip gets `voice=0.8`.

## Sequence

What v4 does, and why:

1. **Open on the best single moment, landing on the drop**: 4 beats of lead-in over the breakdown with
   a riser, the kill on the bass re-entry (level 3), slow motion once the flash has cleared.
2. **Group by clip and agent** so the picture changes on purpose: Bind sheriff (3 segments), Phoenix,
   one Jett kill, Reyna triple, the Vandal 4K, then the ace.
3. **Keep takes continuous when kills are close**: two kills with a dash between them, or a kill, a
   fireball and two more kills, stay one take with a speed ramp through the ability. Less cutting,
   more flow.
4. **Match kill spacing to the music**: three Reyna kills on three consecutive bass hits (beats 29,
   30, 31). Gaps between kills run from 1 to 8 beats, mostly 2 to 5.
5. **End on the biggest play**: the ace last, its final kill in bullet time on the last bass re-entry
   (level 3), then the ACE banner fading to black with the music. No zoom there.
6. Leave out the weakest kill rather than squeeze it onto a beat with no hit (v4 dropped one of 23).

## Music

1. `music_tempo.py`: tempo candidates (check half and double), loudness and bass per second, kick
   pattern per bar, and a list of bass re-entries after a gap: those are the drops. Pick the drop
   that is followed by about as much music as the material needs (v4: track beat 63 at 29.5 s; the
   re-entry at beat 132 became the place of the final kill).
2. `music_grid.py BPM BEAT0`: the true first-beat time. On the first project the comb fit was 38 ms
   early, which is more than two frames.
3. Number the beats so the section reads easily: `M0` = the track beat that becomes timeline beat 0
   (drop on track beat D: `M0 = D + 1`, so the drop is beat -1; v4: 64). `R0` = the first kill minus
   its lead-in (v4: -5.2, a 4.2-beat lead into the kill on the drop). `R1` = the last kill plus its
   tail plus 4 to 7 beats for the end card. `FADE_OUT` = the last 2 to 3 beats.
4. `music_pulses.py` lists the kicks (`low`) and the snares or claps (`mid`; v4: every 4 beats from
   beat 1); hats alone (`high` only) do not count. Kills go only on kicks and snares. Strong hits
   without a kill go into `PULSES` with a weight of 0.5 to 0.9. `music_spec.py` shows the same thing
   as a picture when a hit is unclear.
5. Use the structure: a breakdown before the drop carries the lead-in and a riser; a break near the end
   (v4: beats 63.3 to 68) carries the bullet time, with the music low-passed (`SWEEP`) and a second
   riser, both opening on the kill at the re-entry.

## Time

Anchors are `(beat, source frame)`; `FPB` (27.69) source frames per beat is real time.

- **A kill is an anchor**: `(kill beat, K)` with K the muzzle-flash frame from `kill_table.py`.
- **`lead(k, K, beats, fast=1.6)`** cuts in `beats` before the kill, fast-forwards, and settles to real
  time for the last half beat, so the shot itself plays at true speed. Typical: 0.9 to 2.2 beats,
  `fast` 1.25 to 1.6.
- **`tail(k, K, beats, rate=0.28)`** for a finisher: real time for 0.2 beat (through the recoil and
  the flash, which interpolate badly), slow motion at 0.28x, then 0.4 beat speeding back up to
  0.75x. Typical: 1.5 to 3.2 beats. At 0.75x the game sound is back (a little low in pitch): end the
  segment there with a cut, or pass `out_rate=0.3` if an overlapping transition follows, or the
  pitched sound runs on through the transition.
- **Continuous take**: one anchor per kill; add anchors around an ability to compress it (the dash
  and the fireball play at up to 4.6x between two kills).
- **Bullet time into a kill**: anchors that slow to about 0.15x over the last 4 beats and reach K
  exactly on the beat, as in the last kill of v4. That one arrives at 0.53x, so its flash builds over two
  frames; in a new edit add an anchor one frame before K at real time: `(k - 1/FPB, K - 1)`.
- After a normal kill keep 0.5 to 1.5 beats of real time before cutting, so the banner is seen.
- v4 as a whole: 46 % near real time, 28 % fast-forward, 26 % slow motion.

`$PY timeline.py` prints each segment's frame range and speed range and stops on the usual mistakes
(time running backwards, a gap between segments, a kill outside its segment, video longer than the
anchors). `ranges.py` reports anchors that reach outside a clip.

## Kill accents (`render.py`)

| | level 1 | level 2 finisher | level 3 (opening and final kill only) |
|---|---|---|---|
| zoom in, accelerating over the 0.7 beat before the kill | 12 % | 17 % | 21 % |
| after the kill | eases out over 1.3 beats | stays in until the segment ends | stays in until the segment ends |
| shake (damped, decays in 0.22 beat) | 5 px | 8 px | 12 px |
| roll | 0.25 deg | 0.4 deg | 0.7 deg |
| exposure pop (decays in 0.10 beat) | +0.55 | +0.9 | +1.5 |
| colour fringing (decays in 0.25 beat) | 0.35 % | 0.5 % | 0.8 % |
| backdrop pulse / window glow / light streaks | 0.5 / 0.5 / 0.10 | 0.8 / 0.8 / 0.22 | 1.2 / 1.3 / 0.40 |
| impact frame (inverted monochrome: a bright scene turns nearly black, a dark one nearly white; 1 frame + 1 frame at half) | | | yes |

Also: a `PULSES` hit gives a 1.2 % zoom punch, +0.12 exposure and a backdrop pulse, scaled by its
weight; `skill` ranges get a 6 % zoom swell and a little fringing; the total zoom is capped at 60 %.
The zoom accelerates into the hit and the shake is a damped oscillation, never random: that is what
made the zooms read as "natural" after the user's complaint.

Slow motion look (`bars=`, `push=`): the window narrows by up to 66 px at top and bottom (rounded
corners kept: this replaced black letterbox bars, which looked wrong inside a rounded window),
saturation drops 14 %, the backdrop dims 30 %, and the camera pushes in 7 to 20 % over the range.

## Layout and finishing

- Canvas 1080x1920. Window 1080x912 at y = 470, corners 34 px, showing 1280 of the 1920 source pixels
  in width at zoom 1 and its full height (two thirds of the game picture: crosshair, kill banner and
  most of the fight; minimap and kill feed are cropped). The store keeps 1344 px so zoom-outs and shake have margin.
- Backdrop: the footage reduced to 27x48 and blown up (a very soft blur), at 11.5 % brightness, pulsing
  with kills and `PULSES`, cross-fading between clips during transitions.
- Window stroke, halo and drop shadow; bloom from highlights above 0.62 (stronger on kills);
  saturation x1.16; vignette; gentle S-curve; light unsharp at encode; dither plus fine grain outside
  the window (kills banding in the backdrop).

## Transitions (`tin=` of the incoming segment)

| Kind | Length | Use | What it does |
|---|---|---|---|
| `zcut` | 0 | between kills of one clip or one scene | hard cut hidden by a zoom: outgoing clip zooms in 22 % over its last 0.3 beat, incoming zooms out from 18 % over 0.4 beat |
| `whip` | 0.7 beat, direction `(dx, dy)` | change of clip | both windows slide past, 3.5 deg tilt, motion-blurred; whoosh panned with the direction. `(1, 0)`: the new clip comes in from the right, `(-1, 0)` from the left, `(0, -1)` from the top, `(0, 1)` from the bottom |
| `spin` | 0.8 beat | once, into a new agent | outgoing spins 75 deg and zooms away, incoming unwinds |
| `zoom` | 0.6 to 0.7 beat | into a new scene | punches through the middle of one clip into the next (the cross-fade takes only 12 % of the length; longer reads as a dissolve) |
| `dissolve` / `soft` | 0.5 / 1.2 beats | into slow motion, into the end card | plain cross-fade |

An overlapping transition is centred on the first anchor of the incoming segment and needs footage of
both clips for half its length beyond the anchors (`ranges.py` accounts for it). Keep kills out of
it: the next kill should be at least 1.5 beats after the transition's centre. Vary direction and
kind; v4 uses 4 whips, 4 zcuts, 2 zooms, 1 spin, 1 dissolve and 1 soft.

## Sound

- The music carries the edit: `0.84 * music + 0.60 * game + effects`.
- Game sound is heard at real time only; it fades out between 0.7x and 0.25x and between 1.3x and
  1.8x. Kills of level 2 and 3 are always heard. `mute=True` silences a segment (v4: the end card).
  `FADE_OUT` fades music, game sound and effects together.
- `lag`: gunshots trail the picture by 1.4 to 3.3 frames in these recordings, and it varies per
  kill. With the measured value the shot lands within about 1 ms of the beat (`audio.py` prints it).
- A clip with talking: `voice=0.8` keeps natural pitch and lets the reaction run on through the slow
  motion. `stretch=True` keeps the pitch of in-game voice lines when a take runs off real time, but
  it can shift a gunshot by tens of ms when the speed at the kill is not exactly 1 (one trial: +32 ms).
  Use it only where `audio.py` still reports the kills of that segment on the beat.
- Risers (`RISERS`): filtered noise that climbs for about 4 beats and stops dead on the hit, at 0.13
  and 0.20 gain in v4. Whooshes on whip, spin and zoom transitions come by themselves.
- `SWEEP`: low-pass on the music from 18 kHz down to 620 Hz through the bullet time, opening 4 ms
  before the kill.

## Tried and dropped

- Full-height centre crop (one third of the game width): read as a permanent zoom.
- Slow motion by repeating or blending frames, and speed changes without interpolation: stutter.
- White flash between clips; random shake; strong RGB split; a window that jumps on every beat: the
  user asked for "mais suave" and "zoons mais naturais".
- A zoom on the final ACE banner.
- Black cinema bars over the rounded window.
- Game sound pitched down in slow motion: replaced by fading it out.

## Not done yet

Text on screen in the house style (the reference style has lyric words: `refstyle/textfx.py`); a kill counter;
impact sounds from a sound-effects pack; an editable CapCut project;
a neural beat tracker (the onset measurement was enough). See tools-research.md.
