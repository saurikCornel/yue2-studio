# Quick start

Five minutes from a fresh install to a finished song.

## 1. Open the app

```bash
open "$HOME/Applications/YuE2 Studio.app"
```

The first launch takes about 10 seconds: the app starts the local engine in the background and
then loads the window. Prefer a browser? `python3 server.py` and open
http://127.0.0.1:8787.

## 2. Two things before you generate

- **Plug in the charger.** On battery, generation is significantly slower.
- **Close heavy apps** (Chrome, Electron, Safari) if you are going to render a full song: on a
  24 GB machine the memory margin is thin, and the app stops itself when memory runs out.

## 3. Create a song

1. **Create** tab.
2. **Style (prompt)** — English works best: genre + vocal + instruments + tempo + mood.
   Example: `Indie rock, English male lead vocal, jangly guitars, live drums, 92 BPM`.
3. **Lyrics** — use section tags: `[Verse]`, `[Chorus]`, `[Bridge]`. Four-line verses work
   best.
4. **Mode** — `full` (melody + chords, most control), `melody` (no chord symbols, best for
   covers), `off` (no symbolic plan).
5. **Steps** — 8 for a quick audition, 16 balanced, 32 standard quality.
6. **Seed** — leave it at 0. Same brief + same seed reproduces the same song; change the seed
   to explore variants.
7. Hit **Generate**. The Status panel shows phase, percentage, step counter and the engine log.
   - 8-step audition: about 1 minute.
   - Full 32-step song: 5–6 minutes for ~3:20 of music.
8. When it finishes: player, **Export MP3** (re-encodes on demand; the MP3 is already there in
   both cases), **Reveal in Finder**, **Score** (the ABC score).

## 4. Make a cover

1. **Cover** tab.
2. Drop an audio file (mp3, wav, flac, m4a) or click to pick one.
3. **Transcribe** — under 10 seconds, and it shows the detected melody as ABC.
4. Write the new style and lyrics.
5. **Generate cover**. The result lands in `outputs/cover-<source>/song/`.

Covers need the transcription models: install with `bash install.sh --with-transcribe`.

## 5. Where the files are

```
~/Projects/mlx-Yue/outputs/<name>/
    audio.flac    final audio, 48 kHz stereo (best quality)
    audio.mp3     320 kbps, written automatically when the run finishes
    score.abc     editable score
    result.json   status, duration, truncation flags
```

A cover writes the same files one level down, in `outputs/cover-<source>/song/`.

## Keyboard shortcuts

| | |
|---|---|
| ⌘R | reload the interface |
| ⌘⇧R | restart the engine |
| ⌘L | open the engine console |
| ⌘O | open the outputs folder |
| ⌘Q | quit (also stops the engine) |

## If something goes wrong

- "The backend did not respond within 60 s": app menu → Restart backend (⌘⇧R).
- A generation stopped halfway: close heavy apps and retry with 8 steps.
- Port 8787 busy: usually a stray engine; restart the app with ⌘⇧R.
- Nothing starts: open the console with ⌘L, the full error is there.
- One job at a time: two simultaneous generations will fail, the second one with
  "Another Lyra process owns the GPU".

Full detail: [TROUBLESHOOTING.md](TROUBLESHOOTING.md) and [USAGE.md](USAGE.md).

## Two things worth knowing

- The model weights are CC-BY-NC-4.0: personal or research use, no commercial use.
- Nothing leaves your Mac: generation, transcription and covers are fully local.

## Desktop launcher (optional)

To get a launcher icon on the Desktop, make an alias in Finder (right-click the app → *Make
Alias*, then drag it to the Desktop) or from the terminal:

```bash
osascript -e 'tell application "Finder" to make new alias file at (path to desktop folder) to (POSIX file "'"$HOME"'/Applications/YuE2 Studio.app")'
```
