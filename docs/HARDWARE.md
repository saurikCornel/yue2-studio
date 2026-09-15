# Hardware and performance

## Minimums

| | |
|---|---|
| Chip | Apple Silicon (M1–M5). The runtime rejects Intel/Rosetta explicitly |
| macOS | 14.2+ on M1–M4 · **26.2+ on M5** (MLX uses newer Metal paths) |
| Unified memory | **24 GB minimum**; 32 GB+ comfortable. Upstream tested on M5 Air 32 GB and M3 Max 128 GB |
| Disk | ~14 GB: 11 GB of weights plus the virtualenv, and 2.6 GB more for transcription |
| Python | 3.12 (provisioned by `uv`; do not touch the system Python) |
| Tools | `uv`, `ffmpeg`, and Xcode/Command Line Tools for the native app |

## Why 24 GB is the edge

A generation peaks at roughly 10–12 GiB (AR weights + NAR weights + VAE + activations), and
macOS needs the rest. On a 24 GB machine that leaves a thin margin: the system compresses,
reports transient pressure and — without the patch — the port's guard kills the run. With the
patch it completes, but the slack is still small: keep the charger connected and close
Chrome/Electron/Safari during long batches.

Real peak numbers, measured with the guard active:

| Job | Process peak | MLX peak | New swap |
|---|---|---|---|
| 16 s clip (32 steps) | ~7 GiB | ~6.8 GiB | 0 |
| 3:20 song (32 steps) | 10.40 GiB | 9.93 GiB | 0 |
| 1:16 song (8 steps) | ~9 GiB | ~8.6 GiB | 0 |

Guard budget: 16 GiB (`--memory-budget-gib`), MLX advisory limit 11 GiB, MLX cache limit
128 MiB. The GPU's recommended working set on a 24 GB M5 Pro is 17.76 GiB, so the measured
peak fits with about 7 GiB to spare.

## Measured timings (MacBook Pro M5 Pro · 24 GB · macOS 27.0)

Settings: `--precision 8bit`, `--vae-core-frames 128`, `MLX_ENABLE_TF32=0`.

| Job | Audio | Compute | RTF |
|---|---|---|---|
| Quickstart clip, 32 steps | 16 s | 13.2 s | 0.83 |
| Full song, 32 steps | 200.7 s | 336.8 s | 1.68 |
| Full song, 8 steps | 76.0 s | 47.1 s | 0.62 |
| Transcription (SheetSage2 + MERT2), 16 s source | — | 5.7 s | — |
| Cover from a 16 s source (transcribe + generate) | 16.5 s | 24.4 s | — |

Breakdown of a 3:20 song: symbolic planning (ABC) takes seconds, semantic token generation
(AR) is the long stretch in tokens, acoustic synthesis (NAR, 32 midpoint steps = 64 velocity
evaluations) takes 253.6 s, and the VAE decode 7.8 s. Loading weights and verifying integrity
adds about 4 s.

**Choosing steps.** 8 steps is fast and good for auditioning ideas (RTF below 1 on an M3 Max
and about 0.62 here). 32 steps is standard, the quality the benchmarks report. 16 is the
middle ground.

## Other chips

MLX scales with GPU cores, so M5 Pro/Max and M4 Pro/Max run faster than a base M1. Memory does
not scale: on a 16 GB M1/M2 this does **not** run — the ~10 GiB peak cannot fit alongside
macOS, and the guard will stop it. 24 GB is workable with the patches; 32 GB or more lets you
use upstream untouched.

## Power notes

- The CLI has `--require-ac` for benchmarks: it refuses to start unless plugged in. The app
  does not use it, but it shows the power state in Settings and in the sidebar footer.
- Running on battery works (the timings above are from a plugged-in batch; on battery the
  performance drops because of thermal and power limits). Long batches: use the charger.
- One GPU job at a time: the runtime takes a `flock` on `/tmp/lyra-gpu-<uid>.lock`. A second
  job fails with "Another Lyra process owns the GPU".
