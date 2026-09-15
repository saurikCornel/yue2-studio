# Uso: flujos de trabajo y cómo pedir buena música

## La app

### Crear

1. **Estilo (prompt)**: en inglés funciona mejor. Género + instrumentación + tipo de voz +
   tempo + clima. Ejemplo real:
   `Argentine rock nacional, Spanish male lead vocal, jangly electric guitars, live bass and
   drums, mid tempo 92 BPM, big anthemic chorus`.
2. **Letra**: con etiquetas de sección. El modelo las respeta:
   `[Intro]`, `[Verso]`, `[Pre-Estribillo]`, `[Estribillo]`, `[Puente]`, `[Final]`.
   Versos de 4 líneas y estribillos repetidos dan las canciones más coherentes.
3. **Modo**: `full` (melodía + acordes: el que más control da), `melody` (sin acordes, ideal
   para covers), `off` (sin plan simbólico).
4. **Pasos**: 32 estándar, 8 rápido, 16 intermedio.
5. **Semilla**: mismo estilo + letra + semilla = misma canción. Cambiá la semilla para
   explorar variantes del mismo brief.
6. **Generar**. El panel Estado muestra fase, porcentaje, pasos y el log del CLI en vivo.
   Al terminar: player, **Exportar MP3**, **Mostrar en Finder**, **Partitura**.

### Cover

1. Arrastrá un audio (wav, flac, mp3, m4a…) o hacé clic para elegirlo. Queda en
   `<proyecto>/inputs/`.
2. **Transcribir**: SheetSage2 + MERT2 sacan la melodía (y ritmo, tonalidad y estructura) y
   te la muestran en ABC. Por defecto transcribe los primeros 180 s.
3. Escribí el estilo nuevo y la letra nueva.
4. **Generar cover** con modo `melody`.

El resultado queda en `outputs/cover-<fuente>/song/` con la transcripción al lado, en
`outputs/cover-<fuente>/transcription/`.

### Biblioteca

Lista todo lo que hay en `<proyecto>/outputs/`: canciones, covers y transcripciones, con
duración, modo, semilla, player, exportación a MP3, revelar en Finder, ver partitura y
borrar.

## Lo mismo por CLI

```bash
cd ~/Projects/mlx-Yue
export MLX_ENABLE_TF32=0 LYRA_VAE="$PWD/models/vae"
PY=./.venv/bin/mlx-yue

# canción completa
$PY generate examples/cancion-es.json --model models/converted --vae "$LYRA_VAE" \
    --precision 8bit --offline --vae-core-frames 128 --memory-budget-gib 16 --output outputs/tema

# sólo el plan simbólico (ABC + tokens), sin audio
$PY plan examples/cancion-es.json --model models/converted --output outputs/plan-tema

# con una partitura propia
$PY generate examples/cancion-es.json --abc mi-partitura.abc --mode full \
    --model models/converted --vae "$LYRA_VAE" --offline --output outputs/tema-abc

# transcribir
$PY transcribe inputs/tema.wav --task melody-full \
    --model models/transcription/sheetsage2 --base-model models/transcription/mert2-fullsong \
    --output outputs/transcripcion --offline --memory-budget-gib 16

# cover de punta a punta
$PY cover --audio inputs/tema.wav --style "Jazz-funk, warm lead vocal, Rhodes" \
    --lyrics-file letra-nueva.txt --task melody-full --mode melody \
    --model models/converted --vae "$LYRA_VAE" --offline --memory-budget-gib 16 \
    --output outputs/cover-tema
```

Formato del request JSON:

```json
{
  "id": "mi-tema",
  "style": "género, voz, instrumentos, tempo, clima",
  "lyrics": "[Verso]\n...\n[Estribillo]\n...",
  "cot": "full",
  "seed": 15092026,
  "generation_config": { "ode_steps": 32 },
  "semantic_sampling": { "max_tokens": 9000 }
}
```

`generation_config` también acepta `temperature`, `top_p`, `top_k`, `repetition_penalty`
(dentro de `abc` y `semantic`), y el request admite `cfg_scale` (1.0-1.2) para pegar más al
texto.

## Qué esperar

- **Duración**: la decide el modelo según la letra; una letra de verso+estribillo da ~1:15,
  una canción con puente y estribillo repetido, ~3 minutos. `max_tokens: 9000` alcanza para
  ~4 minutos.
- **Calidad**: la voz canta la letra de forma inteligible (lo verifiqué transcribiendo el mix
  con Whisper y volvió la letra completa). El estribillo suele ser lo mejor; los versos con
  demasiadas palabras seguidas se atropellan.
- **Sin batería ni teclado**: no hay UI para editar la partitura, pero la podés editar: el
  archivo `score.abc` está en la carpeta de salida y podés regenerar pasándolo con `--abc`.

## Recetas

- **Tanteo rápido**: 8 pasos, letra corta (un verso y un estribillo), así escuchás la idea en
  menos de un minuto.
- **Comparar variantes**: mismo brief, semilla distinta; o mismo seed y un solo cambio (estilo
  o letra).
- **Arreglar una canción**: `plan` para ver el ABC, editalo, y volvé a generar con `--abc`.
- **Instrumental**: modo `off` con letra vacía y un estilo que aclare "instrumental".
- **Exportar**: botón MP3 en la app (320 kbps), o a mano:
  `ffmpeg -i audio.flac -c:a libmp3lame -b:a 320k audio.mp3`.
