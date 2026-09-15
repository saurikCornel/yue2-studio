# Parches para `mlx-Yue`

Dos cambios, los dos necesarios para que una Mac de **24 GB** pueda terminar una canción y
transcribir audio. Se aplican con `patches/apply_patches.py`, que es idempotente y
reversible, y están también como diff en `patches/yue2-studio.patch` por si preferís
`git apply`.

```bash
python3 patches/apply_patches.py --project ~/Projects/mlx-Yue          # aplicar
python3 patches/apply_patches.py --project ~/Projects/mlx-Yue --check   # ver estado
python3 patches/apply_patches.py --project ~/Projects/mlx-Yue --revert  # volver atrás
```

Si tenés 32 GB o más no los necesitás: upstream sin tocar funciona.

---

## 1. Guard de memoria tolerante — `src/lyra/measure.py`

**Qué pasa sin el parche.** El guard del port aborta ante cualquier lectura de presión de
memoria distinta de "normal":

```python
if pressure != 1:
    raise MemoryError(f"System memory pressure is not normal (level={pressure})")
if sample["system_available_bytes"] < 2 * _GIB:
    raise MemoryError("Less than 2 GiB of available system memory remains")
```

En Apple Silicon macOS marca **nivel 2 de forma transitoria** cuando comprime el golpe de
3 GiB que significa cargar los pesos del NAR. Medición real del fallo, con 6 GiB todavía
disponibles:

```
t=9.16s  footprint 4.99 GiB  available 6.00 GiB  free 69 MB  compresor 8.14 GiB  pressure=1
t=9.42s  footprint 6.04 GiB  available 6.00 GiB  free 69 MB  compresor 8.14 GiB  pressure=2  -> abort
t=9.81s  footprint 0.21 GiB  available 6.00 GiB  free 69 MB  compresor 8.14 GiB  pressure=1
```

Un solo sample de 0.25 s, con el proceso usando 6 de los 16 GiB de presupuesto, mata la
generación. En las máquinas que upstream probó (M5 Air 32 GB, M3 Max 128 GB) el aviso no
aparece porque hay más colchón.

**Qué cambia.** Se tolera el nivel 2 mientras haya al menos `min_available_gib` libres
(1 GiB por defecto, configurable con la variable de entorno `YUE2_MIN_AVAILABLE_GIB`), y se
cuenta cada aviso tolerado en el reporte de recursos, en
`metadata.transient_pressure_warnings`. El piso de memoria disponible también pasa de 2 GiB
a ese mismo valor.

**Qué NO cambia.** Siguen estrictos: footprint del proceso > presupuesto (16 GiB por
defecto), crecimiento de swap (>64 MiB out o >128 MiB used) y el lock de GPU por proceso.

**Medición con el parche** (canción de 200.7 s, `--precision 8bit`, 32 pasos): 2 samples con
nivel 2 sobre 1344, mínimo disponible 4.64 GiB, **0 bytes de swap**, pico de footprint
10.40 GiB.

## 2. Presupuesto de transcripción según RAM — `src/lyra/music_tools/transcribe.py`

**Qué pasa sin el parche.** El helper `transcribe` trae su propio default:

```python
parser.add_argument('--memory-budget-gib', type=float, default=24)
```

El guard valida `budget <= RAM total − 4`, así que en una Mac de 24 GB el límite es 20 y
**toda** transcripción muere al arrancar, antes de cargar nada:

```
ValueError: Memory budget must exceed 5 GiB and leave 4 GiB OS headroom
```

**Qué cambia.** El default se calcula desde la RAM (`int(GB) − 8`, entre 8 y 48): 16 en una
máquina de 24 GB, 24 en una de 32, 48 en una de 128. Sigue siendo un parámetro explícito:
podés pasar `--memory-budget-gib 12` si querés apretar más.

---

## Revertir

```bash
python3 patches/apply_patches.py --project ~/Projects/mlx-Yue --revert
# o bien:
git -C ~/Projects/mlx-Yue checkout -- src/lyra/measure.py src/lyra/music_tools/transcribe.py
```

## Si upstream cambia el código

El aplicador busca los bloques exactos y falla con un mensaje claro si no los encuentra
(`ATENCION`/`FALLO`), sin dejar los archivos a medio editar. En ese caso: mirá el diff de
`patches/yue2-studio.patch`, portá el cambio a mano y actualizá este documento.

## Cómo reportarlo upstream

Los dos problemas son de upstream y afectan a cualquier Mac con menos de ~32 GB:

- guard: `vanch007/mlx-Yue` → `src/lyra/measure.py`, `GPUExecution._check_sample`.
- presupuesto: `vanch007/mlx-Yue` → `src/lyra/music_tools/transcribe.py`.

Un reporte útil lleva el chip, la RAM, la versión de macOS, el comando exacto y el archivo
`outputs/<job>.resources.json` del run fallido — ahí están todos los samples con presión,
footprint, memoria disponible y swap.
