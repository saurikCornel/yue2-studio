#!/usr/bin/env python3
"""Aplica (o revierte) los parches de YuE2 Studio sobre un checkout de mlx-Yue.

Los parches son dos, y ambos son para máquinas de 24 GB:

  1. src/lyra/measure.py — el guard de memoria aborta ante cualquier lectura de
     presión distinta de "normal", y macOS marca un aviso transitorio (nivel 2)
     mientras comprime la carga de 3 GiB de pesos, aunque queden GiB libres.
     El parche tolera el nivel 2 mientras haya >= YUE2_MIN_AVAILABLE_GIB (1 por
     defecto) y deja estrictos el presupuesto de footprint y los chequeos de swap.
     Configurable:  YUE2_MIN_AVAILABLE_GIB=2 ./install.sh

  2. src/lyra/music_tools/transcribe.py — el helper `transcribe` trae
     --memory-budget-gib 24 por defecto, y el guard exige budget <= RAM total - 4,
     así que en una máquina de 24 GB (límite 20) siempre falla. El parche lo
     calcula desde la RAM disponible (24 GB -> 16).

Uso:
    python3 patches/apply_patches.py --project ~/Projects/mlx-Yue          # aplicar
    python3 patches/apply_patches.py --project ~/Projects/mlx-Yue --check   # solo verificar
    python3 patches/apply_patches.py --project ~/Projects/mlx-Yue --revert  # volver atrás
"""
from __future__ import annotations

import argparse
import os
import subprocess
import sys
from pathlib import Path

MARKER = "YuE2 Studio patch"

MEASURE_OLD = '''        pressure = sample["system_memory_pressure_level"]
        if pressure != 1:
            raise MemoryError(f"System memory pressure is not normal (level={pressure})")
        if sample["system_available_bytes"] < 2 * _GIB:
            raise MemoryError("Less than 2 GiB of available system memory remains")
'''

MEASURE_NEW = '''        pressure = sample["system_memory_pressure_level"]
        if pressure != 1:
            # {marker}: en Apple Silicon macOS marca nivel 2 de forma transitoria
            # mientras comprime el burst de carga de pesos (visto: 1 sample de
            # 0.25 s con 6 GiB disponibles). Se tolera mientras haya
            # min_available_gib libres; el presupuesto de footprint y el swap
            # siguen estrictos. Configurable con YUE2_MIN_AVAILABLE_GIB.
            if sample["system_available_bytes"] < self.min_available_gib * _GIB:
                raise MemoryError(f"System memory pressure is not normal (level={{pressure}})")
            self.monitor.metadata["transient_pressure_warnings"] = (
                self.monitor.metadata.get("transient_pressure_warnings", 0) + 1)
        if sample["system_available_bytes"] < self.min_available_gib * _GIB:
            raise MemoryError(f"Less than {{self.min_available_gib:g}} GiB of available system memory remains")
'''.format(marker=MARKER)

MEASURE_INIT_OLD = '''        self.backend, self.memory_budget_gib = backend, float(memory_budget_gib)
        self._entered = False'''

MEASURE_INIT_NEW = '''        self.backend, self.memory_budget_gib = backend, float(memory_budget_gib)
        # {marker}
        self.min_available_gib = max(0.5, float(os.environ.get("YUE2_MIN_AVAILABLE_GIB", "1")))
        self._entered = False'''.format(marker=MARKER)

TRANSCRIBE_OLD = "    parser.add_argument('--memory-budget-gib', type=float, default=24)"

TRANSCRIBE_NEW = '''    # {marker}: el default 24 de upstream viola el chequeo del guard
    # (exige budget <= RAM total - 4) en máquinas de 24 GB. Se calcula desde la RAM.
    def default_budget():
        try:
            import psutil
            total_gib = psutil.virtual_memory().total / 2 ** 30
            return float(max(8, min(48, int(total_gib) - 8)))
        except Exception:
            return 16.0

    parser.add_argument('--memory-budget-gib', type=float, default=default_budget())'''.format(marker=MARKER)

PATCHES = [
    {
        "name": "guard de memoria tolerante (24 GB)",
        "path": "src/lyra/measure.py",
        "edits": (("init", MEASURE_INIT_OLD, MEASURE_INIT_NEW), ("check", MEASURE_OLD, MEASURE_NEW)),
    },
    {
        "name": "presupuesto de transcripción según RAM",
        "path": "src/lyra/music_tools/transcribe.py",
        "edits": (("budget", TRANSCRIBE_OLD, TRANSCRIBE_NEW),),
    },
]


def read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def write(path: Path, text: str) -> None:
    path.write_text(text, encoding="utf-8")


def state(text: str, patch: dict) -> str:
    """applied | partial | absent"""
    has_marker = MARKER in text
    changed = [new in text for _, _, new in patch["edits"]]
    if all(changed):
        return "applied"
    if has_marker or any(changed):
        return "partial"
    return "absent"


def apply_patch(project: Path, patch: dict, dry: bool) -> str:
    target = project / patch["path"]
    if not target.is_file():
        return f"SALTEADO {patch['path']} (no existe)"
    text = original = read(target)
    current = state(text, patch)
    if current == "applied":
        return f"ok      {patch['path']} (ya parcheado)"
    if current == "partial":
        return (f"ATENCION {patch['path']}: contiene cambios previos o una versión distinta del parche. "
                f"Revertí con --revert o `git checkout {patch['path']}` y volvé a aplicar.")
    for label, old, new in patch["edits"]:
        if old not in text:
            return (f"FALLO   {patch['path']} ({label}): no encontré el bloque esperado — "
                    f"¿cambió upstream? Revisá docs/PATCHES.md.")
        text = text.replace(old, new, 1)
    if dry:
        return f"dry-run {patch['path']} (se aplicaría)"
    write(target, text)
    return f"aplicado {patch['path']} ({len(text) - len(original):+d} bytes)"


def revert_patch(project: Path, patch: dict) -> str:
    target = project / patch["path"]
    if not target.is_file():
        return f"SALTEADO {patch['path']} (no existe)"
    rel = patch["path"]
    done = subprocess.run(["git", "checkout", "--", rel], cwd=str(project),
                          capture_output=True, text=True)
    if done.returncode != 0:
        return f"FALLO   {rel}: {done.stderr.strip()[:160]}"
    return f"revertido {rel}"


def main() -> int:
    parser = argparse.ArgumentParser(description="Parches de YuE2 Studio para mlx-Yue")
    parser.add_argument("--project", default=os.environ.get("YUE2_PROJECT", str(Path.home() / "Projects" / "mlx-Yue")))
    parser.add_argument("--check", action="store_true", help="solo informar el estado")
    parser.add_argument("--revert", action="store_true", help="volver a los archivos originales")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    project = Path(args.project).expanduser().resolve()
    if not (project / "src" / "lyra").is_dir():
        print(f"No parece un checkout de mlx-Yue: {project}")
        return 2

    if args.revert:
        for patch in PATCHES:
            print(revert_patch(project, patch))
        return 0

    if args.check:
        for patch in PATCHES:
            target = project / patch["path"]
            text = read(target) if target.is_file() else ""
            print(f"{state(text, patch):8s} {patch['path']}  —  {patch['name']}")
        return 0

    failures = 0
    for patch in PATCHES:
        line = apply_patch(project, patch, args.dry_run)
        print(line)
        failures += line.startswith(("FALLO", "ATENCION"))
    print(f"\n{len(PATCHES) - failures}/{len(PATCHES)} parches ok")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
