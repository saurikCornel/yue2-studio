---
name: yue2-local-music
description: Generate songs locally with YuE2-3B on Apple Silicon.
---

# YuE2 local (mlx-Yue) on Apple Silicon

Agent-oriented notes for driving the local install: the paths that exist, what each command
costs, and the pitfalls that waste time. Human-facing documentation lives in
[`docs/`](../../docs).

## Installed layout

    ~/Projects/mlx-Yue/                     port + virtualenv + weights
    ~/Projects/mlx-Yue/models/converted/    vanch007/mlx-Yue2-3B (ar-8bit, ar-bf16, nar-bf16, qwen.tiktoken)
    ~/Projects/mlx-Yue/models/vae/          m-a-p/YuE2-Vae   (export LYRA_VAE=$PWD/models/vae)
    ~/Projects/mlx-Yue/models/transcription/  links to SheetSage2 and MERT2-FullSong
    ~/Projects/mlx-Yue/inputs/              source audio for covers
    ~/Projects/mlx-Yue/outputs/             <job>/ for songs, <job>/song/ for covers
    ~/Projects/yue2-studio/                 backend, UI, native app, patches

The official Hugging Face wheel (`yue2_infer`) is Linux + NVIDIA only. On a Mac the working
path is the MLX port; do not send anyone down the MPS route — `yue2_infer` pins torch 2.10,
whose BF16 `is_causal` attention leaks future keys on MPS (upstream issue #176, open).

## Generate

    cd ~/Projects/mlx-Yue && source .venv/bin/activate && export MLX_ENABLE_TF32=0 \
      && export LYRA_VAE="$PWD/models/vae" \
      && mlx-yue generate ~/Projects/yue2-studio/examples/english-song.json \
         --model models/converted --vae "$LYRA_VAE" --precision 8bit --offline \
         --vae-core-frames 128 --memory-budget-gib 16 --output outputs/<name>

Request JSON: `id`, `style` (English prompt works best), `lyrics` (section tags),
`cot` = full | melody | off, `seed`, optional `generation_config.ode_steps` and
`semantic_sampling.max_tokens`. The output directory must be absent or empty.

Measured on M5 Pro 24 GB: 16 s clip = 14 s; 200.7 s song = 336.8 s end to end (RTF 1.68),
peak footprint 10.4 GiB, zero swap. Stages: AR plan and semantics, then NAR synthesis (the
long part), then the VAE decode (~8 s). 8 steps roughly halves the wall clock.

## Pitfalls that cost time

- `--require-ac` aborts instantly on battery. Plug in, or drop the flag and record that the
  run was unplugged; never mix the two in one benchmark.
- Helper defaults: `transcribe` (and `music`) used to default `--memory-budget-gib` to 24,
  which the guard rejects on a 24 GB Mac (`budget <= total − 4`). The YUE2 Studio patch
  computes it from RAM; if you are on an unpatched checkout, pass 16 explicitly.
- A stale `outputs/<name>.resources.jsonl` makes the next run fail with `FileExistsError`.
  Delete `outputs/<name>.resources.json*` first.
- 24 GB machines need the memory-guard patch (level 2 is transient while macOS compresses
  the NAR weight load). Revert with `git checkout src/lyra/measure.py`.
- Covers keep artifacts in `<output>/song/` and `<output>/transcription/`; plain generations
  put `audio.flac` at the top of `<output>/`. Any scanner must check both levels.
- Transcription needs `--extra transcription` plus SheetSage2/MERT2-FullSong; with
  `--offline` the hub needs `refs/main` in the cache, so pass
  `--model models/transcription/sheetsage2 --base-model models/transcription/mert2-fullsong`.
- One GPU job at a time; the pipeline flock()s `/tmp/lyra-gpu-<uid>.lock` and a second job
  fails with "Another Lyra process owns the GPU".
- Avoid `rm -rf outputs/name*` in zsh scripts: an unmatched glob aborts the command.

## Verify before reporting success

- `result.json`: `status: complete`, `truncated.abc` and `truncated.semantic` false.
- `ffprobe`: 48 kHz stereo; `ffmpeg -af volumedetect`: `mean_volume` near −16 dB (not −91).
- Transcribe the mix with Whisper (`--language en --task transcribe`) and compare with the
  lyrics to confirm the vocal actually sings them.
- Keep the resource report (`outputs/<job>.resources.json`) when something fails: it holds
  footprint, available memory, pressure level and swap for every sample.

## Delivery

Convert to MP3 320k with `/opt/homebrew/opt/ffmpeg-full/bin/ffmpeg`, then:

    hermes send -t telegram "MEDIA:/abs/path/song.mp3" --json

Confirm the JSON returns a `chat_id` before claiming it was sent. Keep the FLAC local.

## Licenses

Port code Apache-2.0; YuE2 weights CC-BY-NC-4.0 (no commercial use).
