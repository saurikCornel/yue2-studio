# Instalación

Dos caminos: el instalador (recomendado) o el paso a paso manual.

## Rápido

```bash
git clone https://github.com/<usuario>/yue2-studio.git
cd yue2-studio
bash install.sh                        # motor + app
bash install.sh --with-transcribe      # + transcripción y covers (+2.6 GB)
bash install.sh --check                # solo informar el estado
bash install.sh --no-app               # sin compilar la app nativa
bash install.sh --help
```

Variables: `YUE2_PROJECT` (dónde clonar el port, por defecto `~/Projects/mlx-Yue`) y
`YUE2_MIN_AVAILABLE_GIB` (memoria libre mínima que exige el parche del guard, por defecto 1).

El instalador es idempotente: si ya hay pesos, entorno o parches, los saltea. Re-ejecutarlo
es la forma normal de reparar o actualizar una instalación.

Qué hace, en orden:

1. Verifica Apple Silicon, macOS, memoria (≥24 GB), `uv`, `ffmpeg`, `swiftc`.
2. Clona (o actualiza con `git pull --ff-only`) `vanch007/mlx-Yue` en `$YUE2_PROJECT`.
3. Aplica los parches de `patches/apply_patches.py`.
4. `uv sync --frozen --no-dev` (+ `--extra transcription` si pediste covers).
5. Descarga los pesos convertidos (~10.5 GB) y la VAE, y limpia `.cache`/`.gitattributes`.
6. Crea `models/paths.json` y, si corresponde, enlaza los modelos de transcripción.
7. Corre el doctor y exige `pass`.
8. Escribe `config.json` y compila `YuE2 Studio.app` en `~/Applications`.

## Manual

### 0. Dependencias

```bash
brew install uv ffmpeg
xcode-select --install        # o Xcode completo, para compilar la app
```

### 1. Port MLX

```bash
git clone https://github.com/vanch007/mlx-Yue.git ~/Projects/mlx-Yue
cd ~/Projects/mlx-Yue
uv sync --frozen --no-dev                 # NO uses "uv sync" a secas: arrastra el grupo dev
uv pip install --python .venv/bin/python hf_transfer    # descargas más rápidas
```

### 2. Parches

```bash
python3 ~/Projects/yue2-studio/patches/apply_patches.py --project ~/Projects/mlx-Yue
python3 ~/Projects/yue2-studio/patches/apply_patches.py --project ~/Projects/mlx-Yue --check
```

Si tenés 32 GB o más, podés saltear este paso (ver [PATCHES.md](PATCHES.md)).

### 3. Pesos

```bash
cd ~/Projects/mlx-Yue
export HF_HUB_ENABLE_HF_TRANSFER=1
.venv/bin/python - <<'PY'
from huggingface_hub import snapshot_download
snapshot_download("vanch007/mlx-Yue2-3B", local_dir="models/converted")
snapshot_download("m-a-p/YuE2-Vae",       local_dir="models/vae")
PY
rm -rf models/converted/.cache models/vae/.cache models/converted/.gitattributes models/vae/.gitattributes
printf '{\n  "model": "models/converted",\n  "vae": "models/vae"\n}\n' > models/paths.json
```

### 4. Verificar

```bash
cd ~/Projects/mlx-Yue
MLX_ENABLE_TF32=0 ./.venv/bin/mlx-yue doctor --model models/converted --vae models/vae --verify-hashes
```

Tiene que decir `"status": "pass"` con `model` y `vae` en `true`. Si falla, mirá
[TROUBLESHOOTING.md](TROUBLESHOOTING.md).

### 5. Primera canción

```bash
cd ~/Projects/mlx-Yue
export MLX_ENABLE_TF32=0 LYRA_VAE="$PWD/models/vae"
./.venv/bin/mlx-yue generate examples/cancion-es.json \
  --model models/converted --vae "$LYRA_VAE" --precision 8bit --offline \
  --vae-core-frames 128 --memory-budget-gib 16 --output outputs/prueba
ffprobe outputs/prueba/audio.flac     # 48 kHz, estéreo, ~3:20
```

### 6. App

```bash
cd ~/Projects/yue2-studio
bash build_app.sh                     # instala en ~/Applications
bash build_app.sh /Applications       # o donde quieras
open "$HOME/Applications/YuE2 Studio.app"
```

Sin app nativa, la interfaz es la misma en el navegador:

```bash
cd ~/Projects/yue2-studio
python3 server.py                     # http://127.0.0.1:8787
```

### 7. Transcripción y covers (opcional)

```bash
cd ~/Projects/mlx-Yue
uv sync --frozen --no-dev --extra transcription
export HF_HUB_ENABLE_HF_TRANSFER=1
.venv/bin/python - <<'PY'
from huggingface_hub import snapshot_download
import pathlib
for repo, rev in (("m-a-p/SheetSage2", "eab522a8168e8b8b8c4856bf8609cd86198f01fe"),
                  ("m-a-p/MERT-v2-FullSong", "d8ba1c745e733b3908ce6ad16ebeb17ac7600a42")):
    path = snapshot_download(repo, revision=rev, allow_patterns=["config.json", "model.safetensors"])
    ref = pathlib.Path(path).parents[1] / "refs"      # necesario para --offline
    ref.mkdir(parents=True, exist_ok=True)
    (ref / "main").write_text(rev)
    print("ok", repo)
PY
mkdir -p models/transcription
ln -sfn "$HOME/.cache/huggingface/hub/models--m-a-p--SheetSage2/snapshots/"*/ models/transcription/sheetsage2
ln -sfn "$HOME/.cache/huggingface/hub/models--m-a-p--MERT-v2-FullSong/snapshots/"*/ models/transcription/mert2-fullsong
```

Prueba rápida:

```bash
./.venv/bin/mlx-yue transcribe inputs/mi-audio.wav --task melody-full \
  --model models/transcription/sheetsage2 --base-model models/transcription/mert2-fullsong \
  --output outputs/transcripcion --offline --memory-budget-gib 16
```

## Desinstalar

```bash
rm -rf "$HOME/Applications/YuE2 Studio.app"
rm -rf ~/Projects/yue2-studio ~/Projects/mlx-Yue        # el port y los pesos (11 GB)
rm -rf ~/.cache/huggingface/hub/models--m-a-p--SheetSage2 \
       ~/.cache/huggingface/hub/models--m-a-p--MERT-v2-FullSong   # transcripción (2.6 GB)
```

No se instala nada fuera de esas rutas: ni demonios, ni servicios, ni ficheros del sistema.

## Estructura en disco tras instalar

```
~/Projects/mlx-Yue/                    11 GB   port + entorno + pesos
  ├── models/converted/                 9.2 GB AR (bf16/8bit) + NAR + tokenizer
  ├── models/vae/                       507 MB VAE 48 kHz
  ├── models/transcription/             enlaces a la caché de HuggingFace
  └── outputs/                          canciones, covers, transcripciones
~/Projects/yue2-studio/                 200 KB  app, backend, UI, parches
~/Applications/YuE2 Studio.app          111 KB  binario Swift
~/.cache/huggingface/hub/               2.6 GB  SheetSage2 + MERT2-FullSong (opcional)
```
