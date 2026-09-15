# Installation

Two paths: the installer (recommended) or the manual walkthrough.

## Quick path

```bash
git clone https://github.com/stavitian/yue2-studio.git
cd yue2-studio
bash install.sh                        # engine + app
bash install.sh --with-transcribe      # + transcription and covers (+2.6 GB)
bash install.sh --check                # report the state of an install
bash install.sh --no-app               # skip the native app
bash install.sh --help
```

Environment variables: `YUE2_PROJECT` (where the MLX port is cloned, default
`~/Projects/mlx-Yue`) and `YUE2_MIN_AVAILABLE_GIB` (free memory the memory-guard patch
requires, default 1).

The installer is idempotent: existing weights, virtualenvs and patches are skipped.
Re-running it is the normal way to repair or update an installation.

What it does, in order:

1. Checks Apple Silicon, macOS version, memory (≥24 GB), `uv`, `ffmpeg`, `swiftc`.
2. Clones (or updates with `git pull --ff-only`) `vanch007/mlx-Yue` into `$YUE2_PROJECT`.
3. Applies the patches from `patches/apply_patches.py`.
4. Runs `uv sync --frozen --no-dev` (plus `--extra transcription` if you asked for covers).
5. Downloads the converted weights (~10.5 GB) and the VAE, then removes `.cache` and
   `.gitattributes` from the model directories.
6. Writes `models/paths.json` and, when applicable, links the transcription models.
7. Runs the runtime doctor and requires `pass`.
8. Writes `config.json` and builds `YuE2 Studio.app` into `~/Applications`.

## Manual walkthrough

### 0. Dependencies

```bash
brew install uv ffmpeg
xcode-select --install        # or full Xcode, to build the native app
```

### 1. MLX port

```bash
git clone https://github.com/vanch007/mlx-Yue.git ~/Projects/mlx-Yue
cd ~/Projects/mlx-Yue
uv sync --frozen --no-dev                 # do NOT run plain "uv sync": it pulls the dev group too
uv pip install --python .venv/bin/python hf_transfer    # faster downloads
```

### 2. Patches

```bash
python3 ~/Projects/yue2-studio/patches/apply_patches.py --project ~/Projects/mlx-Yue
python3 ~/Projects/yue2-studio/patches/apply_patches.py --project ~/Projects/mlx-Yue --check
```

On a machine with 32 GB or more you can skip this step (see [PATCHES.md](PATCHES.md)).

### 3. Weights

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

### 4. Verify

```bash
cd ~/Projects/mlx-Yue
MLX_ENABLE_TF32=0 ./.venv/bin/mlx-yue doctor --model models/converted --vae models/vae --verify-hashes
```

It has to report `"status": "pass"` with `model` and `vae` set to `true`. If it fails, see
[TROUBLESHOOTING.md](TROUBLESHOOTING.md).

### 5. First song

```bash
cd ~/Projects/mlx-Yue
export MLX_ENABLE_TF32=0 LYRA_VAE="$PWD/models/vae"
cp ~/Projects/yue2-studio/examples/english-song.json requests/
./.venv/bin/mlx-yue generate requests/english-song.json \
  --model models/converted --vae "$LYRA_VAE" --precision 8bit --offline \
  --vae-core-frames 128 --memory-budget-gib 16 --output outputs/first-song
ffprobe outputs/first-song/audio.flac     # 48 kHz, stereo, about 1:20
```

### 6. App

```bash
cd ~/Projects/yue2-studio
bash build_app.sh                     # installs into ~/Applications
bash build_app.sh /Applications       # or wherever you prefer
open "$HOME/Applications/YuE2 Studio.app"
```

Without the native app, the interface is the same in a browser:

```bash
cd ~/Projects/yue2-studio
python3 server.py                     # http://127.0.0.1:8787
```

### 7. Transcription and covers (optional)

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
    ref = pathlib.Path(path).parents[1] / "refs"      # required for --offline
    ref.mkdir(parents=True, exist_ok=True)
    (ref / "main").write_text(rev)
    print("ok", repo)
PY
mkdir -p models/transcription
ln -sfn "$HOME/.cache/huggingface/hub/models--m-a-p--SheetSage2/snapshots/"*/ models/transcription/sheetsage2
ln -sfn "$HOME/.cache/huggingface/hub/models--m-a-p--MERT-v2-FullSong/snapshots/"*/ models/transcription/mert2-fullsong
```

Quick test:

```bash
./.venv/bin/mlx-yue transcribe inputs/my-audio.wav --task melody-full \
  --model models/transcription/sheetsage2 --base-model models/transcription/mert2-fullsong \
  --output outputs/transcription --offline --memory-budget-gib 16
```

## Uninstall

```bash
rm -rf "$HOME/Applications/YuE2 Studio.app"
rm -rf ~/Projects/yue2-studio ~/Projects/mlx-Yue        # port and weights (11 GB)
rm -rf ~/.cache/huggingface/hub/models--m-a-p--SheetSage2 \
       ~/.cache/huggingface/hub/models--m-a-p--MERT-v2-FullSong   # transcription (2.6 GB)
```

Nothing is installed outside those paths: no daemons, no services, no system files.

## Disk layout after installing

```
~/Projects/mlx-Yue/                    11 GB   port + virtualenv + weights
  ├── models/converted/                 9.2 GB AR (bf16/8bit) + NAR + tokenizer
  ├── models/vae/                       507 MB 48 kHz VAE
  ├── models/transcription/             links into the Hugging Face cache
  └── outputs/                          songs, covers, transcriptions
~/Projects/yue2-studio/                 200 KB app, backend, UI, patches
~/Applications/YuE2 Studio.app          111 KB Swift binary
~/.cache/huggingface/hub/               2.6 GB SheetSage2 + MERT2-FullSong (optional)
```
