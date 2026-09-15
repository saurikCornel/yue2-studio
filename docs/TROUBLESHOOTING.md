# Known issues and fixes

Every error in this list came from a real installation. Messages are quoted verbatim so you
can search for them.

## The doctor fails with "missing or unexpected files"

```
"model": {"error": "Converted directory has missing or unexpected files: unexpected=['.cache/...', '.gitattributes']"}
```

`snapshot_download` leaves its cache and `.gitattributes` inside the model directory, and the
doctor treats them as unexpected files.

```bash
cd ~/Projects/mlx-Yue
rm -rf models/converted/.cache models/vae/.cache models/converted/.gitattributes models/vae/.gitattributes
```

## "AC power is required for an acceptance benchmark"

`--require-ac` refuses to start on battery. Either plug in the charger or drop the flag:

```bash
./.venv/bin/mlx-yue generate ... --offline --output outputs/song   # no --require-ac
```

Record that the run was on battery — do not mix those numbers with plugged-in benchmarks.

## "Resource evidence already exists: outputs/<job>.resources.jsonl"

A previous run left the evidence file behind and the next one refuses to overwrite it.

```bash
rm -f outputs/<job>.resources.json outputs/<job>.resources.jsonl
```

## "System memory pressure is not normal (level=2)"

The port's guard aborting on a transient macOS warning. This is exactly what patch 1 fixes —
see [PATCHES.md](PATCHES.md). If you still see it **with** the patch applied, the pressure is
real: close heavy apps, lower `--vae-core-frames` to 64, or run with `--precision 8bit`.

## "Memory budget must exceed 5 GiB and leave 4 GiB OS headroom"

The transcription helper defaults `--memory-budget-gib` to 24 while the guard requires
`budget <= RAM − 4` (20 on a 24 GB machine). Patch 2 fixes the default; you can also pass it
explicitly:

```bash
./.venv/bin/mlx-yue transcribe audio.wav --task melody-full --memory-budget-gib 16 ...
```

## "LocalEntryNotFoundError: Cannot find an appropriate cached snapshot folder"

Transcription with `--offline` cannot find the weights because the hub cannot resolve a
snapshot by revision without `refs`. Fix it by creating the ref, or by pointing at the
directories:

```bash
# option A: ref inside the cache (install.sh does this)
printf 'eab522a8168e8b8b8c4856bf8609cd86198f01fe' > \
  ~/.cache/huggingface/hub/models--m-a-p--SheetSage2/refs/main

# option B: pass the directories explicitly
./.venv/bin/mlx-yue transcribe audio.wav --task melody-full \
  --model models/transcription/sheetsage2 --base-model models/transcription/mert2-fullsong ...
```

## "Another Lyra process owns the GPU"

Another job is running (or a process is stuck). One GPU job at a time:

```bash
pgrep -fl "mlx-yue"        # see what is running
pgrep -fl "[s]erver.py"    # or whether the app backend is mid-job
```

The lock lives in `/tmp/lyra-gpu-<uid>.lock` and is released when the process exits.

## Port 8787 is taken, or the app is stuck on "the backend did not respond"

Almost always a stray backend:

```bash
pgrep -fl "[s]erver.py" && pkill -f "[s]erver.py"
open "$HOME/Applications/YuE2 Studio.app"
```

The app also has **⌘⇧R** to restart its own backend.

## MP3 export fails or sounds wrong

The plain Homebrew ffmpeg does not always ship every codec. The project prefers `ffmpeg-full`
when present:

```bash
brew install ffmpeg-full        # lands in /opt/homebrew/opt/ffmpeg-full/bin/ffmpeg
```

The backend picks that binary automatically. The MP3 is written next to the FLAC (`audio.mp3`)
when a run finishes — for covers that is `<output>/song/audio.mp3`. When it is missing, the
encode failed: the app reports "no audio.flac found, or ffmpeg failed to encode", which means
either a failed run (no FLAC) or a broken ffmpeg install.

## Transcription fails with `FileNotFoundError: [Errno 2] ... 'ffmpeg'`

Only transcription (and covers, which transcribe first) shells out to `ffmpeg`: upstream's
`lyra/transcription/pipeline.py` decodes the source audio with a bare `ffmpeg` command, so
it dies before the model is loaded. `generate` never calls it, which is why songs still work.

The usual trigger is opening the app from the Finder or the Dock: a `.app` launched that way
inherits launchd's minimal `PATH` (`/usr/bin:/bin:/usr/sbin:/sbin`), where Homebrew binaries
are missing. The app adds `/opt/homebrew/bin`, `/opt/homebrew/opt/ffmpeg-full/bin`,
`/usr/local/bin` and `/opt/homebrew/sbin` to the backend environment, and the backend merges
the same directories (plus the project's `.venv/bin`) into the `PATH` of every job it spawns.
To check what the running backend sees:

```bash
curl -s http://127.0.0.1:8787/api/health | python3 -c 'import json,sys; d=json.load(sys.stdin); print(d["ffmpeg"], d["ffmpeg_ok"])'
```

`"ffmpeg_ok": false` means no usable binary was found — `brew install ffmpeg`. If you run
`mlx-yue transcribe` by hand from a shell that has no Homebrew on `PATH`, use the absolute
path (`export PATH="/opt/homebrew/bin:$PATH"`).

## Transcription is very slow, or will not start

- Pass `--max-seconds 180` to transcribe only the first stretch (the UI does this).
- SheetSage2 + MERT2 in MLX need roughly 3 GB of extra RAM.
- Check the extras are installed: `uv sync --frozen --no-dev --extra transcription`
  (missing `scipy`/`mido`/`mir_eval`/`pretty_midi` makes the helper fail on startup).

## A song is incomplete, or reports "truncated"

Look at `outputs/<job>/result.json`:

- `"status": "complete"` and `"truncated": {"abc": false, "semantic": false}` — full song.
- `"truncated": {"semantic": true}` — `max_tokens` ran out before the end (the default is
  9000, enough for 3–4 minutes; raise it in the request for longer pieces).
- Any other `"status"` — the run did not finish; the log in the Status panel says why.

## "zsh: no matches found"

Not a project issue: zsh aborts the command when a glob matches nothing
(`rm -rf outputs/something*` with no match). Quote it or use `setopt NULL_GLOB`:

```bash
rm -rf outputs/something* 2>/dev/null || true
```

## The audio came out silent or cut short

Verify without listening:

```bash
ffprobe -v error -show_entries format=duration -show_entries stream=sample_rate,channels \
  -of default=noprint_wrappers=1 outputs/<job>/audio.flac
ffmpeg -hide_banner -nostats -i outputs/<job>/audio.flac -af volumedetect -f null - 2>&1 | grep volume
```

Expect 48000 Hz, 2 channels and a `mean_volume` around −16 dB. A level near −91 dB is
silence: check that the lyrics are not empty and that the style prompt describes something.

To confirm the vocals actually sing the requested lyrics, transcribe the mix with Whisper
(if installed; `pip install openai-whisper`):

```bash
whisper outputs/<job>/audio.flac --model large-v3-turbo \
  --language en --task transcribe --output_dir /tmp/check --output_format txt --fp16 False
```

The transcript should match the lyrics you wrote (allowing for Whisper's spelling). If it
returns noise, the song failed: try another seed or shorten the verses.
