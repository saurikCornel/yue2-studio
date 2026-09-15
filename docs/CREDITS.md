# Credits and third-party licenses

This repository (installer, backend, UI, native app and patches) is **MIT** — see
[LICENSE](../LICENSE).

## Projects this depends on

| Project | Author | License | What it provides |
|---|---|---|---|
| [mlx-Yue](https://github.com/vanch007/mlx-Yue) | vanch007 | Apache-2.0 | Native Apple Silicon port of the YuE2 pipeline: AR planner, NAR flow matching, VAE, transcription |
| [YuE / YuE2](https://github.com/multimodal-art-projection/YuE) | Multimodal Art Projection (M-A-P) | Apache-2.0 (code) | Original model, official pipeline, reference weights |
| [MLX](https://github.com/ml-explore/mlx) and [MLX-LM](https://github.com/ml-explore/mlx-lm) | Apple | MIT | Metal inference framework |
| [stable-audio-tools](https://github.com/Stability-AI/stable-audio-tools) | Stability AI | MIT | VAE architecture (Oobleck) |
| [SheetSage](https://github.com/chrisdonahue/sheetsage) | Chris Donahue | MIT | Base idea for score transcription |
| [MERT](https://github.com/m-a-p/MERT) | M-A-P | CC-BY-NC-4.0 | Music encoder behind MERT2 |
| [Qwen](https://github.com/QwenLM/Qwen) | Alibaba | Apache-2.0 | Tokenizer compatible with the AR model |

## Models and data

- **YuE2-3B** (3.59 B parameters, 28 layers) was trained by the M-A-P team with Tokenwave.AI
  (licensed synthetic data) and MBZUAI. The weights are **CC-BY-NC-4.0**: personal and research
  use only.
- **MERT2** and **SheetSage2** were trained on roughly 700 K and 28 K hours respectively, with
  an emphasis on CC0 music and synthetic data.
- **WildSongBench** is the associated benchmark.

The weights are **not** part of this repository; they are downloaded from Hugging Face during
installation.

## About the patches

Both patches in `patches/` modify files from `mlx-Yue` (Apache-2.0). They are distributed as a
diff that the user applies to their own checkout, preserving upstream's license and copyright
notice. What each change does and why is documented in [PATCHES.md](PATCHES.md).

## Citing

If you use the model, cite the original M-A-P work:

```bibtex
@misc{yue2,
  title  = {YuE2: Frontier music generation with symbolic planning},
  author = {Multimodal Art Projection (M-A-P) and Tokenwave.AI and MBZUAI},
  year   = {2026},
  url    = {https://map-yue2.github.io/}
}
```

If you use the MLX port, cite `vanch007/mlx-Yue` as well. If this installer or the app helped
you, a mention of this repository is enough.
