# Patches for `mlx-Yue`

Two changes, both required before a **24 GB** Mac can finish a song or transcribe audio.
They are applied by `patches/apply_patches.py`, which is idempotent and reversible, and they
are also shipped as a plain diff in `patches/yue2-studio.patch` for `git apply`.

```bash
python3 patches/apply_patches.py --project ~/Projects/mlx-Yue          # apply
python3 patches/apply_patches.py --project ~/Projects/mlx-Yue --check   # report state
python3 patches/apply_patches.py --project ~/Projects/mlx-Yue --revert  # restore upstream
```

With 32 GB or more you do not need them: upstream works untouched.

---

## 1. Tolerant memory guard — `src/lyra/measure.py`

**What happens without the patch.** The port's guard aborts on any memory-pressure reading
other than "normal":

```python
if pressure != 1:
    raise MemoryError(f"System memory pressure is not normal (level={pressure})")
if sample["system_available_bytes"] < 2 * _GIB:
    raise MemoryError("Less than 2 GiB of available system memory remains")
```

On Apple Silicon, macOS reports **level 2 transiently** while it compresses the 3 GiB burst
of loading the NAR weights. Measured on a real failure, with 6 GiB still available:

```
t=9.16s  footprint 4.99 GiB  available 6.00 GiB  free 69 MB  compressor 8.14 GiB  pressure=1
t=9.42s  footprint 6.04 GiB  available 6.00 GiB  free 69 MB  compressor 8.14 GiB  pressure=2  -> abort
t=9.81s  footprint 0.21 GiB  available 6.00 GiB  free 69 MB  compressor 8.14 GiB  pressure=1
```

A single 0.25 s sample, with the process using 6 of its 16 GiB budget, kills the run. On the
machines upstream tested (M5 Air 32 GB, M3 Max 128 GB) the warning does not appear because
there is more headroom.

**What changes.** Level 2 is tolerated as long as at least `min_available_gib` (1 GiB by
default, configurable through `YUE2_MIN_AVAILABLE_GIB`) remains available, and every
tolerated warning is counted in the resource report as
`metadata.transient_pressure_warnings`. The availability floor moves from 2 GiB to the same
value.

**What does not change.** Still strict: process footprint above the budget (16 GiB by
default), swap growth (>64 MiB out or >128 MiB used) and the one-GPU-job-per-process lock.

**Measured with the patch** (200.7 s song, `--precision 8bit`, 32 steps): 2 samples at level 2
out of 1344, minimum available 4.64 GiB, **0 bytes of swap**, peak footprint 10.40 GiB.

## 2. RAM-based transcription budget — `src/lyra/music_tools/transcribe.py`

**What happens without the patch.** The `transcribe` helper ships its own default:

```python
parser.add_argument('--memory-budget-gib', type=float, default=24)
```

The guard requires `budget <= total RAM − 4`, so on a 24 GB Mac the limit is 20 and **every**
transcription dies on startup, before loading anything:

```
ValueError: Memory budget must exceed 5 GiB and leave 4 GiB OS headroom
```

**What changes.** The default is computed from RAM (`int(GB) − 8`, clamped to 8–48): 16 on a
24 GB machine, 24 on a 32 GB one, 48 on a 128 GB one. It is still an explicit flag: pass
`--memory-budget-gib 12` if you want a tighter ceiling.

---

## Reverting

```bash
python3 patches/apply_patches.py --project ~/Projects/mlx-Yue --revert
# or:
git -C ~/Projects/mlx-Yue checkout -- src/lyra/measure.py src/lyra/music_tools/transcribe.py
```

## If upstream changes the code

The applier matches exact blocks and fails loudly (`ATENCION`/`FALLO` in the output) instead
of leaving files half-edited. In that case, look at the diff in
`patches/yue2-studio.patch`, port the change by hand and update this document.

## Reporting upstream

Both issues are upstream's and affect any Mac below roughly 32 GB:

- guard: `vanch007/mlx-Yue` → `src/lyra/measure.py`, `GPUExecution._check_sample`.
- budget: `vanch007/mlx-Yue` → `src/lyra/music_tools/transcribe.py`.

A useful report includes the chip, RAM, macOS version, the exact command and the
`outputs/<job>.resources.json` file from the failed run — it holds every sample with
pressure, footprint, available memory and swap.
