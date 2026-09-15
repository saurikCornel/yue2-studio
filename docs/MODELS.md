# Models and licenses

This repository ships no weights: the installer downloads them from Hugging Face. Here is
what each piece is, how large it is and under which license.

## Generation

| Piece | Repo | Size | License |
|---|---|---|---|
| AR generator (bf16) | `vanch007/mlx-Yue2-3B` → `ar-bf16.safetensors` | 4.33 GB | CC-BY-NC-4.0 |
| AR generator (int8) | `vanch007/mlx-Yue2-3B` → `ar-8bit.safetensors` | 2.66 GB | CC-BY-NC-4.0 |
| NAR (flow matching, bf16) | `vanch007/mlx-Yue2-3B` → `nar-bf16.safetensors` | 2.93 GB | CC-BY-NC-4.0 |
| Tokenizer | `vanch007/mlx-Yue2-3B` → `qwen.tiktoken` | 2.5 MB | — |
| 48 kHz stereo VAE | `m-a-p/YuE2-Vae` → `model.safetensors` | 507 MB | CC-BY-NC-4.0 |

Total: **~10.5 GB**. The AR model ships in two precisions: `8bit` (faster and lighter, what
the app uses) and `bf16` (precision reference). NAR and VAE are always bf16/FP32.

These are the MLX port's weights (`vanch007/mlx-Yue2-3B`), already converted from the
originals at `m-a-p/YuE2-3B`; they are smaller because the AR is quantized and because only
the parts inference needs were extracted.

## Transcription and covers (optional, +2.6 GB)

| Piece | Repo | Size | License |
|---|---|---|---|
| SheetSage2 (audio → score) | `m-a-p/SheetSage2` | 218 MB | CC-BY-NC-4.0 |
| MERT2-FullSong (music encoder) | `m-a-p/MERT-v2-FullSong` | 2.4 GB | CC-BY-NC-4.0 |

Pinned revisions live in the port's `src/lyra/transcription/model.py`: the installer fetches
those exact commits, not `main`.

## License of what you generate

The weights are **CC-BY-NC-4.0**: research and personal use, **not commercial**. Anything you
generate inherits that restriction. For commercial use, check the terms published by M-A-P and
by Tokenwave.AI (which provided most of the synthetic training data).

## What this project does not use

- Nothing from the CUDA path: `yue2_infer` (the official package) is Linux + NVIDIA GPU. On
  macOS it has MPS branches, but it pins `torch==2.10.0`, whose BF16 causal attention is broken
  on MPS (it leaks up to three future keys, with no error and no NaN; issue #176 in
  `multimodal-art-projection/YuE`).
- PyTorch at runtime: the port is pure MLX. Torch only appears in development tests.

## Verify what you downloaded

```bash
cd ~/Projects/mlx-Yue
MLX_ENABLE_TF32=0 ./.venv/bin/mlx-yue doctor --model models/converted --vae models/vae --verify-hashes
```

`--verify-hashes` compares SHA-256 against the ones shipped with the package. Reference
sizes: `ar-8bit` 2,656,158,264 bytes, `ar-bf16` 4,331,951,136, `nar-bf16` 2,929,490,456, VAE
530,512,720.
