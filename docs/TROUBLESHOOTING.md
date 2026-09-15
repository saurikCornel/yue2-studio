# Problemas conocidos y cómo se arreglan

Todos los errores de esta lista aparecieron en instalaciones reales. El mensaje va tal cual
sale por consola para que lo puedas buscar.

## El doctor falla con "missing or unexpected files"

```
"model": {"error": "Converted directory has missing or unexpected files: unexpected=['.cache/...', '.gitattributes']"}
```

`snapshot_download` deja su caché y `.gitattributes` dentro del directorio de modelos y el
doctor los considera archivos inesperados.

```bash
cd ~/Projects/mlx-Yue
rm -rf models/converted/.cache models/vae/.cache models/converted/.gitattributes models/vae/.gitattributes
```

## "AC power is required for an acceptance benchmark"

El flag `--require-ac` rechaza arrancar a batería. O enchufás, o sacás el flag:

```bash
./.venv/bin/mlx-yue generate ... --offline --output outputs/tema   # sin --require-ac
```

Y registrá que esa corrida fue a batería: no la mezcles con números tomados enchufado.

## "Resource evidence already exists: outputs/<job>.resources.jsonl"

Un run anterior dejó el archivo de evidencia y el siguiente se niega a pisarlo.

```bash
rm -f outputs/<job>.resources.json outputs/<job>.resources.jsonl
```

## "System memory pressure is not normal (level=2)"

El guard del port cortando por un aviso transitorio de macOS. Es exactamente lo que arregla
el parche 1 — ver [PATCHES.md](PATCHES.md). Si lo ves **con** el parche aplicado, es presión
real: cerrá apps pesadas, bajá `--vae-core-frames` a 64, o corré con `--precision 8bit`.

## "Memory budget must exceed 5 GiB and leave 4 GiB OS headroom"

El helper de transcripción traía `--memory-budget-gib 24` por defecto y el guard exige
`budget <= RAM − 4` (20 en una máquina de 24 GB). Parche 2, o pasalo a mano:

```bash
./.venv/bin/mlx-yue transcribe audio.wav --task melody-full --memory-budget-gib 16 ...
```

## "LocalEntryNotFoundError: Cannot find an appropriate cached snapshot folder"

La transcripción con `--offline` no encuentra los pesos: el hub no resuelve el snapshot por
revisión si no existen los `refs`. Se arregla creando el ref o apuntando a los directorios:

```bash
# opción A: ref en la caché (lo hace install.sh)
printf 'eab522a8168e8b8b8c4856bf8609cd86198f01fe' > \
  ~/.cache/huggingface/hub/models--m-a-p--SheetSage2/refs/main

# opción B: pasar los directorios explícitos
./.venv/bin/mlx-yue transcribe audio.wav --task melody-full \
  --model models/transcription/sheetsage2 --base-model models/transcription/mert2-fullsong ...
```

## "Another Lyra process owns the GPU"

Hay otro trabajo corriendo (o quedó un proceso colgado). Un solo trabajo de GPU por vez:

```bash
pgrep -fl "mlx-yue"        # ver qué está corriendo
pgrep -fl "[s]erver.py"    # o si el backend de la app está a mitad de un job
```

El lock vive en `/tmp/lyra-gpu-<uid>.lock` y se libera solo cuando el proceso termina.

## El puerto 8787 está ocupado / la app se queda en "el backend no respondió"

Casi siempre es un backend viejo suelto:

```bash
pgrep -fl "[s]erver.py" && pkill -f "[s]erver.py"
open "$HOME/Applications/YuE2 Studio.app"
```

La app también trae **⌘⇧R** para reiniciar su backend.

## El MP3 sale mal o el botón de exportar falla

El ffmpeg de Homebrew "pelado" no siempre trae todo. El proyecto usa `ffmpeg-full` si está:

```bash
brew install ffmpeg-full        # queda en /opt/homebrew/opt/ffmpeg-full/bin/ffmpeg
```

El backend prefiere ese binario automáticamente.

## La transcripción tarda muchísimo o no arranca

- Pasá `--max-seconds 180` para transcribir sólo el primer tramo (así lo hace la UI).
- SheetSage2 + MERT2 en MLX necesitan ~3 GB de RAM extra.
- Verificá que los extras estén: `uv sync --frozen --no-dev --extra transcription`
  (si falta `scipy`/`mido`/`mir_eval`/`pretty_midi`, el helper se cae al arrancar).

## Una canción quedó a medias o "truncated"

Mirá `outputs/<job>/result.json`:

- `"status": "complete"` y `"truncated": {"abc": false, "semantic": false}` → canción entera.
- `"truncated": {"semantic": true}` → se acabó `max_tokens` antes del final (el default es
  9000, alcanza para 3-4 minutos; para más, subilo en el request).
- `"status"` distinto de complete → el run no terminó; el log del panel Estado dice por qué.

## "zsh: no matches found"

No es un problema del proyecto: zsh aborta el comando si un glob no matchea
(`rm -rf outputs/algo*` sin coincidencias). Usá comillas o `setopt NULL_GLOB`:

```bash
rm -rf outputs/algo* 2>/dev/null || true
```

## El audio salió mudo o cortado

Verificación rápida, sin escuchar:

```bash
ffprobe -v error -show_entries format=duration -show_entries stream=sample_rate,channels \
  -of default=noprint_wrappers=1 outputs/<job>/audio.flac
ffmpeg -hide_banner -nostats -i outputs/<job>/audio.flac -af volumedetect -f null - 2>&1 | grep volume
```

Esperás 48000 Hz, 2 canales, y `mean_volume` alrededor de −16 dB. Si el nivel es −91 dB, es
silencio: revisá que la letra no esté vacía y que el estilo describa algo.

Para confirmar que la voz canta la letra pedida, transcribilo con Whisper (si lo tenés
instalado; `pip install openai-whisper`):

```bash
whisper outputs/<job>/audio.flac --model large-v3-turbo \
  --language es --task transcribe --output_dir /tmp/chequeo --output_format txt --fp16 False
```

La transcripción tiene que devolver, más o menos, la letra que escribiste. Si devuelve ruido,
la canción salió mal: probá otra semilla o acortá los versos.
