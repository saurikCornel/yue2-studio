# Modelos y licencias

Este repo no incluye pesos: el instalador los baja desde Hugging Face. Acá está qué es cada
cosa, cuánto pesa y qué licencia tiene.

## Generación

| Pieza | Repo | Tamaño | Licencia |
|---|---|---|---|
| Generador AR (bf16) | `vanch007/mlx-Yue2-3B` → `ar-bf16.safetensors` | 4.33 GB | CC-BY-NC-4.0 |
| Generador AR (int8) | `vanch007/mlx-Yue2-3B` → `ar-8bit.safetensors` | 2.66 GB | CC-BY-NC-4.0 |
| NAR (flow matching, bf16) | `vanch007/mlx-Yue2-3B` → `nar-bf16.safetensors` | 2.93 GB | CC-BY-NC-4.0 |
| Tokenizer | `vanch007/mlx-Yue2-3B` → `qwen.tiktoken` | 2.5 MB | — |
| VAE 48 kHz estéreo | `m-a-p/YuE2-Vae` → `model.safetensors` | 507 MB | CC-BY-NC-4.0 |

Total: **~10.5 GB**. El AR trae dos precisiones: `8bit` (más rápido y liviano, el que usa la
app) y `bf16` (referencia de precisión). El NAR y la VAE siempre van bf16/FP32.

Los pesos son los del port MLX (`vanch007/mlx-Yue2-3B`), ya convertidos de los originales de
`m-a-p/YuE2-3B`; pesan menos porque el AR está cuantizado y porque sólo se extrajeron las
partes que usa la inferencia.

## Transcripción y covers (opcional, +2.6 GB)

| Pieza | Repo | Tamaño | Licencia |
|---|---|---|---|
| SheetSage2 (audio → partitura) | `m-a-p/SheetSage2` | 218 MB | CC-BY-NC-4.0 |
| MERT2-FullSong (encoder musical) | `m-a-p/MERT-v2-FullSong` | 2.4 GB | CC-BY-NC-4.0 |

Revisión fijada en `src/lyra/transcription/model.py` del port: se descargan esos commits
exactos, no `main`.

## Licencia de lo generado

Los pesos son **CC-BY-NC-4.0**: uso de investigación y personal, **no comercial**. Lo que
generes hereda esa restricción. Si necesitás uso comercial, mirá los términos de M-A-P y de
Tokenwave.AI (que aportó buena parte de los datos sintéticos de entrenamiento).

## Qué NO usa

- Nada de la ruta CUDA: `yue2_infer` (el paquete oficial) es Linux + GPU NVIDIA. En macOS
  tiene ramas MPS, pero fija `torch==2.10.0`, cuya atención causal en BF16 está rota en MPS
  (filtra hasta 3 keys futuras, sin error ni NaN; issue #176 de `multimodal-art-projection/YuE`).
- PyTorch en runtime: el port es MLX puro. Torch sólo aparece en tests de desarrollo.

## Verificar lo que bajaste

```bash
cd ~/Projects/mlx-Yue
MLX_ENABLE_TF32=0 ./.venv/bin/mlx-yue doctor --model models/converted --vae models/vae --verify-hashes
```

`--verify-hashes` compara SHA-256 contra los que trae el propio paquete. En la instalación de
referencia: `ar-8bit` 2 656 158 264 bytes, `ar-bf16` 4 331 951 136, `nar-bf16` 2 929 490 456,
VAE 530 512 720.
