---
name: editing-gameplay-montages
description: Use when asked to edit gameplay clips (Valorant, CS2, Fortnite, any shooter) into a highlight montage, frag movie or "edit" synced to music for TikTok, Reels or Shorts; when the editing of a reference video must be copied ("com a mesma edição desse vídeo", velocity edit, lyric words on screen); when adding slow motion, speed ramps, kill zooms, transitions, beat sync, lyric text or a cover image to gameplay with ffmpeg and Python; or when a rendered edit stutters, feels low-fps ("travado", "quedas de fps"), has choppy slow motion, kills off the beat, words out of sync or clipping sound. Also in Portuguese - "edita um vídeo", "faz um montage", "highlight", "edit pro TikTok", "faz uma capa".
---

# Editing gameplay montages

## Overview

A music-synced gameplay edit rendered by a custom Python pipeline. ffmpeg only decodes and encodes; time remapping, motion blur, camera moves, transitions, text, colour and sound are computed in Python from one file, `timeline.py`, written in beats of the music.

**Core principle: you cannot watch or hear the video, so nothing is done by feel.** Frames are addressed by index, beats are measured on the waveform, each kill is pinned to its muzzle-flash frame, and every render is judged by numbers and by images you read. Every shortcut around this produced a version the user sent back (pitfalls.md).

The bundled scripts are proven: from the first project's store they re-render its v4 with a bit-identical picture, an agent given only this skill produced a passing edit with them in one render, and the reference-style set is the one that rendered the second project's v3 (its sound comes out byte-identical). Copy them into the project and edit `timeline.py`; do not rewrite the pipeline from memory.

## First reply: the briefing

When this skill loads, the first reply is this message, in the user's language (Portuguese below) and in
the user's tone. Leave out an item their request already answers; if it answers everything, skip the
briefing and start. Then wait for the answer. After it, decide everything else alone.

> Bora fazer esse edit! Antes de eu começar, me conta:
>
> 1. **O que você quer**: vertical (TikTok, Reels, Shorts) ou horizontal (YouTube)? Quanto tempo, uns 15, 30 ou 45 segundos? Mais intenso ou mais suave? Quer a letra da música na tela? Quer capa?
> 2. **As jogadas**: quais são as melhores, e qual você quer abrindo e fechando o vídeo? Tem alguma que não pode faltar ou que você não curte?
> 3. **A música**: qual arquivo, e se quiser, qual parte (por exemplo "o drop em 0:45").
> 4. **O jogo**: Valorant, CS2 ou outro?
>
> Dicas para ficar top:
> - **Coloque um vídeo de referência na pasta**: um edit que você curtiu, baixado do TikTok ou do YouTube. Eu copio os cortes, o ritmo, os efeitos e o texto dele; é o jeito mais certeiro de chegar no estilo que você imagina.
> - **Clipes**: o ideal é 1920x1080 ou mais, a 60 fps ou mais (ShadowPlay, Outplayed, OBS, Medal), com uns segundos antes e depois de cada jogada. Gravação crua de alguns minutos também serve, eu acho as kills.
> - **Música** em boa qualidade: .flac, .wav ou .mp3 320k.
> - Tudo na mesma pasta. Eu crio uma pasta `_editor` lá dentro para o projeto (reserve de 7 a 13 GB livres).
>
> Depois disso eu decido o resto sozinho e te entrego cada versão como um arquivo novo, sem apagar nada seu.

Defaults for anything left unanswered: vertical house style, about 30 s, intensity as the examples, no
text on screen, no cover, the section and plays you judge best. With a reference video in the folder:
the reference style, artist and title as intro words, lyric words only if every line was confirmed
(reference-style.md, "Lyric words"). The vertical house style has no text renderer (edit-design.md, "Not
done yet"): lyric words there mean the reference style's horizontal format, or no text; say which in the
report. Write the answers and the defaults taken into the project's `LEIAME.md`.

## Which style

| The user gives | Style | Read |
|---|---|---|
| a reference video ("mesma edição desse vídeo") | reference style: full-frame gameplay, blur-in cuts on the beat, lyric words, luma fade. Its OUTPUT is 1920x1080 at 60 fps (sources of any size and rate are fine: `ingest.py`); a vertical or other-size reference: reference-style.md, "Another frame size or rate" | reference-style.md; `scripts/` plus `scripts/refstyle/` |
| clips and a song, no reference | house style, below (the user on its v3: "PERFEITO, mas ... ainda sinto umas quedas de fps"; v4 removed the stutter) | edit-design.md; `scripts/` |

Not for: plain trimming, joining or converting (use ffmpeg directly); edits the user wants to keep adjusting by hand in an editor (tools-research.md).

## House style

- 1080x1920, 60 fps. Gameplay in a wide rounded window over a blurred backdrop of the same footage that pulses with the beat.
- Every kill on a measured kick or snare, with its gunshot heard on that beat.
- Zoom, shake and flash are short accents on kills. Slow motion only as a finisher, with real motion blur. Inside a take, speed ramps replace cuts.
- Transitions move both clips (whip, spin, zoom-through). No white flashes. Every transition lands on a kick / bass hit, never on a snare alone.
- Intense but smooth: stutter is the defect this user notices first.

## What this user wants, in their words

These hold in BOTH styles and outrank a reference video where the two disagree.

| Rule | Their words |
|---|---|
| No standing zoom: never a crop or zoom that enlarges the gameplay for a whole shot, not even to hide the HUD. Short accents that ease in and out were accepted, each style with its own values: house (windowed) kill zooms of 12 to 21 %, edit-design.md; reference (full frame) a push-in of 3.5 % per take and a kill punch under 5 %, reference-style.md | "voce deixou um zoom no video todo ... fica estranho"; "no comeco aquele zoom ta mt feio" |
| Nothing may stutter; slow motion perfectly smooth | "o slow motion ta bem travadinho"; "sinto umas quedas de fps" |
| Kills exactly on the beat | "da pra sincronizar melhor" |
| Transitions on the bass (kick, 808), not on the snare; snares carry the accents inside a take (zoom punch, shake, a kill). Both styles. Measured: the delivered v4 had 0 of 13 transitions on a kick, v3 19 of 57 | an editor's note the user adopted: "bota no prompt para as trasições rolarem nos graves da música, não no snare. acho que vai ficar mais fino" |
| The ending only darkens: no zoom on the ace | "no fim nao de um zoom no ace apenas deixe a tela escurecer" |
| Words on screen are translucent | "as letras estavam sem transparencia alguma 100% solidas" |
| Words sit in the exact middle of the screen | "tem que centralizar a letra no meio da tela" |
| Words follow the voice one by one | "tentar sincronizar ao maximo as letras da tela" |
| No label, subtitle or watermark: only the song's words (artist and title as intro words passed without comment) | "tira esse valorant edit da tela" |
| "Bonito" = a clean kill at a distance, not the biggest flick | "aquela kill da raze, é muito feia" (point-blank, explosion over the screen) |
| After the briefing, decide alone and report afterwards: no questions in the middle of the work | "nao me pergunte NADA"; "apenas faça o que voce decidir" |
| When they say they will play, stop every heavy job at once (how: pipeline.md, "Handling jobs on this PC") | "consegue renderizar dps ?vou jogar agora" |

## Workflow

`PY=./venv311/Scripts/python`, in Git Bash, from the project folder `<clips folder>/_editor/`. Every Bash call starts in a fresh shell, so begin each command with `cd "<project>" && PY=./venv311/Scripts/python &&`. Setup commands, script table and timings: pipeline.md.

0. **Briefing**: the first reply is the briefing message ("First reply: the briefing", above). Wait for the answer, then list the folder and decide the rest alone.
1. **Project**: copy the scripts and `models/` (pipeline.md, "Setup"), create the venv, write `clips.json`, then `$PY ingest.py && $PY mkpts.py`. `ingest.py` accepts any size and frame rate (1440p, 4K, 4:3 stretched, 21:9, 30 to 240 fps) and makes 1920x1080 60 fps working copies; everything after it assumes that format.
2. **Reference style only**: dissect the reference frame by frame and write the findings to a notes file (reference-style.md).
3. **Watch the clips and find the kills**. `$PY peek.py c1 0 99999 60` shows a clip at one tile per second. Any game: `$PY kills_auto.py <game>` (profiles in `games/`: `valorant`, `cs2`, `generic`; another game: copy `generic.json` to `games/<game>.json` and set its rectangles with `--regions`) writes `kills.json` and review sheets `autokill_NN.jpg`. The `cs2` profile comes from the game's HUD files and was never run on footage: run `--regions` on a frame with a kill first, and trust nothing before its sheets confirm it. Valorant also has the banner tools for trimmed clips (`find_kills.py`, `kill_table.py`) and the kill-feed + ammo tools for raw recordings (reference-style.md, "Finding kills in raw 2-minute recordings"). Confirm on the sheets that each kill is the player's and that its flash starts on tile K (`+0`), absent on K-1. Choose clean kills by reading the stills.
4. **Music**: `$PY music_tempo.py` (tempo, candidate drops), then `$PY music_grid.py BPM BEAT0` (never skip: the first guess is tens of ms early). Fill in the music block at the top of `timeline.py` (`MUSIC`, `BPM`, `BEAT0`, `M0`, `R0`, `R1`, `FADE_OUT`, and what is tied to the song's structure: the `RISERS` beats, in the house style `SWEEP` and `PULSES`, in the reference style `LUMA_FADE`; choosing the section: edit-design.md "Music", valid for both styles; the example's segments can stay for now), then read the hits with `$PY music_pulses.py` and `$PY music_spec.py`. Lyric words: reference-style.md.
5. **Write `timeline.py`** from `timeline_example.py` (edit-design.md) or `timeline_ref_example.py` (reference-style.md): best moments on the drops, the plays the user named where they asked, kills as anchors on measured hits, every transition on a kick / bass hit. `$PY timeline.py` must pass, and `$PY music_pulses.py` must print "none" for kills on empty beats (house style) and for transitions not on a kick (both styles).
6. **Footage**: `$PY ranges.py && $PY prep.py ranges.json` (GPU, in the background), `$PY densify.py run 12 28`, reference style also `$PY posmap.py`, then `$PY check_store.py` (0 missing, no duplicates).
7. **Stills before video**: `$PY render.py N N+1 look.jpg` on each kill, transition, slow-motion frame, word, first and last second; read them (stills can start while `prep.py` still runs; reference style: after one `$PY posmap.py`). Reference style: enlarged crops of your stills beside the same crops of the reference BEFORE the first full render (verification.md).
8. **Sound**: house style: `$PY kill_lags.py` for each segment's `lag`, then `$PY audio.py` must put each shot within a few ms of its beat, or you must be able to explain the number (verification.md, "Sound"). Reference style: `$PY audio.py` says how each gunshot was placed (measured, clip offset, none) and must print a `mix peak` below 1.0.
9. **Render** in the background: `bash run.sh master.mp4` (12 to 16 min).
10. **Verify**: `$PY check.py master.mp4 --sheets`, read `sync_*.jpg` (flash absent on `-1`, starting on the tile the printed table names) and `pv_*.jpg`. Fix and repeat (verification.md).
11. **Deliver**: `bash deliver.sh master.mp4 "../<name>_vN.mp4"`, never over an earlier version; run `check.py` on that file.
12. **Save what was learned** in this skill and in the session's memory directory before the final report; leave a `LEIAME.md` in the project.

## Rules, and what happened without them

| Rule | Without it |
|---|---|
| Read frames by index (`clipio`), never `-ss` plus an `fps` filter | 1 frame in 3 duplicated or dropped: "travado", "quedas de fps" |
| Refine the beat grid with `music_grid.py` | grid 38 ms early, kills beside the hits |
| The beat gets the muzzle-flash frame; the gunshot is placed on the same beat (`lag`, or per-kill shots in the reference style) | a kill 4 frames late |
| Any speed other than 1 comes from interpolated sub-frames, shutter-integrated | "slow motion ta bem travadinho" |
| Sub-frames are built through `rifeutil.Tween` (the bundled scripts do); a store built without it, as both projects' first stores were, needs `fixends.py` | slow motion stalled an eighth of a frame at every real frame |
| Recording duplicates are rebuilt before interpolating (`prep.py`, `repair.py`) | slow motion freezes on them |
| Real time for 0.2 to 0.3 beat after the shot before slowing (`tail()`, `post()`) | slow motion sat on the flash and magnified artifacts |
| A slow lead-in reaches the kill at real speed: one anchor a frame before it (reference-style `L` entries add it; the house example's bullet time predates the rule and arrives at 0.53x) | the flash appeared 2 frames after the beat |
| Judge a reference's look on enlarged crops, not contact-sheet tiles | letters drawn 90 % opaque when the reference's were see-through |
| Rank kills by reading stills; camera travel is only a hint | the biggest "flick" was the kill the user called ugly |
| One word per cue on its measured vocal onset; only lyric lines confirmed against a lyrics page | phrases appeared before they were sung; speech recognition gets half a trap verse wrong |
| AAC with `-aac_pns 0 -aac_tns 0 -aac_is 0` after the limiter; check the decoded peak | three deliveries clipped at +3 dBFS |
| Sound files keep headroom until the limiter | a 16-bit mix flattened 0.05 % of v4's samples before the limiter saw them |
| Stills first; long jobs in the background with short status notes | flaws found only after a 12-minute render; the user interrupted a long blocking wait |
| A GPU job that slows down: look for the user's game before touching the code (commands: pipeline.md, "Handling jobs on this PC") | an hour of interpolation at an eighth of the speed while CS2 ran |
| Before overwriting a file of this skill, read its current version: another session may have updated it | a newer `rifeutil.py` (with `finish()`) was replaced by an older copy and two scripts broke |

## Reporting to the user

Reply in the user's language (the original user: Brazilian Portuguese, informal). Lead with the file path and its state. Say what changed, give the measured facts, and state plainly that you cannot watch or hear it, so feel, intensity and mix are theirs to judge. End by saying they can describe in their own words anything to change. No questions after the briefing: decide, and never need a confirmation, by not deleting or overwriting anything of theirs. Answer a message that arrives mid-run in the next line you write.

## Files

| File | Read it when |
|---|---|
| pipeline.md | setting up, running or modifying the scripts; timings; what to re-run after a change |
| edit-design.md | house style: sequence, beats, speed ramps, effect values, transitions, sound |
| reference-style.md | copying a reference video; raw recordings; lyric words; cover image |
| verification.md | judging a render; thresholds; reading the sheets; the report |
| pitfalls.md | something looks or measures wrong (symptom, cause, fix), including shell traps on this machine |
| tools-research.md | the user asks about other editors, MCPs or skills |
| scripts/, models/ | the pipeline (house style, plus the tools both styles share) and the interpolation network |
| scripts/refstyle/ | files that replace or extend `scripts/` for the reference style (README.md inside) |
