---
name: yue2-local-music
description: Generate songs locally with YuE2-3B on Apple Silicon.
---

# YuE2 local (mlx-Yue) on Apple Silicon

The upstream Hugging Face wheel (`yue2_infer`) is Linux + NVIDIA CUDA only. On a Mac the working path is the
community MLX port `github.com/vanch007/mlx-Yue` (Torch-free, 8-bit AR, Metal SDPA). Do not send the user down the
MPS route: `yue2_infer` pins torch 2.10, whose BF16 `is_causal` attention silently leaks future keys on MPS
(upstream issue #176, open).

## Installed layout on this machine

    ~/Projects/mlx-Yue/            # git checkout (uv env in .venv, python 3.12)
    ~/Projects/mlx-Yue/models/converted/   # vanch007/mlx-Yue2-3B  (ar-8bit, ar-bf16, nar-bf16, qwen.tiktoken)
    ~/Projects/mlx-Yue/models/vae/         # m-a-p/YuE2-Vae  (export LYRA_VAE=$PWD/models/vae)
    ~/Projects/mlx-Yue/tools/PATCH-24GB.md # local guard patch, documented
    ~/Projects/mlx-Yue/examples/cancion-es.json  # working Spanish full-song request

Setup if missing: `git clone`, `uv sync --frozen --no-dev` (NOT plain `uv sync`, it pulls the dev group),
`uv pip install --python .venv/bin/python hf_transfer` for a fast weight pull, then `snapshot_download` of both
repos into `models/converted` and `models/vae` (~10.4 GB total). Then delete `models/*/.cache` and
`models/*/.gitattributes`, otherwise `mlx-yue doctor` reports "missing or unexpected files".

## Generate a song

    cd ~/Projects/mlx-Yue && source .venv/bin/activate && export MLX_ENABLE_TF32=0 \
      && export LYRA_VAE="$PWD/models/vae" \
      && mlx-yue generate examples/cancion-es.json --model models/converted --vae "$LYRA_VAE" \
         --precision 8bit --offline --vae-core-frames 128 --output outputs/<name>

Request JSON: `id`, `style` (English prompt works best), `lyrics` (section tags, plain ASCII or UTF-8),
`cot` = full | melody | off, `seed`. Defaults: semantic `max_tokens` 9000 (keep it for full songs), acoustic
32 midpoint steps (64 evaluations). Output dir must be absent or empty.

Measured on M5 Pro 24 GB: 16 s clip = 14 s; 200.7 s song = 336.8 s end to end (RTF 1.68), peak footprint
10.4 GiB, zero swap. Stages: AR plan/semantic, then NAR synthesis (the long part), then VAE decode (~8 s).

## Pitfalls that cost time

- `--require-ac` aborts instantly on battery ("AC power is required for an acceptance benchmark"). Plug in the
  charger, or drop the flag and record that the run was unplugged. Never mix the two groups in one benchmark.
- The `transcribe` and `music` helpers default `--memory-budget-gib` to 24, which the guard rejects on a 24 GB Mac
  (it requires `budget <= total - 4` = 20). Always pass `--memory-budget-gib 16`; the default was locally patched
  to 16 in `src/lyra/music_tools/transcribe.py`.
- Transcription needs its extras and two extra checkpoints (SheetSage2 218 MB + MERT-v2-FullSong 2.4 GB, ~2.6 GB):
  `uv sync --frozen --no-dev --extra transcription` then `snapshot_download` of `m-a-p/SheetSage2` and
  `m-a-p/MERT-v2-FullSong` (pinned revisions in `src/lyra/transcription/model.py`). With `--offline` the hub cache
  lookup fails unless `refs/main` exists, so symlink the snapshots into the project and pass them explicitly:
  `--model models/transcription/sheetsage2 --base-model models/transcription/mert2-fullsong`. 16 s of audio
  transcribes in ~6 s.
- `mlx-yue cover` writes the song into `<output>/song/` with the transcription in `<output>/transcription/`;
  plain `generate` writes `audio.flac` at the top of `<output>/`. Any library/scan code must check both levels.
- A stale `outputs/<name>.resources.jsonl` makes the next run die with `FileExistsError`. Delete
  `outputs/<name>.resources.json*` before rerunning.
- 24 GB machines: the port's guard aborts on any memory-pressure reading above level 1, and macOS raises a
  transient level 2 while compressing the multi-GB NAR weight load even with ~6 GiB available. Local fix in
  `src/lyra/measure.py::GPUExecutionGuard._check_sample`: tolerate level 2 while `system_available_bytes`
  >= 4 GiB (keep the <2 GiB, footprint-budget and swap checks strict). Evidence and revert instructions in
  `tools/PATCH-24GB.md`. `git checkout src/lyra/measure.py` reverts it.
- Only one GPU job at a time; the pipeline flock()s `/tmp/lyra-gpu-<uid>.lock` and fails otherwise.
- Verify artifacts before claiming success: `result.json` (`status: complete`, `truncated`), FLAC 48 kHz stereo
  via ffprobe, non-silent via ffmpeg volumedetect, and transcribe the mix with Whisper (`--language es
  --task transcribe`) to confirm the vocals actually sing the requested lyrics.
- Weights are CC-BY-NC-4.0 (non-commercial); port code is Apache-2.0.

## Studio app (macOS)

`~/Projects/yue2-studio/` wraps the CLI in a local app: `server.py` (stdlib backend, 127.0.0.1:8787, one GPU job at
once, Range-capable file serving), `ui/index.html` (dark minimal UI: Crear / Cover / Biblioteca / Ajustes),
`app/main.swift` (WKWebView wrapper that starts the backend) and `build_app.sh` (compiles `YuE2 Studio.app` into
`~/Applications`). Run it from a terminal with `/usr/bin/python3 server.py`, or install the bundle. The backend
config lives in `config.json` (project, vae_core_frames, precision, memory_budget_gib, transcription paths).

## Delivery

Convert to MP3 320k with `/opt/homebrew/opt/ffmpeg-full/bin/ffmpeg` and send with minimum caption:

    hermes send -t telegram "MEDIA:/abs/path/song.mp3" --json

Confirm the JSON returns a `chat_id` before saying it was sent; the FLAC stays local.
