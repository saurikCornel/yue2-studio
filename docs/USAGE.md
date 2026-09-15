# Usage: workflows and how to ask for good music

## The app

### Create

1. **Style prompt**: English works best. Genre + instrumentation + vocal type + tempo + mood.
   Real example:
   `Argentine rock, Spanish male lead vocal, jangly electric guitars, live bass and drums,
   mid tempo 92 BPM, big anthemic chorus`.
2. **Lyrics**: use section tags, the model follows them:
   `[Intro]`, `[Verse]`, `[Pre-Chorus]`, `[Chorus]`, `[Bridge]`, `[Outro]`.
   Four-line verses and a repeated chorus produce the most coherent songs.
3. **Mode**: `full` (melody + chords, the most control), `melody` (no chord symbols, best for
   covers), `off` (no symbolic plan).
4. **Steps**: 32 standard, 8 fast, 16 in between.
5. **Seed**: same style + lyrics + seed reproduces the same song. Change the seed to explore
   variants of the same brief.
6. **Generate**. The Status panel shows phase, percentage, step counter and the CLI log live.
   When it finishes: player, **Export MP3**, **Reveal in Finder**, **Score**.

### Cover

1. Drop an audio file (wav, flac, mp3, m4a…) or click to pick one. It is stored in
   `<project>/inputs/`.
2. **Transcribe**: SheetSage2 + MERT2 extract the melody (plus rhythm, key and structure) and
   show it as ABC. It transcribes the first 180 seconds by default.
3. Write the new style and the new lyrics.
4. **Generate cover** in `melody` mode.

The result lands in `outputs/cover-<source>/song/`, with the transcription next to it in
`outputs/cover-<source>/transcription/`.

### Library

Lists everything under `<project>/outputs/`: songs, covers and transcriptions, with duration,
mode, seed, a player, MP3 export, Finder reveal, score viewer and delete.

## The same thing from the CLI

```bash
cd ~/Projects/mlx-Yue
export MLX_ENABLE_TF32=0 LYRA_VAE="$PWD/models/vae"
PY=./.venv/bin/mlx-yue

# full song
$PY generate ~/Projects/yue2-studio/examples/english-song.json \
    --model models/converted --vae "$LYRA_VAE" --precision 8bit --offline \
    --vae-core-frames 128 --memory-budget-gib 16 --output outputs/song

# plan only (ABC + tokens), no audio
$PY plan ~/Projects/yue2-studio/examples/english-song.json \
    --model models/converted --output outputs/plan

# with your own score
$PY generate ~/Projects/yue2-studio/examples/english-song.json --abc my-score.abc --mode full \
    --model models/converted --vae "$LYRA_VAE" --offline --output outputs/song-abc

# transcribe
$PY transcribe inputs/song.wav --task melody-full \
    --model models/transcription/sheetsage2 --base-model models/transcription/mert2-fullsong \
    --output outputs/transcription --offline --memory-budget-gib 16

# end-to-end cover
$PY cover --audio inputs/song.wav --style "Jazz-funk, warm lead vocal, Rhodes" \
    --lyrics-file new-lyrics.txt --task melody-full --mode melody \
    --model models/converted --vae "$LYRA_VAE" --offline --memory-budget-gib 16 \
    --output outputs/cover-song
```

Request JSON format (see `examples/english-song.json`):

```json
{
  "id": "my-song",
  "style": "genre, vocals, instruments, tempo, mood",
  "lyrics": "[Verse]\n...\n[Chorus]\n...",
  "cot": "full",
  "seed": 15092026,
  "generation_config": { "ode_steps": 32 },
  "semantic_sampling": { "max_tokens": 9000 }
}
```

`generation_config` also accepts `temperature`, `top_p`, `top_k` and `repetition_penalty`
(inside `abc` and `semantic`), and the request accepts `cfg_scale` (1.0–1.2) to follow the text
more closely.

## What to expect

- **Length**: the model decides from the lyrics. A verse plus a chorus gives about 1:15; a
  song with a bridge and a repeated chorus runs about 3 minutes. `max_tokens: 9000` is enough
  for roughly 4 minutes.
- **Quality**: the vocal sings the lyrics intelligibly (verified by transcribing the mix with
  Whisper and getting the lyrics back). Choruses tend to be the strongest part; verses with too
  many syllables in a row get crowded.
- **Score editing**: there is no score editor in the UI, but the file is right there — edit
  `score.abc` in the output directory and regenerate by passing it with `--abc`.

## Recipes

- **Quick audition**: 8 steps, short lyrics (one verse and one chorus). Under a minute.
- **Compare variants**: same brief, different seed; or the same seed and one single change
  (style or lyrics).
- **Fix a song**: run `plan` to get the ABC, edit it, regenerate with `--abc`.
- **Instrumental**: `off` mode with empty lyrics and a style that says "instrumental".
- **Export**: the MP3 button in the app (320 kbps), or by hand:
  `ffmpeg -i audio.flac -c:a libmp3lame -b:a 320k audio.mp3`.
