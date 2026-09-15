#!/bin/bash
# YuE2 Studio — instalador para Apple Silicon.
#
#   bash install.sh                  instala motor + app (recomendado)
#   bash install.sh --check          solo informa el estado del entorno
#   bash install.sh --with-transcribe  agrega transcripción y covers (+2.6 GB)
#   bash install.sh --no-app         sin compilar la app (usa la UI en el navegador)
#
# Variables: YUE2_PROJECT (default ~/Projects/mlx-Yue), YUE2_MIN_AVAILABLE_GIB
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT="${YUE2_PROJECT:-$HOME/Projects/mlx-Yue}"
UPSTREAM="https://github.com/vanch007/mlx-Yue.git"
WEIGHTS_REPO="vanch007/mlx-Yue2-3B"
VAE_REPO="m-a-p/YuE2-Vae"

CHECK_ONLY=0
WITH_TRANSCRIBE=0
BUILD_APP=1
for arg in "$@"; do
  case "$arg" in
    --check) CHECK_ONLY=1 ;;
    --with-transcribe) WITH_TRANSCRIBE=1 ;;
    --no-app) BUILD_APP=0 ;;
    -h|--help) sed -n '2,10p' "$0"; exit 0 ;;
    *) echo "opción desconocida: $arg"; exit 2 ;;
  esac
done

say()  { printf '\n\033[1m== %s\033[0m\n' "$*"; }
ok()   { printf '   ok   %s\n' "$*"; }
warn() { printf '   !    %s\n' "$*"; }
die()  { printf '\n\033[31mERROR: %s\033[0m\n' "$*" >&2; exit 1; }

# ---------------------------------------------------------------- chequeos
say "entorno"
[ "$(uname -s)" = "Darwin" ] || die "esto es solo para macOS"
[ "$(uname -m)" = "arm64" ] || die "se necesita Apple Silicon (arm64), no Intel/Rosetta"
CHIP="$(sysctl -n machdep.cpu.brand_string 2>/dev/null || echo 'Apple Silicon')"
RAM_GIB="$(( $(sysctl -n hw.memsize) / 1073741824 ))"
MACOS="$(sw_vers -productVersion)"
ok "$CHIP · ${RAM_GIB} GB · macOS $MACOS"

if [ "$RAM_GIB" -lt 24 ]; then
  die "hacen falta 24 GB de memoria unificada como mínimo (probado en M5 Pro 24 GB y M3 Max 128 GB)"
elif [ "$RAM_GIB" -lt 32 ]; then
  warn "24 GB: funciona, pero el margen de memoria es fino. Cargador conectado y apps pesadas cerradas."
fi

case "$CHIP" in
  *"M5"*) [ "${MACOS%%.*}" -ge 26 ] || warn "M5 pide macOS 26.2 o superior" ;;
esac

HAVE_UV=$(command -v uv || true)
[ -n "$HAVE_UV" ] || die "falta uv:  brew install uv"
ok "uv $("$HAVE_UV" --version | awk '{print $2}')"

HAVE_FFMPEG=$(command -v ffmpeg || true)
[ -n "$HAVE_FFMPEG" ] && ok "ffmpeg ${HAVE_FFMPEG}" || warn "sin ffmpeg (necesario para transcripción y covers):  brew install ffmpeg"

HAVE_SWIFTC=$(command -v swiftc || true)
[ -n "$HAVE_SWIFTC" ] && ok "swiftc (Xcode) listo" || warn "sin swiftc: la app nativa no se compila (se puede usar igual en el navegador)"

for path in "/opt/homebrew/opt/ffmpeg-full/bin/ffmpeg"; do
  [ -x "$path" ] && ok "ffmpeg-full presente (mejor codificación de MP3)"
done

say "proyecto mlx-Yue en $PROJECT"
if [ "$CHECK_ONLY" = "1" ]; then
  [ -d "$PROJECT/.venv" ] && ok "entorno instalado" || warn "falta el entorno (uv sync)"
  [ -f "$PROJECT/models/converted/conversion.json" ] && ok "pesos del generador" || warn "faltan pesos (--no-models evitó la descarga)"
  [ -f "$PROJECT/models/vae/config.json" ] && ok "VAE" || warn "falta la VAE"
  python3 "$ROOT/patches/apply_patches.py" --project "$PROJECT" --check || true
  "$PROJECT/.venv/bin/mlx-yue" doctor --model "$PROJECT/models/converted" --vae "$PROJECT/models/vae" 2>/dev/null \
    | python3 -c "import json,sys; d=json.load(sys.stdin); print('   doctor:', d['status'], d['checks'])" || warn "doctor no disponible"
  exit 0
fi

# ---------------------------------------------------------------- checkout
if [ -d "$PROJECT/.git" ]; then
  ok "checkout existente, hago git pull"
  git -C "$PROJECT" pull --ff-only || warn "no se pudo actualizar (seguimos con lo que hay)"
else
  mkdir -p "$(dirname "$PROJECT")"
  git clone --depth 1 "$UPSTREAM" "$PROJECT"
  ok "clonado desde $UPSTREAM"
fi
cd "$PROJECT"

# ---------------------------------------------------------------- parches
say "parches (guard de memoria y presupuesto de transcripción)"
python3 "$ROOT/patches/apply_patches.py" --project "$PROJECT"

# ---------------------------------------------------------------- entorno python
say "entorno Python (uv sync, sin dev group)"
if [ "$WITH_TRANSCRIBE" = "1" ]; then
  uv sync --frozen --no-dev --extra transcription
else
  uv sync --frozen --no-dev
fi
uv pip install --python .venv/bin/python hf_transfer >/dev/null 2>&1 || warn "hf_transfer no instalado (la descarga irá más lenta)"
ok "entorno listo"

# ---------------------------------------------------------------- pesos
PY=".venv/bin/python"
if [ -f models/converted/conversion.json ] && [ -f models/vae/config.json ]; then
  ok "pesos ya presentes, salteo la descarga (~10.5 GB)"
else
  say "descarga de pesos (~10.5 GB: AR bf16/8bit + NAR + VAE)"
  HF_HUB_ENABLE_HF_TRANSFER=1 "$PY" - <<PYEOF
from huggingface_hub import snapshot_download
snapshot_download("$WEIGHTS_REPO", local_dir="models/converted")
snapshot_download("$VAE_REPO", local_dir="models/vae")
PYEOF
  # el doctor rechaza archivos inesperados dentro de los directorios de modelos
  rm -rf models/converted/.cache models/vae/.cache models/converted/.gitattributes models/vae/.gitattributes
  ok "pesos listos"
  du -sh models/converted models/vae | sed 's/^/   /'
fi

printf '{\n  "model": "models/converted",\n  "vae": "models/vae"\n}\n' > models/paths.json

# ---------------------------------------------------------------- transcripción
if [ "$WITH_TRANSCRIBE" = "1" ]; then
  say "modelos de transcripción (SheetSage2 + MERT2-FullSong, ~2.6 GB)"
  HF_HUB_ENABLE_HF_TRANSFER=1 "$PY" - <<'PYEOF'
from huggingface_hub import snapshot_download
pairs = (("m-a-p/SheetSage2", "eab522a8168e8b8b8c4856bf8609cd86198f01fe"),
         ("m-a-p/MERT-v2-FullSong", "d8ba1c745e733b3908ce6ad16ebeb17ac7600a42"))
for repo, rev in pairs:
    path = snapshot_download(repo, revision=rev, allow_patterns=["config.json", "model.safetensors"])
    print("   ok  ", repo, "->", path)
    # con --offline el hub no resuelve el snapshot por revisión si no hay refs
    import pathlib
    ref = pathlib.Path(path).parents[1] / "refs"
    ref.mkdir(parents=True, exist_ok=True)
    (ref / "main").write_text(rev)
PYEOF
  mkdir -p models/transcription
  # find en vez de globs: con set -u/-o pipefail un glob sin match aborta el instalador
  SHEETSAGE="$(find "$HOME/.cache/huggingface/hub/models--m-a-p--SheetSage2/snapshots" -maxdepth 1 -mindepth 1 -type d 2>/dev/null | head -1)"
  MERT="$(find "$HOME/.cache/huggingface/hub/models--m-a-p--MERT-v2-FullSong/snapshots" -maxdepth 1 -mindepth 1 -type d 2>/dev/null | head -1)"
  [ -n "$SHEETSAGE" ] && ln -sfn "$SHEETSAGE" models/transcription/sheetsage2
  [ -n "$MERT" ] && ln -sfn "$MERT" models/transcription/mert2-fullsong
  ok "transcripción lista (el studio la usa desde models/transcription/)"
fi

# ---------------------------------------------------------------- verificación
say "verificación"
MLX_ENABLE_TF32=0 "$PY" -m lyra.cli doctor --model models/converted --vae models/vae \
  | "$PY" -c "import json,sys; d=json.load(sys.stdin); print('   doctor:', d['status'], d['checks']); sys.exit(0 if d['status']=='pass' else 1)" \
  || die "el doctor no dio pass; revisá docs/TROUBLESHOOTING.md"

# ---------------------------------------------------------------- app
say "app"
mkdir -p "$HOME/.config/yue2-studio" 2>/dev/null || true
CONFIG="$ROOT/config.json"
if [ ! -f "$CONFIG" ]; then
  cat > "$CONFIG" <<JSON
{
  "project": "$PROJECT",
  "port": 8787,
  "vae_core_frames": 128,
  "precision": "8bit",
  "memory_budget_gib": 16,
  "transcription_model": "models/transcription/sheetsage2",
  "transcription_base_model": "models/transcription/mert2-fullsong",
  "console_visible": true
}
JSON
  ok "config.json creado apuntando a $PROJECT"
else
  python3 - "$CONFIG" "$PROJECT" <<'PYEOF'
import json, sys
path, project = sys.argv[1], sys.argv[2]
data = json.load(open(path))
if data.get("project") != project:
    data["project"] = project
    json.dump(data, open(path, "w"), indent=2)
    print("   ok   config.json actualizado ->", project)
else:
    print("   ok   config.json ya apuntaba al proyecto")
PYEOF
fi

if [ "$BUILD_APP" = "1" ] && [ -n "$HAVE_SWIFTC" ]; then
  bash "$ROOT/build_app.sh" | tail -3 | sed 's/^/   /'
else
  warn "sin app nativa: usá  python3 $ROOT/server.py  y abrí http://127.0.0.1:8787"
fi

say "listo"
cat <<EOF
   App:       ~/Applications/YuE2 Studio.app   (o arrastrala a /Applications)
   Sin app:   python3 "$ROOT/server.py"   ->   http://127.0.0.1:8787
   CLI:       cd "$PROJECT" && ./.venv/bin/mlx-yue generate examples/cancion-es.json \\
                --model models/converted --vae models/vae --precision 8bit --offline --output outputs/prueba

   Los pesos son CC-BY-NC-4.0: uso personal, no comercial.
   Si algo falla, mirá docs/TROUBLESHOOTING.md.
EOF
