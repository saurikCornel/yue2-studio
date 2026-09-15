# Hardware y rendimiento

## Mínimos

| | |
|---|---|
| Chip | Apple Silicon (M1–M5). El runtime rechaza Intel/Rosetta explícitamente |
| macOS | 14.2+ en M1–M4 · **26.2+ en M5** (MLX usa rutas de Metal nuevas) |
| Memoria unificada | **24 GB mínimo**; 32 GB+ holgado. Upstream probó en M5 Air 32 GB y M3 Max 128 GB |
| Disco | ~14 GB: 11 GB de pesos + entorno, y 2.6 GB extra si querés transcripción |
| Python | 3.12 (lo pone `uv`, no toques el Python del sistema) |
| Herramientas | `uv`, `ffmpeg`, y Xcode/Command Line Tools si querés la app nativa |

## Por qué 24 GB es el borde

El proceso de generación pide ~10-12 GiB de pico (pesos AR + NAR + VAE + activaciones), y
macOS necesita el resto. En una máquina de 24 GB eso deja el margen justo: el sistema
comprime, marca presión transitoria y —sin el parche— el guard del port corta la
generación. Con el parche corre, pero el colchón sigue siendo fino: dejá el cargador
conectado y cerrá Chrome/Electron/Safari durante una tanda larga.

Números del pico real, medidos con el guard activo:

| Trabajo | Pico del proceso | Pico de MLX | Swap nuevo |
|---|---|---|---|
| Clip de 16 s (32 pasos) | ~7 GiB | ~6.8 GiB | 0 |
| Canción de 3:20 (32 pasos) | 10.40 GiB | 9.93 GiB | 0 |
| Canción de 1:16 (8 pasos) | ~9 GiB | ~8.6 GiB | 0 |

Presupuesto del guard: 16 GiB (`--memory-budget-gib`), límite asesor de MLX 11 GiB, y
límite del cache de MLX 128 MiB. Working set recomendado por la GPU en un M5 Pro de 24 GB:
17.76 GiB — o sea que el pico medido entra con ~7 GiB de aire.

## Tiempos medidos (MacBook Pro M5 Pro · 24 GB · macOS 27.0)

Configuración: `--precision 8bit`, `--vae-core-frames 128`, `MLX_ENABLE_TF32=0`.

| Trabajo | Audio | Cómputo | RTF |
|---|---|---|---|
| Clip quickstart, 32 pasos | 16 s | 13.2 s | 0.83 |
| Canción completa castellano, 32 pasos | 200.7 s | 336.8 s | 1.68 |
| Cumbia villera, 8 pasos | 76.0 s | 47.1 s | 0.62 |
| Transcripción (SheetSage2 + MERT2), 16 s de fuente | — | 5.7 s | — |
| Cover sobre fuente de 16 s (transcribir + generar) | 16.5 s | 24.4 s | — |

Desglose de una canción de 3:20: planificación simbólica (ABC) unos segundos, generación de
tokens semánticos (AR) el tramo más largo en tokens, síntesis acústica (NAR, 32 pasos de
midpoint = 64 evaluaciones) 253.6 s, decodificación VAE 7.8 s. La carga de pesos y la
verificación de integridad suman ~4 s.

**Elegir pasos.** 8 pasos = rápido, sirve para tantear ideas (RTF < 1 en M3 Max y ~0.62 acá).
32 pasos = estándar, la calidad que reportan los benchmarks. 16 es un punto medio.

## Otros chips

MLX escala con los núcleos de GPU, así que M5 Pro/Max y M4 Pro/Max van a andar más rápido
que un M1 base. Lo que no escala es la memoria: en un M1/M2 de 16 GB **no va** — el pico de
10 GiB no entra con macOS encima, y el guard lo va a cortar. En 24 GB es viable con los
parches; en 32 GB o más podés usar upstream sin tocar nada.

## Notas de energía

- El CLI tiene `--require-ac` para benchmarks: rechaza arrancar si no estás enchufado. La app
  no lo usa, pero muestra el estado en Ajustes y en el pie del sidebar.
- Correr a batería funciona (los tiempos de arriba son de una tanda enchufada; a batería el
  rendimiento baja por límites térmicos y de energía). Para tandas largas, cargador.
- Un solo trabajo de GPU a la vez: el runtime toma un `flock` en
  `/tmp/lyra-gpu-<uid>.lock`. Si lanzás dos, el segundo falla con
  "Another Lyra process owns the GPU".
