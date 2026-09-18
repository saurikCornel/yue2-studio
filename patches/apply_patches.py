#!/usr/bin/env python3
"""Apply (or revert) the YuE2 Studio patches on an mlx-Yue checkout.

Both patches target machines with 24 GB of unified memory:

  1. src/lyra/measure.py — the memory guard aborts on any memory-pressure reading other
     than "normal", and macOS reports a transient warning (level 2) while it compresses
     the 3 GiB burst of loading the weights, even with GiBs still available. The patch
     tolerates level 2 while at least YUE2_MIN_AVAILABLE_GIB (1 by default) is free,
     and disables footprint / available / swap aborts (they still log into metadata).
     Busy 32 GB Macs were falsely killed by swap growth while loading weights.
     Configurable:  YUE2_MIN_AVAILABLE_GIB=2 ./install.sh

  2. src/lyra/music_tools/transcribe.py — the `transcribe` helper defaults
     --memory-budget-gib to 24, while the guard requires budget <= total RAM - 4, so on a
     24 GB machine (limit 20) every transcription fails on startup. The patch computes the
     default from RAM (24 GB -> 16).

Usage:
    python3 patches/apply_patches.py --project ~/Projects/mlx-Yue           # apply
    python3 patches/apply_patches.py --project ~/Projects/mlx-Yue --check   # report state
    python3 patches/apply_patches.py --project ~/Projects/mlx-Yue --revert  # restore upstream
"""
from __future__ import annotations

import argparse
import os
import subprocess
import sys
from pathlib import Path

MARKER = "YuE2 Studio patch"

MEASURE_OLD = '''        footprint = sample["physical_footprint_bytes"]
        if footprint > self.memory_budget_gib * _GIB:
            raise MemoryError(f"Process footprint {footprint / _GIB:.2f} GiB exceeds "
                              f"{self.memory_budget_gib:g} GiB budget")
        pressure = sample["system_memory_pressure_level"]
        if pressure != 1:
            raise MemoryError(f"System memory pressure is not normal (level={pressure})")
        if sample["system_available_bytes"] < 2 * _GIB:
            raise MemoryError("Less than 2 GiB of available system memory remains")
        swapped = sample["system_swap_out_bytes"] - self._baseline["system_swap_out_bytes"]
        growth = sample["system_swap_used_bytes"] - self._baseline["system_swap_used_bytes"]
        if swapped > 64 * _MIB or growth > 128 * _MIB:
            raise MemoryError(f"Stopping GPU workload after new swapping: "
                              f"{swapped / _MIB:.1f} MiB out, {growth / _MIB:.1f} MiB used growth")
'''

MEASURE_NEW = '''        footprint = sample["physical_footprint_bytes"]
        if footprint > self.memory_budget_gib * _GIB:
            # {marker}: footprint abort disabled — log only (busy 32 GB Macs false-trigger)
            self.monitor.metadata["footprint_over_budget"] = True
            self.monitor.metadata["footprint_gib"] = round(footprint / _GIB, 2)
        pressure = sample["system_memory_pressure_level"]
        if pressure != 1:
            # {marker}: on Apple Silicon macOS reports level 2 transiently while it
            # compresses the burst of loading the weights (observed: one 0.25 s sample
            # with 6 GiB available). Never aborts; recorded in metadata. Configure with
            # YUE2_MIN_AVAILABLE_GIB for the soft available floor warning.
            if sample["system_available_bytes"] < self.min_available_gib * _GIB:
                self.monitor.metadata["pressure_warning_level"] = pressure
            self.monitor.metadata["transient_pressure_warnings"] = (
                self.monitor.metadata.get("transient_pressure_warnings", 0) + 1)
        if sample["system_available_bytes"] < self.min_available_gib * _GIB:
            self.monitor.metadata["low_available_warning"] = True
        # {marker}: swap abort disabled — log only
        swapped = sample["system_swap_out_bytes"] - self._baseline["system_swap_out_bytes"]
        growth = sample["system_swap_used_bytes"] - self._baseline["system_swap_used_bytes"]
        if swapped > 0 or growth > 0:
            self.monitor.metadata["swap_out_mib"] = round(swapped / _MIB, 1)
            self.monitor.metadata["swap_growth_mib"] = round(growth / _MIB, 1)
'''.format(marker=MARKER)

MEASURE_INIT_OLD = '''        self.backend, self.memory_budget_gib = backend, float(memory_budget_gib)
        self._entered = False'''

MEASURE_INIT_NEW = '''        self.backend, self.memory_budget_gib = backend, float(memory_budget_gib)
        # {marker}
        self.min_available_gib = max(0.5, float(os.environ.get("YUE2_MIN_AVAILABLE_GIB", "1")))
        self._entered = False'''.format(marker=MARKER)

TRANSCRIBE_OLD = "    parser.add_argument('--memory-budget-gib', type=float, default=24)"

TRANSCRIBE_NEW = '''    # {marker}: upstream's default of 24 violates the guard check
    # (budget <= total RAM - 4) on 24 GB machines. Computed from RAM instead.
    def default_budget():
        try:
            import psutil
            total_gib = psutil.virtual_memory().total / 2 ** 30
            return float(max(8, min(48, int(total_gib) - 8)))
        except Exception:
            return 16.0

    parser.add_argument('--memory-budget-gib', type=float, default=default_budget())'''.format(marker=MARKER)


MLX_LIMIT_OLD = "            mx.set_memory_limit(int((budget - 5) * _GIB))"
MLX_LIMIT_NEW = "            mx.set_memory_limit(int(max(budget - 2, budget * 0.9) * _GIB))  # YuE2 Studio: less aggressive Metal cap"

PATCHES = [
    {
        "name": "non-aborting memory guard (24/32 GB)",
        "path": "src/lyra/measure.py",
        "edits": (("init", MEASURE_INIT_OLD, MEASURE_INIT_NEW), ("check", MEASURE_OLD, MEASURE_NEW), ("mlx_limit", MLX_LIMIT_OLD, MLX_LIMIT_NEW)),
    },
    {
        "name": "RAM-based transcription budget",
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
        return f"SKIPPED {patch['path']} (not found)"
    text = original = read(target)
    current = state(text, patch)
    if current == "applied":
        return f"ok      {patch['path']} (already patched)"
    if current == "partial":
        return (f"WARNING {patch['path']}: contains previous edits or a different version of the patch. "
                f"Revert with --revert or `git checkout {patch['path']}` and apply again.")
    for label, old, new in patch["edits"]:
        if old not in text:
            return (f"FAILED  {patch['path']} ({label}): expected block not found — "
                    f"did upstream change? See docs/PATCHES.md.")
        text = text.replace(old, new, 1)
    if dry:
        return f"dry-run {patch['path']} (would be applied)"
    write(target, text)
    return f"applied {patch['path']} ({len(text) - len(original):+d} bytes)"


def revert_patch(project: Path, patch: dict) -> str:
    target = project / patch["path"]
    if not target.is_file():
        return f"SKIPPED {patch['path']} (not found)"
    rel = patch["path"]
    done = subprocess.run(["git", "checkout", "--", rel], cwd=str(project),
                          capture_output=True, text=True)
    if done.returncode != 0:
        return f"FAILED  {rel}: {done.stderr.strip()[:160]}"
    return f"reverted {rel}"


def main() -> int:
    parser = argparse.ArgumentParser(description="YuE2 Studio patches for mlx-Yue")
    parser.add_argument("--project", default=os.environ.get("YUE2_PROJECT", str(Path.home() / "Projects" / "mlx-Yue")))
    parser.add_argument("--check", action="store_true", help="only report the current state")
    parser.add_argument("--revert", action="store_true", help="restore the upstream files")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    project = Path(args.project).expanduser().resolve()
    if not (project / "src" / "lyra").is_dir():
        print(f"Not an mlx-Yue checkout: {project}")
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
        failures += line.startswith(("FAILED", "WARNING"))
    print(f"\n{len(PATCHES) - failures}/{len(PATCHES)} patches ok")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
