#!/bin/bash
# YuE2 Studio — installer for Apple Silicon.
#
#   bash install.sh                    install engine + app (recommended)
#   bash install.sh --check            only report the state of the environment
#   bash install.sh --with-transcribe  add transcription and covers (+2.6 GB)
#   bash install.sh --no-app           skip the native app (use the browser UI)
#
# Environment variables: YUE2_PROJECT (default ~/Projects/mlx-Yue),
#                        YUE2_MIN_AVAILABLE_GIB (memory-guard threshold, default 1)
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
    *) echo "unknown option: $arg"; exit 2 ;;
  esac
done

say()  { printf '\n\033[1m== %s\033[0m\n' "$*"; }
ok()   { printf '   ok   %s\n' "$*"; }
warn() { printf '   !    %s\n' "$*"; }
die()  { printf '\n\033[31mERROR: %s\033[0m\n' "$*" >&2; exit 1; }

# ---------------------------------------------------------------- environment
say "environment"
[ "$(uname -s)" = "Darwin" ] || die "macOS only"
[ "$(uname -m)" = "arm64" ] || die "Apple Silicon (arm64) required, no Intel/Rosetta"
CHIP="$(sysctl -n machdep.cpu.brand_string 2>/dev/null || echo 'Apple Silicon')"
RAM_GIB="$(( $(sysctl -n hw.memsize) / 1073741824 ))"
MACOS="$(sw_vers -productVersion)"
ok "$CHIP · ${RAM_GIB} GB · macOS $MACOS"

if [ "$RAM_GIB" -lt 24 ]; then
  die "24 GB of unified memory required (tested on M5 Pro 24 GB and M3 Max 128 GB)"
elif [ "$RAM_GIB" -lt 32 ]; then
  warn "24 GB: it works, but the memory margin is thin. Keep the charger plugged in and heavy apps closed."
fi

case "$CHIP" in
  *"M5"*) [ "${MACOS%%.*}" -ge 26 ] || warn "M5 requires macOS 26.2 or newer" ;;
esac

HAVE_UV=$(command -v uv || true)
[ -n "$HAVE_UV" ] || die "uv is missing:  brew install uv"
ok "uv $("$HAVE_UV" --version | awk '{print $2}')"

HAVE_FFMPEG=$(command -v ffmpeg || true)
[ -n "$HAVE_FFMPEG" ] && ok "ffmpeg ${HAVE_FFMPEG}" || warn "no ffmpeg (needed for transcription and covers):  brew install ffmpeg"

HAVE_SWIFTC=$(command -v swiftc || true)
[ -n "$HAVE_SWIFTC" ] && ok "swiftc (Xcode) found" || warn "no swiftc: the native app will not be built (the browser UI still works)"

[ -x "/opt/homebrew/opt/ffmpeg-full/bin/ffmpeg" ] && ok "ffmpeg-full present (better MP3 encoding)"

say "mlx-Yue project at $PROJECT"
if [ "$CHECK_ONLY" = "1" ]; then
  [ -d "$PROJECT/.venv" ] && ok "virtualenv installed" || warn "virtualenv missing (uv sync)"
  [ -f "$PROJECT/models/converted/conversion.json" ] && ok "generator weights" || warn "weights missing"
  [ -f "$PROJECT/models/vae/config.json" ] && ok "VAE" || warn "VAE missing"
  python3 "$ROOT/patches/apply_patches.py" --project "$PROJECT" --check || true
  "$PROJECT/.venv/bin/mlx-yue" doctor --model "$PROJECT/models/converted" --vae "$PROJECT/models/vae" 2>/dev/null \
    | python3 -c "import json,sys; d=json.load(sys.stdin); print('   doctor:', d['status'], d['checks'])" || warn "doctor not available"
  exit 0
fi

# ---------------------------------------------------------------- checkout
if [ -d "$PROJECT/.git" ]; then
  ok "existing checkout, running git pull"
  git -C "$PROJECT" pull --ff-only || warn "could not update (continuing with what is on disk)"
else
  mkdir -p "$(dirname "$PROJECT")"
  git clone --depth 1 "$UPSTREAM" "$PROJECT"
  ok "cloned from $UPSTREAM"
fi
cd "$PROJECT"

# ---------------------------------------------------------------- patches
say "patches (memory guard and transcription budget)"
python3 "$ROOT/patches/apply_patches.py" --project "$PROJECT"

# ---------------------------------------------------------------- python environment
say "Python environment (uv sync, no dev group)"
if [ "$WITH_TRANSCRIBE" = "1" ]; then
  uv sync --frozen --no-dev --extra transcription
else
  uv sync --frozen --no-dev
fi
uv pip install --python .venv/bin/python hf_transfer >/dev/null 2>&1 || warn "hf_transfer not installed (downloads will be slower)"
ok "environment ready"

# ---------------------------------------------------------------- weights
PY=".venv/bin/python"
if [ -f models/converted/conversion.json ] && [ -f models/vae/config.json ]; then
  ok "weights already present, skipping the download (~10.5 GB)"
else
  say "downloading weights (~10.5 GB: AR bf16/8bit + NAR + VAE)"
  HF_HUB_ENABLE_HF_TRANSFER=1 "$PY" - <<PYEOF
from huggingface_hub import snapshot_download
snapshot_download("$WEIGHTS_REPO", local_dir="models/converted")
snapshot_download("$VAE_REPO", local_dir="models/vae")
PYEOF
  # the doctor rejects unexpected files inside the model directories
  rm -rf models/converted/.cache models/vae/.cache models/converted/.gitattributes models/vae/.gitattributes
  ok "weights ready"
  du -sh models/converted models/vae | sed 's/^/   /'
fi

printf '{\n  "model": "models/converted",\n  "vae": "models/vae"\n}\n' > models/paths.json

# ---------------------------------------------------------------- transcription
if [ "$WITH_TRANSCRIBE" = "1" ]; then
  say "transcription models (SheetSage2 + MERT2-FullSong, ~2.6 GB)"
  HF_HUB_ENABLE_HF_TRANSFER=1 "$PY" - <<'PYEOF'
from huggingface_hub import snapshot_download
pairs = (("m-a-p/SheetSage2", "eab522a8168e8b8b8c4856bf8609cd86198f01fe"),
         ("m-a-p/MERT-v2-FullSong", "d8ba1c745e733b3908ce6ad16ebeb17ac7600a42"))
for repo, rev in pairs:
    path = snapshot_download(repo, revision=rev, allow_patterns=["config.json", "model.safetensors"])
    print("   ok  ", repo, "->", path)
    # with --offline the hub cannot resolve a revision without refs
    import pathlib
    ref = pathlib.Path(path).parents[1] / "refs"
    ref.mkdir(parents=True, exist_ok=True)
    (ref / "main").write_text(rev)
PYEOF
  mkdir -p models/transcription
  # find instead of globs: under set -euo pipefail a glob without matches aborts the installer
  SHEETSAGE="$(find "$HOME/.cache/huggingface/hub/models--m-a-p--SheetSage2/snapshots" -maxdepth 1 -mindepth 1 -type d 2>/dev/null | head -1)"
  MERT="$(find "$HOME/.cache/huggingface/hub/models--m-a-p--MERT-v2-FullSong/snapshots" -maxdepth 1 -mindepth 1 -type d 2>/dev/null | head -1)"
  [ -n "$SHEETSAGE" ] && ln -sfn "$SHEETSAGE" models/transcription/sheetsage2
  [ -n "$MERT" ] && ln -sfn "$MERT" models/transcription/mert2-fullsong
  ok "transcription ready (the studio reads models/transcription/)"
fi

# ---------------------------------------------------------------- verification
say "verification"
MLX_ENABLE_TF32=0 "$PY" -m lyra.cli doctor --model models/converted --vae models/vae \
  | "$PY" -c "import json,sys; d=json.load(sys.stdin); print('   doctor:', d['status'], d['checks']); sys.exit(0 if d['status']=='pass' else 1)" \
  || die "the doctor did not pass; see docs/TROUBLESHOOTING.md"

# ---------------------------------------------------------------- app
say "app"
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
  ok "config.json written, pointing at $PROJECT"
else
  python3 - "$CONFIG" "$PROJECT" <<'PYEOF'
import json, sys
path, project = sys.argv[1], sys.argv[2]
data = json.load(open(path))
if data.get("project") != project:
    data["project"] = project
    json.dump(data, open(path, "w"), indent=2)
    print("   ok   config.json updated ->", project)
else:
    print("   ok   config.json already pointed at the project")
PYEOF
fi

if [ "$BUILD_APP" = "1" ] && [ -n "$HAVE_SWIFTC" ]; then
  bash "$ROOT/build_app.sh" | tail -3 | sed 's/^/   /'
else
  warn "no native app: run  python3 $ROOT/server.py  and open http://127.0.0.1:8787"
fi

say "done"
cat <<EOF
   App:        ~/Applications/YuE2 Studio.app   (drag it to /Applications if you prefer)
   No app:     python3 "$ROOT/server.py"   ->   http://127.0.0.1:8787
   CLI:
     cd "$PROJECT" && ./.venv/bin/mlx-yue generate "$ROOT/examples/english-song.json" \\
        --model models/converted --vae models/vae --precision 8bit --offline \\
        --vae-core-frames 128 --memory-budget-gib 16 --output outputs/first-song

   The weights are CC-BY-NC-4.0: personal use, no commercial use.
   If something fails, read docs/TROUBLESHOOTING.md.
EOF
