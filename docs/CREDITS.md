# Créditos y licencias de terceros

Este repositorio (instalador, backend, UI, ventana nativa y parches) es **MIT** — ver
[LICENSE](../LICENSE).

## Proyectos de los que depende

| Proyecto | Autor | Licencia | Qué aporta |
|---|---|---|---|
| [mlx-Yue](https://github.com/vanch007/mlx-Yue) | vanch007 | Apache-2.0 | Port nativo Apple Silicon del pipeline YuE2: planner AR, flow matching NAR, VAE, transcripción |
| [YuE / YuE2](https://github.com/multimodal-art-projection/YuE) | Multimodal Art Projection (M-A-P) | Apache-2.0 (código) | Modelo original, pipeline oficial, pesos de referencia |
| [MLX](https://github.com/ml-explore/mlx) y [MLX-LM](https://github.com/ml-explore/mlx-lm) | Apple | MIT | Framework de inferencia en Metal |
| [stable-audio-tools](https://github.com/Stability-AI/stable-audio-tools) | Stability AI | MIT | Arquitectura del VAE (Oobleck) |
| [SheetSage](https://github.com/chrisdonahue/sheetsage) | Chris Donahue | MIT | Idea base de transcripción a partitura |
| [MERT](https://github.com/m-a-p/MERT) | M-A-P | CC-BY-NC-4.0 | Encoder musical subyacente a MERT2 |
| [Qwen](https://github.com/QwenLM/Qwen) | Alibaba | Apache-2.0 | Tokenizer compatible con el AR |

## Modelos y datos

- **YuE2-3B** (3.59 B parámetros, 28 capas) fue entrenado por el equipo M-A-P con
  Tokenwave.AI (datos sintéticos bajo licencia) y MBZUAI. Los pesos están en
  **CC-BY-NC-4.0**: sólo uso personal y de investigación.
- **MERT2** y **SheetSage2** se entrenaron sobre ~700 K y ~28 K horas respectivamente, con
  foco en música CC0 y datos sintéticos.
- `WildSongBench` es el benchmark asociado del proyecto.

Los pesos **no** se incluyen en este repositorio; se descargan desde Hugging Face al instalar.

## Sobre los parches

Los dos parches de `patches/` modifican archivos de `mlx-Yue` (Apache-2.0). Se distribuyen
como diff aplicable sobre un checkout propio del usuario, manteniendo la licencia y el aviso
de copyright de upstream. El detalle de cada cambio y por qué está en
[PATCHES.md](PATCHES.md).

## Cómo citar

Si usás el modelo, citá el trabajo original de M-A-P:

```bibtex
@misc{yue2,
  title  = {YuE2: Frontier music generation with symbolic planning},
  author = {Multimodal Art Projection (M-A-P) and Tokenwave.AI and MBZUAI},
  year   = {2026},
  url    = {https://map-yue2.github.io/}
}
```

Si usás el port MLX, citá también `vanch007/mlx-Yue`. Si te sirvió este instalador o la app,
una mención al repo alcanza.
