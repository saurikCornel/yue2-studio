#!/usr/bin/env python3
"""YuE2 Studio — local backend.

Wraps the mlx-Yue CLI (generation, covers, transcription) for the native macOS
app. Standard library only; listens on 127.0.0.1.

Main endpoints:
  GET  /                       -> UI
  GET  /api/health             -> project, models, ffmpeg, power and patch state
  POST /api/generate           -> queue a song
  POST /api/cover              -> queue a cover (transcribe + generate)
  POST /api/transcribe         -> queue a transcription (audio -> ABC)
  POST /api/upload?name=x      -> upload audio into inputs/
  GET  /api/jobs, /api/jobs/<id>, POST /api/jobs/<id>/cancel
  GET  /api/library            -> generated songs
  POST /api/library/<id>/mp3   -> exporta mp3 320k
  POST /api/library/<id>/reveal, DELETE /api/library/<id>
  GET  /files/<relpath>        -> serve audio/text from outputs/ and inputs/ (Range)
"""
from __future__ import annotations

import json
import mimetypes
import os
import queue
import re
import shutil
import signal
import subprocess
import sys
import threading
import time
import urllib.parse
import uuid
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

HOME = Path.home()
STUDIO_DIR = Path(__file__).resolve().parent
CONFIG_PATH = STUDIO_DIR / "config.json"
FFMPEG_FULL = Path("/opt/homebrew/opt/ffmpeg-full/bin/ffmpeg")

DEFAULTS = {
    "project": str(HOME / "Projects" / "mlx-Yue"),
    "port": 8787,
    "vae_core_frames": 128,
    "precision": "8bit",
    "memory_budget_gib": 16,
    "transcription_model": "models/transcription/sheetsage2",
    "transcription_base_model": "models/transcription/mert2-fullsong",
    "console_visible": True,
}

STATE_LOCK = threading.Lock()
JOBS: dict = {}
JOB_ORDER: list = []
JOB_QUEUE: "queue.Queue[str]" = queue.Queue()
CURRENT_JOB = None


# ---------------------------------------------------------------- config

def load_config() -> dict:
    cfg = dict(DEFAULTS)
    if CONFIG_PATH.is_file():
        try:
            cfg.update(json.loads(CONFIG_PATH.read_text(encoding="utf-8")))
        except Exception:
            pass
    return cfg


def save_config(cfg: dict) -> dict:
    merged = dict(DEFAULTS)
    merged.update({k: v for k, v in cfg.items() if k in DEFAULTS})
    CONFIG_PATH.parent.mkdir(parents=True, exist_ok=True)
    CONFIG_PATH.write_text(json.dumps(merged, indent=2) + "\n", encoding="utf-8")
    return merged


# ---------------------------------------------------------------- helpers

def project_dir(cfg: dict) -> Path:
    return Path(cfg["project"]).expanduser().resolve()


def venv_bin(project: Path, name: str) -> Path:
    return project / ".venv" / "bin" / name


def slug(text: str, fallback: str = "song") -> str:
    base = re.sub(r"[^a-zA-Z0-9\-]+", "-", (text or "").strip().lower()).strip("-")
    base = re.sub(r"-{2,}", "-", base)[:42].strip("-")
    return base or fallback


def unique_id(project: Path, base: str) -> str:
    candidate, n = base, 2
    while (project / "outputs" / candidate).exists() or (project / "requests" / f"{candidate}.json").exists():
        candidate = f"{base}-{n}"
        n += 1
    return candidate


def inside(root: Path, target: Path) -> bool:
    try:
        target.resolve().relative_to(root.resolve())
        return True
    except Exception:
        return False


def ac_status() -> dict:
    try:
        out = subprocess.run(["pmset", "-g", "ps"], capture_output=True, text=True, timeout=5).stdout
    except Exception:
        return {"ac": None, "detail": "pmset unavailable"}
    ac = "AC Power" in out
    return {"ac": ac, "detail": out.strip().splitlines()[0] if out.strip() else ""}


def guard_patch_status(project: Path) -> str:
    path = project / "src" / "lyra" / "measure.py"
    if not path.is_file():
        return "unknown"
    text = path.read_text(encoding="utf-8", errors="ignore")
    if "transient_pressure_warnings" in text:
        m = re.search(r'YUE2_MIN_AVAILABLE_GIB", "([0-9.]+)"', text)
        return f"patched-{m.group(1)}gib" if m else "patched"
    return "stock"


# A double-clicked .app inherits launchd's minimal PATH (/usr/bin:/bin:/usr/sbin:/sbin),
# so Homebrew tools are invisible to the backend and to everything it spawns. The
# transcriber decodes audio with a bare "ffmpeg" (lyra/transcription/pipeline.py), which
# raised FileNotFoundError when the app was opened from the Finder. Jobs get this merged
# PATH instead of whatever the GUI handed us.
TOOL_DIRS = ("/opt/homebrew/bin", "/opt/homebrew/opt/ffmpeg-full/bin", "/usr/local/bin",
             "/opt/homebrew/sbin", "/usr/local/sbin")


def tool_path(project=None) -> str:
    parts = [p for p in os.environ.get("PATH", "").split(os.pathsep) if p]
    extra: list = list(TOOL_DIRS)
    if project is not None:
        extra.insert(0, str(Path(project) / ".venv" / "bin"))
    for directory in extra:
        if directory not in parts and Path(directory).is_dir():
            parts.append(directory)
    return os.pathsep.join(parts)


def find_ffmpeg() -> str:
    """Absolute ffmpeg path, resolved past the minimal PATH of a GUI launch."""
    for candidate in [FFMPEG_FULL] + [Path(d) / "ffmpeg" for d in TOOL_DIRS]:
        if candidate.is_file() and os.access(candidate, os.X_OK):
            return str(candidate)
    return shutil.which("ffmpeg", path=tool_path()) or ""


def require_ffmpeg() -> None:
    if not find_ffmpeg():
        raise ValueError("ffmpeg not found; transcription and covers decode the audio with it "
                         "(install it with: brew install ffmpeg)")


def ffmpeg_binary() -> str:
    return find_ffmpeg() or "ffmpeg"


# ---------------------------------------------------------------- jobs

def new_job(kind: str, request: dict, output_name: str, cmd: list, project: Path) -> dict:
    job = {
        "id": uuid.uuid4().hex[:12],
        "kind": kind,
        "request": request,
        "output_name": output_name,
        "cmd": cmd,
        "project": str(project),
        "state": "queued",
        "phase": "queued",
        "progress": 0.0,
        "log": [],
        "started": None,
        "ended": None,
        "seconds": None,
        "error": None,
        "result": None,
        "proc": None,
    }
    with STATE_LOCK:
        JOBS[job["id"]] = job
        JOB_ORDER.append(job["id"])
    JOB_QUEUE.put(job["id"])
    return job


PROGRESS_RE = re.compile(r"(\d+)\s*/\s*(\d+)\s+steps?\s*\((\d+)%\)")


def advance(job: dict, line: str) -> None:
    low = line.lower()
    m = PROGRESS_RE.search(line)
    if m:
        done, total, pct = int(m.group(1)), int(m.group(2)), int(m.group(3))
        job["phase"] = "synthesizing audio"
        job["progress"] = max(job["progress"], 0.38 + 0.57 * (pct / 100.0))
        job["steps"] = [done, total]
        return
    if "planning" in low or "abc" in low and "plan" in low:
        job["phase"] = "planning the score"
        job["progress"] = max(job["progress"], 0.06)
    elif "semantic" in low:
        job["phase"] = "generating tokens (AR)"
        job["progress"] = max(job["progress"], 0.16)
    elif "synthes" in low or "acoustic" in low or "flow" in low or "nar" in low:
        job["phase"] = "synthesizing audio"
        job["progress"] = max(job["progress"], 0.38)
    elif "vae" in low or "decod" in low:
        job["phase"] = "decoding audio (VAE)"
        job["progress"] = max(job["progress"], 0.95)
    elif "transcri" in low or "sheetsage" in low:
        job["phase"] = "transcribing"
        job["progress"] = max(job["progress"], 0.3)


def run_job(job: dict) -> None:
    global CURRENT_JOB
    project = Path(job["project"])
    job["state"] = "running"
    job["started"] = time.time()
    CURRENT_JOB = job["id"]
    env = dict(os.environ)
    env["PATH"] = tool_path(project)
    env["MLX_ENABLE_TF32"] = "0"
    env["LYRA_VAE"] = str(project / "models" / "vae")
    env["PYTHONUNBUFFERED"] = "1"
    try:
        proc = subprocess.Popen(
            job["cmd"], cwd=str(project), env=env, stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT, text=True, bufsize=1, errors="replace",
        )
        job["proc"] = proc
        assert proc.stdout is not None
        for raw in proc.stdout:
            line = raw.rstrip("\n")
            if not line:
                continue
            job["log"].append(line)
            if len(job["log"]) > 600:
                del job["log"][:200]
            advance(job, line)
        code = proc.wait()
        job["seconds"] = round(time.time() - job["started"], 1)
        if code == 0:
            job["state"] = "done"
            job["phase"] = "done"
            job["progress"] = 1.0
            job["result"] = read_result(project, job["output_name"])
            if job["result"].get("audio"):
                job["result"]["mp3_url"] = ensure_mp3(project, job["output_name"])
        else:
            job["state"] = "failed"
            job["error"] = f"process exited with code {code}"
            tail = [l for l in job["log"] if "Error" in l or "error" in l][-3:]
            if tail:
                job["error"] += " — " + " | ".join(t.strip()[:200] for t in tail)
    except Exception as exc:  # pragma: no cover
        job["state"] = "failed"
        job["error"] = f"{type(exc).__name__}: {exc}"
        job["seconds"] = round(time.time() - (job["started"] or time.time()), 1)
    finally:
        job["proc"] = None
        CURRENT_JOB = None
        if job["state"] == "cancelled":
            job["phase"] = "cancelled"


def artifact_dir(folder: Path) -> Path:
    """Covers keep the song in <output>/song/; direct generations in <output>/."""
    if (folder / "audio.flac").is_file():
        return folder
    nested = folder / "song"
    if (nested / "audio.flac").is_file():
        return nested
    return folder


def read_result(project: Path, name: str) -> dict:
    out = project / "outputs" / name
    artifact = artifact_dir(out)
    result = {"name": name}
    rj = artifact / "result.json"
    if rj.is_file():
        try:
            data = json.loads(rj.read_text(encoding="utf-8"))
            result["status"] = data.get("status")
            result["audio_seconds"] = data.get("audio_seconds")
            result["truncated"] = data.get("truncated")
        except Exception:
            pass
    audio = artifact / "audio.flac"
    if audio.is_file():
        rel = audio.relative_to(project).as_posix()
        result["audio"] = str(audio)
        result["audio_url"] = "/files/" + rel
        result["bytes"] = audio.stat().st_size
    abc = artifact / "score.abc"
    if abc.is_file():
        result["abc"] = str(abc)
        result["abc_url"] = "/files/" + abc.relative_to(project).as_posix()
    return result


def ensure_mp3(project: Path, name: str) -> str:
    """Export the 320k MP3 next to the artifact; returns its /files/ URL or "".

    Covers keep the song in <output>/song/, so the source and the target both come from
    artifact_dir() — never from the top of the output folder.
    """
    artifact = artifact_dir(project / "outputs" / name)
    source = artifact / "audio.flac"
    if not source.is_file():
        return ""
    target = artifact / "audio.mp3"
    if not target.is_file() or target.stat().st_mtime < source.stat().st_mtime:
        cmd = [ffmpeg_binary(), "-y", "-hide_banner", "-loglevel", "error", "-i", str(source),
               "-c:a", "libmp3lame", "-b:a", "320k", str(target)]
        done = subprocess.run(cmd, capture_output=True, text=True)
        if done.returncode != 0 or not target.is_file():
            return ""
    return "/files/" + target.relative_to(project).as_posix()


def worker() -> None:
    while True:
        job_id = JOB_QUEUE.get()
        job = JOBS.get(job_id)
        if job is None:
            continue
        if job.get("state") == "cancelled":
            continue
        run_job(job)
        JOB_QUEUE.task_done()


def cancel_job(job: dict) -> bool:
    proc = job.get("proc")
    if job["state"] in ("queued", "running"):
        job["state"] = "cancelled"
        if proc is not None:
            try:
                proc.send_signal(signal.SIGTERM)
                for _ in range(20):
                    if proc.poll() is not None:
                        break
                    time.sleep(0.25)
                if proc.poll() is None:
                    proc.kill()
            except Exception:
                pass
        return True
    return False


# ---------------------------------------------------------------- library

def library(project: Path) -> list:
    out = project / "outputs"
    items = []
    if not out.is_dir():
        return items
    for entry in sorted(out.iterdir(), key=lambda p: p.stat().st_mtime if p.exists() else 0, reverse=True):
        if not entry.is_dir():
            continue
        item = {"name": entry.name, "dir": str(entry), "mtime": entry.stat().st_mtime}
        artifact = artifact_dir(entry)
        rj = artifact / "result.json"
        if rj.is_file():
            try:
                data = json.loads(rj.read_text(encoding="utf-8"))
                item["status"] = data.get("status")
                item["audio_seconds"] = data.get("audio_seconds")
                item["truncated"] = data.get("truncated")
            except Exception:
                pass
        rq = artifact / "request.json"
        if rq.is_file():
            try:
                req = json.loads(rq.read_text(encoding="utf-8"))
                item["style"] = req.get("style")
                item["mode"] = req.get("cot")
                item["seed"] = req.get("seed")
                item["lyrics"] = (req.get("lyrics") or "")[:4000]
            except Exception:
                pass
        audio = artifact / "audio.flac"
        if audio.is_file():
            item["audio"] = "/files/" + audio.relative_to(project).as_posix()
            item["bytes"] = audio.stat().st_size
        mp3 = artifact / "audio.mp3"
        if mp3.is_file():
            item["mp3"] = "/files/" + mp3.relative_to(project).as_posix()
        abc = artifact / "score.abc"
        if abc.is_file():
            item["abc"] = "/files/" + abc.relative_to(project).as_posix()
        if (entry / "cover.json").is_file():
            item["kind"] = "cover"
        elif (entry / "transcription.mid").is_file() or (entry / "events.json").is_file():
            item["kind"] = "transcription"
        else:
            item["kind"] = "song"
        items.append(item)
    return items


# ---------------------------------------------------------------- request builders

def build_generate_request(cfg: dict, payload: dict) -> tuple:
    project = project_dir(cfg)
    style = (payload.get("style") or "").strip()
    lyrics = (payload.get("lyrics") or "").strip()
    if not style:
        raise ValueError("style prompt cannot be empty")
    if not lyrics:
        raise ValueError("lyrics cannot be empty")
    base = slug(payload.get("id") or style.split(",")[0], "song")
    name = unique_id(project, base)
    steps = int(payload.get("steps") or 32)
    precision = payload.get("precision") or cfg["precision"]
    request = {
        "id": name,
        "style": style,
        "lyrics": lyrics,
        "cot": payload.get("mode") or "full",
        "seed": int(payload.get("seed") or 0),
        "generation_config": {"ode_steps": steps},
    }
    if payload.get("cfg_scale"):
        request["cfg_scale"] = float(payload["cfg_scale"])
    req_dir = project / "requests"
    req_dir.mkdir(parents=True, exist_ok=True)
    req_path = req_dir / f"{name}.json"
    req_path.write_text(json.dumps(request, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    cmd = [
        str(venv_bin(project, "mlx-yue")), "generate", str(req_path.relative_to(project)),
        "--model", "models/converted", "--vae", "models/vae",
        "--precision", precision, "--offline",
        "--vae-core-frames", str(int(cfg["vae_core_frames"])),
        "--memory-budget-gib", str(float(cfg["memory_budget_gib"])),
        "--output", f"outputs/{name}",
    ]
    return name, request, cmd


def build_cover_request(cfg: dict, payload: dict) -> tuple:
    project = project_dir(cfg)
    audio = Path(payload.get("audio") or "")
    if not audio.is_file() or not inside(project / "inputs", audio):
        raise ValueError("pick a valid audio file from inputs/")
    require_ffmpeg()
    style = (payload.get("style") or "").strip()
    lyrics = (payload.get("lyrics") or "").strip()
    if not style or not lyrics:
        raise ValueError("style and lyrics are required for a cover")
    base = slug(f"cover-{audio.stem}", "cover")
    name = unique_id(project, base)
    steps = int(payload.get("steps") or 32)
    precision = payload.get("precision") or cfg["precision"]
    lyrics_path = project / "requests" / f"{name}.lyrics.txt"
    lyrics_path.parent.mkdir(parents=True, exist_ok=True)
    lyrics_path.write_text(lyrics, encoding="utf-8")
    request = {
        "id": name, "style": style, "lyrics": lyrics,
        "cot": payload.get("mode") or "melody", "seed": int(payload.get("seed") or 0),
        "generation_config": {"ode_steps": steps},
        "source_audio": str(audio),
    }
    (project / "requests" / f"{name}.json").write_text(
        json.dumps(request, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    cmd = [
        str(venv_bin(project, "mlx-yue")), "cover", "--audio", str(audio),
        "--style", style, "--lyrics-file", str(lyrics_path.relative_to(project)),
        "--task", payload.get("task") or "melody-full",
        "--mode", request["cot"], "--seed", str(request["seed"]),
        "--transcription-model", cfg["transcription_model"],
        "--base-model", cfg["transcription_base_model"],
        "--model", "models/converted", "--vae", "models/vae",
        "--precision", precision, "--offline",
        "--vae-core-frames", str(int(cfg["vae_core_frames"])),
        "--memory-budget-gib", str(float(cfg["memory_budget_gib"])),
        "--output", f"outputs/{name}",
    ]
    return name, request, cmd


def build_transcribe_request(cfg: dict, payload: dict) -> tuple:
    project = project_dir(cfg)
    audio = Path(payload.get("audio") or "")
    if not audio.is_file() or not inside(project / "inputs", audio):
        raise ValueError("pick a valid audio file from inputs/")
    require_ffmpeg()
    name = unique_id(project, slug(f"transcription-{audio.stem}", "transcription"))
    cmd = [
        str(venv_bin(project, "mlx-yue")), "transcribe", str(audio),
        "--task", payload.get("task") or "full",
        "--model", cfg["transcription_model"],
        "--base-model", cfg["transcription_base_model"],
        "--output", f"outputs/{name}", "--offline",
        "--memory-budget-gib", str(float(cfg["memory_budget_gib"])),
    ]
    media_seconds = payload.get("max_seconds")
    if media_seconds:
        cmd += ["--max-seconds", str(int(media_seconds))]
    request = {"id": name, "audio": str(audio), "task": payload.get("task") or "full"}
    (project / "requests").mkdir(parents=True, exist_ok=True)
    (project / "requests" / f"{name}.json").write_text(
        json.dumps(request, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return name, request, cmd


# ---------------------------------------------------------------- http

class Handler(BaseHTTPRequestHandler):
    server_version = "YuE2Studio/1.0"
    cfg = load_config()

    def log_message(self, fmt, *args):  # stay quiet
        pass

    # --- helpers
    def send_json(self, data, code=200):
        body = json.dumps(data, ensure_ascii=False).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def send_bytes(self, body: bytes, ctype: str, code=200, extra=None):
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        for k, v in (extra or {}).items():
            self.send_header(k, v)
        self.end_headers()
        self.wfile.write(body)

    def read_body(self) -> bytes:
        length = int(self.headers.get("Content-Length") or 0)
        return self.rfile.read(length) if length else b""

    def json_body(self) -> dict:
        raw = self.read_body()
        if not raw:
            return {}
        return json.loads(raw.decode("utf-8"))

    # --- GET
    def do_GET(self):
        parsed = urllib.parse.urlparse(self.path)
        path = parsed.path
        project = project_dir(self.cfg)
        if path in ("/", "/index.html"):
            index = STUDIO_DIR / "ui" / "index.html"
            if not index.is_file():
                return self.send_json({"error": "ui/index.html is missing"}, 500)
            return self.send_bytes(index.read_bytes(), "text/html; charset=utf-8")
        if path == "/api/health":
            return self.send_json(self.health())
        if path == "/api/config":
            return self.send_json(self.cfg)
        if path == "/api/jobs":
            with STATE_LOCK:
                return self.send_json({"jobs": [self.public_job(JOBS[j]) for j in JOB_ORDER[-40:]]})
        if path.startswith("/api/jobs/"):
            job = JOBS.get(path.split("/")[3])
            if not job:
                return self.send_json({"error": "unknown job"}, 404)
            return self.send_json(self.public_job(job))
        if path == "/api/library":
            return self.send_json({"songs": library(project), "inputs": self.inputs(project)})
        if path == "/api/abc":
            query = urllib.parse.parse_qs(parsed.query)
            rel = (query.get("path") or [""])[0]
            target = (project / rel).resolve()
            if not inside(project, target) or not target.is_file():
                return self.send_json({"error": "invalid file"}, 400)
            return self.send_bytes(target.read_bytes(), "text/plain; charset=utf-8")
        if path.startswith("/files/"):
            return self.serve_file(project, path[len("/files/"):])
        return self.send_json({"error": "not found"}, 404)

    # --- POST
    def do_POST(self):
        parsed = urllib.parse.urlparse(self.path)
        path = parsed.path
        try:
            if path == "/api/generate":
                name, request, cmd = build_generate_request(self.cfg, self.json_body())
                job = new_job("generate", request, name, cmd, project_dir(self.cfg))
                return self.send_json({"job": self.public_job(job)}, 202)
            if path == "/api/cover":
                name, request, cmd = build_cover_request(self.cfg, self.json_body())
                job = new_job("cover", request, name, cmd, project_dir(self.cfg))
                return self.send_json({"job": self.public_job(job)}, 202)
            if path == "/api/transcribe":
                name, request, cmd = build_transcribe_request(self.cfg, self.json_body())
                job = new_job("transcribe", request, name, cmd, project_dir(self.cfg))
                return self.send_json({"job": self.public_job(job)}, 202)
            if path == "/api/upload":
                query = urllib.parse.parse_qs(parsed.query)
                raw_name = os.path.basename((query.get("name") or ["audio.wav"])[0])
                suffix = Path(raw_name).suffix.lower() or ".wav"
                if suffix not in {".wav", ".flac", ".mp3", ".m4a", ".aac", ".ogg", ".opus", ".aiff", ".aif"}:
                    suffix = ".wav"
                stem = slug(Path(raw_name).stem, "audio")[:60]
                inputs = project_dir(self.cfg) / "inputs"
                inputs.mkdir(parents=True, exist_ok=True)
                target = inputs / f"{stem}{suffix}"
                data = self.read_body()
                if not data:
                    return self.send_json({"error": "empty body"}, 400)
                target.write_bytes(data)
                return self.send_json({"path": str(target), "name": target.name, "bytes": len(data)})
            if path.startswith("/api/jobs/") and path.endswith("/cancel"):
                job = JOBS.get(path.split("/")[3])
                if not job:
                    return self.send_json({"error": "unknown job"}, 404)
                return self.send_json({"cancelled": cancel_job(job)})
            if path.startswith("/api/library/"):
                parts = path.split("/")
                name = urllib.parse.unquote(parts[3])
                if len(parts) == 5 and parts[4] == "mp3":
                    return self.export_mp3(name)
                if len(parts) == 5 and parts[4] == "reveal":
                    target = project_dir(self.cfg) / "outputs" / name
                    if not inside(project_dir(self.cfg) / "outputs", target):
                        return self.send_json({"error": "invalid path"}, 400)
                    subprocess.Popen(["open", "-R", str(target)])
                    return self.send_json({"ok": True})
            if path == "/api/config":
                self.cfg = save_config(self.json_body())
                return self.send_json(self.cfg)
            if path == "/api/reveal":
                return self.send_json({"ok": False, "error": "not supported"})
        except ValueError as exc:
            return self.send_json({"error": str(exc)}, 400)
        except Exception as exc:
            return self.send_json({"error": f"{type(exc).__name__}: {exc}"}, 500)
        return self.send_json({"error": "not found"}, 404)

    # --- DELETE
    def do_DELETE(self):
        path = urllib.parse.urlparse(self.path).path
        if path.startswith("/api/library/"):
            name = urllib.parse.unquote(path.split("/")[3])
            project = project_dir(self.cfg)
            target = project / "outputs" / name
            if not inside(project / "outputs", target) or not target.is_dir():
                return self.send_json({"error": "invalid song"}, 400)
            shutil.rmtree(target)
            for suffix in (".resources.json", ".resources.jsonl"):
                stale = project / "outputs" / f"{name}{suffix}"
                if stale.is_file():
                    stale.unlink()
            return self.send_json({"deleted": name})
        return self.send_json({"error": "not found"}, 404)

    # --- response helpers
    def public_job(self, job: dict) -> dict:
        data = {k: v for k, v in job.items() if k not in ("proc", "cmd", "project")}
        data["log_tail"] = job["log"][-60:]
        data["queue_position"] = self.queue_position(job["id"])
        return data

    def queue_position(self, job_id: str) -> int:
        if JOBS.get(job_id, {}).get("state") != "queued":
            return 0
        pending = [j for j in JOB_ORDER if JOBS[j]["state"] == "queued"]
        return pending.index(job_id) + 1 if job_id in pending else 0

    def inputs(self, project: Path) -> list:
        folder = project / "inputs"
        if not folder.is_dir():
            return []
        return [{"name": p.name, "path": str(p), "bytes": p.stat().st_size,
                 "url": f"/files/inputs/{urllib.parse.quote(p.name)}"}
                for p in sorted(folder.iterdir()) if p.is_file() and not p.name.startswith(".")]

    def health(self) -> dict:
        project = project_dir(self.cfg)
        venv = venv_bin(project, "mlx-yue")
        data = {
            "studio": str(STUDIO_DIR),
            "project": str(project),
            "project_ok": project.is_dir(),
            "cli": str(venv),
            "cli_ok": venv.is_file(),
            "models_ok": (project / "models" / "converted" / "conversion.json").is_file(),
            "vae_ok": (project / "models" / "vae" / "config.json").is_file(),
            "ffmpeg": ffmpeg_binary(),
            "ffmpeg_ok": bool(find_ffmpeg()),
            "config": self.cfg,
            "guard": guard_patch_status(project),
            "power": ac_status(),
            "jobs": {"queued": sum(1 for j in JOBS.values() if j["state"] == "queued"),
                     "running": sum(1 for j in JOBS.values() if j["state"] == "running")},
            "disk_free_gb": round(shutil.disk_usage(str(project)).free / 1e9, 1) if project.is_dir() else None,
        }
        try:
            data["version"] = subprocess.run([str(venv), "--help"], capture_output=True, text=True,
                                             timeout=10, cwd=str(project)).returncode == 0
        except Exception:
            data["version"] = False
        return data

    def export_mp3(self, name: str):
        project = project_dir(self.cfg)
        folder = project / "outputs" / name
        if not inside(project / "outputs", folder) or not folder.is_dir():
            return self.send_json({"error": "invalid song"}, 400)
        target = artifact_dir(folder) / "audio.mp3"
        url = ensure_mp3(project, name)
        if not url:
            return self.send_json({"error": "no audio.flac found, or ffmpeg failed to encode"}, 400)
        return self.send_json({"mp3": url, "bytes": target.stat().st_size})

    def serve_file(self, project: Path, rel: str):
        rel = urllib.parse.unquote(rel)
        target = (project / rel).resolve()
        allowed = [project / "outputs", project / "inputs", project / "models"]
        if not any(inside(root, target) for root in allowed) or not target.is_file():
            return self.send_json({"error": "invalid file"}, 404)
        ctype = mimetypes.guess_type(str(target))[0] or "application/octet-stream"
        size = target.stat().st_size
        start, end = 0, size - 1
        range_header = self.headers.get("Range")
        if range_header:
            m = re.match(r"bytes=(\d*)-(\d*)", range_header)
            if m:
                if m.group(1):
                    start = int(m.group(1))
                if m.group(2):
                    end = min(int(m.group(2)), size - 1)
        length = end - start + 1
        self.send_response(206 if range_header else 200)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(length))
        self.send_header("Accept-Ranges", "bytes")
        if range_header:
            self.send_header("Content-Range", f"bytes {start}-{end}/{size}")
        self.end_headers()
        with target.open("rb") as fh:
            fh.seek(start)
            remaining = length
            while remaining > 0:
                chunk = fh.read(min(1 << 20, remaining))
                if not chunk:
                    break
                self.wfile.write(chunk)
                remaining -= len(chunk)


def main() -> None:
    cfg = load_config()
    port = int(os.environ.get("YUE2_STUDIO_PORT") or cfg.get("port") or 8787)
    threading.Thread(target=worker, daemon=True).start()
    server = ThreadingHTTPServer(("127.0.0.1", port), Handler)
    Handler.cfg = cfg
    print(json.dumps({"studio": str(STUDIO_DIR), "port": port, "project": cfg["project"]}), flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
