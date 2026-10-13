# Culling Engine (Proyecto 1) — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Motor local de selección de fotos de eventos que recibe una carpeta, analiza cada foto (nitidez, caras, ojos, exposición, duplicados) y escribe `Label` de color + `Rating` en XMP para revisar en Lightroom.

**Architecture:** Pipeline de funciones puras + finas envolturas de modelos. `loader` carga (JPEG directo / RAW vía preview embebido) y reescala a ≤2500px. Cada analizador (`sharpness`, `exposure`, `embedding`, `faces`, `eyes`) devuelve métricas sin estado. `grouping` agrupa ráfagas (tiempo + pHash). `decision` aplica reglas → color+estrellas. `xmp_writer` escribe sidecar (RAW) o metadatos embebidos (JPEG, solo metadatos, sin recomprimir). `cli` orquesta vía `typer`.

**Tech Stack:** Python 3.11 · OpenCV (YuNet) · MediaPipe (FaceMesh) · **onnxruntime + OCEC** (ojos cerrados) · rawpy · imagehash/Pillow · NumPy · PyYAML · typer · exiftool (binario externo, para embeber XMP en JPEG) · pytest + ruff.

**Spec:** `docs/superpowers/specs/2026-06-26-culling-engine-design.md`

---

## Desviaciones respecto al spec (decididas en planificación)

1. **JPEG: el XMP va embebido en el archivo (solo metadatos, lossless), no en sidecar.**
   Lightroom **no lee sidecars `.xmp` para JPEG** (solo para RAW). Para que las etiquetas
   aparezcan en Lightroom, en JPEG se escribe el XMP **dentro** del archivo con `exiftool`
   (`-overwrite_original`, sin recompresión). Esto matiza el límite "nunca tocar el original":
   se toca **solo la sección de metadatos**, nunca los píxeles. En RAW sí se usa sidecar.
2. **Agrupado secuencial en vez de DBSCAN.** Ráfaga = fotos consecutivas en el tiempo
   (`< burst_time_window_s`) y perceptualmente similares (`hamming(pHash) <= phash_max_distance`).
   Determinista y testeable; suficiente para ráfagas. DBSCAN/embeddings queda como mejora futura.
3. **Etiquetas de color en inglés** (`Green`/`Blue`/`Red`) — son los nombres que el set por
   defecto de Lightroom mapea a color. Configurable en el preset (`labels`).

## Revisión v2 — cambios obligatorios tras el spike (VisionCull Pro + Pianke)

> Estos puntos **sobrescriben** las tareas indicadas. Origen: lectura de
> `YuChiHuaCheng/vision-cull-pro` y `zhaoyue4810/pianke`. Modelo OCEC: `PINTO0309/OCEC` (MIT).

- **A. Ojos cerrados con OCEC ONNX (sobrescribe Task 8).** En vez de decidir por EAR, se usa
  el modelo dedicado **OCEC** (`prob_open`). Flujo: FaceMesh ubica los landmarks de cada ojo →
  se recorta cada ojo (con padding) → OCEC clasifica `open`/`closed`/`uncertain`. EAR se sigue
  calculando como señal de respaldo si OCEC no está disponible. `uncertain`/`closed` **solo
  penaliza el score** (no pinta color). Umbrales OCEC: open ≥0.58, closed ≤0.42.
- **B. Emparejado RAW+JPG por "unidades" (sobrescribe Task 9 y 13).** Antes de analizar, se
  agrupan los archivos del **mismo nombre base en la misma carpeta** en una *unidad*
  (`primary` + `companions`). Fuente de análisis: si un RAW tiene JPG hermano → se analiza el
  **JPG** (cero decodificación RAW); si no, el preview embebido del RAW. La decisión y el XMP
  se aplican a **toda la unidad** (sidecar para el RAW + embebido para el JPG).
- **C. Nitidez sobre el centro 60% (ajusta Task 4).** `global_sharpness` calcula el Laplaciano
  sobre el recorte central (60% ancho × 60% alto), más justo con fondos desenfocados/bokeh.
  La nitidez por cara sigue usando la caja de la cara.
- **D. Exposición con ratios + estado (ajusta Task 5).** Además del score 0..1, `exposure`
  devuelve `status` (`normal`/`underexposed`/`overexposed`) usando media de luma + ratios de
  recorte. Defaults (de VCP/Pianke): sombras `<35` ≥0.35 ó luma media ≤70 → under; altas `>235`
  ≥0.25 ó luma media ≥188 → over.
- **E. Defaults de preset medidos (ajusta Task 3).** `ear_threshold: 0.22` (valor medido por
  Pianke; 0.18 no detectaba). OCEC thresholds en preset (`ocec_open: 0.58`, `ocec_closed: 0.42`).
- **F. Filosofía conservadora.** Lo `uncertain` nunca fuerza rechazo; el rojo se reserva a
  borrosa global y peor(es) de un grupo de duplicados (como ya define el spec del usuario).

### A.1 — `analysis/eyes.py` v2 (reemplaza el código de Task 8, Step 4)

```python
# photoselect/analysis/eyes.py
from __future__ import annotations
import math
from pathlib import Path
import cv2
import numpy as np
import mediapipe as mp

try:
    import onnxruntime as ort
except Exception:           # onnxruntime opcional; sin él, fallback a EAR
    ort = None

OCEC_MODEL = Path(__file__).resolve().parents[2] / "models" / "ocec_s.onnx"
_RIGHT_EYE = [33, 160, 158, 133, 153, 144]
_LEFT_EYE = [362, 385, 387, 263, 373, 380]
_MOUTH_CORNERS = (61, 291)
_MOUTH_VERT = (13, 14)

_mesh = mp.solutions.face_mesh.FaceMesh(
    static_image_mode=True, max_num_faces=1, refine_landmarks=True)
_ocec = ort.InferenceSession(str(OCEC_MODEL), providers=["CPUExecutionProvider"]) \
    if (ort is not None and OCEC_MODEL.exists()) else None


def _ear(pts: list[tuple[float, float]]) -> float:
    p1, p2, p3, p4, p5, p6 = pts
    return (math.dist(p2, p6) + math.dist(p3, p5)) / (2.0 * math.dist(p1, p4) + 1e-6)


def _eye_box(pts: list[tuple[float, float]], w: int, h: int) -> tuple[int, int, int, int]:
    xs = [p[0] for p in pts]; ys = [p[1] for p in pts]
    x1, x2, y1, y2 = min(xs), max(xs), min(ys), max(ys)
    px = max(4, int((x2 - x1) * 0.45)); py = max(4, int((y2 - y1) * 1.25))
    return (max(0, int(x1 - px)), max(0, int(y1 - py)),
            min(w, int(x2 + px)), min(h, int(y2 + py)))


def _prob_open(eye_crop: np.ndarray) -> float | None:
    if _ocec is None or eye_crop.size == 0:
        return None
    inp = _ocec.get_inputs()[0]
    ih, iw = (int(inp.shape[2]), int(inp.shape[3])) if len(inp.shape) == 4 else (24, 40)
    rgb = cv2.cvtColor(cv2.resize(eye_crop, (iw, ih)), cv2.COLOR_BGR2RGB).astype(np.float32) / 255.0
    tensor = np.transpose(rgb, (2, 0, 1))[None]
    out = _ocec.run(None, {inp.name: tensor})[0]
    return float(np.clip(np.ravel(out)[0], 0.0, 1.0))


def analyze_eyes(face_crop_bgr: np.ndarray,
                 ocec_open: float = 0.58, ocec_closed: float = 0.42) -> tuple[float, bool]:
    """Devuelve (eyes_open_score 0..1, is_smiling). 1.0 = ojos abiertos con certeza."""
    h, w = face_crop_bgr.shape[:2]
    res = _mesh.process(cv2.cvtColor(face_crop_bgr, cv2.COLOR_BGR2RGB))
    if not res.multi_face_landmarks:
        return 0.0, False
    lm = res.multi_face_landmarks[0].landmark

    def pt(i: int) -> tuple[float, float]:
        return (lm[i].x * w, lm[i].y * h)

    left = [pt(i) for i in _LEFT_EYE]; right = [pt(i) for i in _RIGHT_EYE]
    probs = []
    for eye_pts in (left, right):
        x1, y1, x2, y2 = _eye_box(eye_pts, w, h)
        p = _prob_open(face_crop_bgr[y1:y2, x1:x2])
        if p is not None:
            probs.append(p)
    if probs:                                   # OCEC disponible
        score = min(probs)                      # el ojo más cerrado manda
    else:                                        # fallback EAR -> 0..1
        ear = (_ear(left) + _ear(right)) / 2.0
        score = float(min(1.0, ear / 0.30))
    mouth_w = math.dist(pt(_MOUTH_CORNERS[0]), pt(_MOUTH_CORNERS[1]))
    mouth_h = math.dist(pt(_MOUTH_VERT[0]), pt(_MOUTH_VERT[1]))
    is_smiling = mouth_w > 0 and (mouth_h / mouth_w) > 0.35
    return float(score), bool(is_smiling)
```

> **`FaceMetrics.eye_aspect_ratio` pasa a representar `eyes_open_score` (0..1).** En `decision.py`
> la condición de "ojos abiertos" se vuelve `f.eye_aspect_ratio >= 0.5` (umbral de score, no EAR).
> El test de Task 8 se mantiene: abiertos > cerrados.

### B.1 — Emparejado de unidades en `loader.py` (añadir a Task 9)

```python
# añadir a photoselect/loader.py
from collections import defaultdict

def discover_units(folder: Path) -> list[tuple[Path, list[Path], Path]]:
    """Agrupa archivos por (stem en minúsculas) dentro de la carpeta.
    Devuelve [(primary, companions, analysis_source)].
    analysis_source = JPG hermano si el primary es RAW y existe; si no, el primary."""
    by_stem: dict[str, list[Path]] = defaultdict(list)
    for p in folder.iterdir():
        if p.suffix.lower() in (JPEG_EXTS | RAW_EXTS):
            by_stem[p.stem.lower()].append(p)
    units: list[tuple[Path, list[Path], Path]] = []
    for files in by_stem.values():
        files.sort(key=lambda p: 0 if p.suffix.lower() in RAW_EXTS else 1)
        primary = files[0]
        companions = files[1:]
        jpg = next((f for f in files if f.suffix.lower() in JPEG_EXTS), None)
        analysis_source = jpg if (is_raw(primary) and jpg is not None) else primary
        units.append((primary, companions, analysis_source))
    return sorted(units, key=lambda u: u[0].name)
```

> **Pipeline (Task 13):** `cull_folder` itera `discover_units` en vez de `iterdir`. Analiza
> `analysis_source`, asigna una `PhotoMetrics` a la unidad, y al escribir aplica
> `write_metadata` al `primary` **y a cada companion**.

## File Structure

```
Photo Selector/
  pyproject.toml                  → metadata, deps, ruff/pytest config
  .gitignore                      → models/, data/, __pycache__, *.egg-info
  models/                         → face_detection_yunet_2023mar.onnx (descargado, no versionado)
  presets/eventos-escolares.yaml  → preset de ejemplo
  photoselect/
    __init__.py
    types.py        → dataclasses: FaceMetrics, PhotoMetrics, Decision
    presets.py      → Preset + load_preset(yaml)
    loader.py       → carga imagen (JPEG/RAW preview), resize, timestamp EXIF
    analysis/
      __init__.py
      sharpness.py  → varianza Laplaciano global / por región
      exposure.py   → score de exposición por histograma
      embedding.py  → pHash + distancia de Hamming
      faces.py      → YuNet: detección de caras (cajas)
      eyes.py       → MediaPipe FaceMesh: EAR + sonrisa
    grouping.py     → group_bursts(photos) -> grupos de índices
    decision.py     → photo_score + decide() -> [Decision]
    xmp_writer.py   → build_xmp (puro) + write_metadata (sidecar/embebido)
    pipeline.py     → analyze_photo + cull_folder
    cli.py          → typer app: comando `cull`
  tests/
    conftest.py     → helpers para imágenes sintéticas
    fixtures/       → JPEGs pequeños: sharp.jpg, blurry.jpg, face_open.jpg, face_closed.jpg, burst_*.jpg
    test_*.py
```

---

### Task 1: Scaffold del proyecto

**Files:**
- Create: `Photo Selector/pyproject.toml`
- Create: `Photo Selector/.gitignore`
- Create: `Photo Selector/photoselect/__init__.py`
- Create: `Photo Selector/photoselect/analysis/__init__.py`
- Create: `Photo Selector/tests/__init__.py`

- [ ] **Step 1: Crear `pyproject.toml`**

```toml
[project]
name = "photoselect"
version = "0.1.0"
requires-python = ">=3.11"
dependencies = [
    "opencv-python>=4.8",
    "mediapipe>=0.10",
    "rawpy>=0.19",
    "imagehash>=4.3",
    "Pillow>=10",
    "numpy>=1.26,<2.0",
    "PyYAML>=6.0",
    "typer>=0.12",
]

[project.optional-dependencies]
dev = ["pytest>=8", "pytest-cov>=5", "ruff>=0.5"]

[project.scripts]
photoselect = "photoselect.cli:app"

[build-system]
requires = ["setuptools>=68"]
build-backend = "setuptools.build_meta"

[tool.pytest.ini_options]
testpaths = ["tests"]

[tool.ruff]
line-length = 100
target-version = "py311"
```

- [ ] **Step 2: Crear `.gitignore`**

```gitignore
__pycache__/
*.egg-info/
.pytest_cache/
.coverage
models/
data/
*.csv
```

- [ ] **Step 3: Crear paquetes vacíos**

`photoselect/__init__.py`, `photoselect/analysis/__init__.py`, `tests/__init__.py` → archivos vacíos.

- [ ] **Step 4: Instalar en editable**

Run: `cd "Photo Selector" && pip install -e ".[dev]"`
Expected: instala sin errores.

- [ ] **Step 5: Verificar herramientas**

Run: `cd "Photo Selector" && pytest -q && ruff check .`
Expected: pytest dice "no tests ran" (exit 0 o 5); ruff sin errores.

- [ ] **Step 6: Commit**

```bash
git add "Photo Selector/pyproject.toml" "Photo Selector/.gitignore" "Photo Selector/photoselect" "Photo Selector/tests"
git commit -m "chore(photo-selector): scaffold python package + tooling"
```

---

### Task 2: Tipos de datos (`types.py`)

**Files:**
- Create: `Photo Selector/photoselect/types.py`
- Test: `Photo Selector/tests/test_types.py`

- [ ] **Step 1: Escribir el test que falla**

```python
# tests/test_types.py
from pathlib import Path
from photoselect.types import FaceMetrics, PhotoMetrics, Decision

def test_photo_metrics_has_faces():
    f = FaceMetrics(box=(0, 0, 10, 10), eye_aspect_ratio=0.3, eye_sharpness=120.0, is_smiling=True)
    p = PhotoMetrics(path=Path("a.jpg"), timestamp=1.0, sharpness_global=200.0,
                     exposure_score=0.9, phash=123, faces=[f])
    assert p.has_faces is True
    assert PhotoMetrics(Path("b.jpg"), 1.0, 200.0, 0.9, 123).has_faces is False

def test_decision_fields():
    d = Decision(path=Path("a.jpg"), label="Green", rating=3)
    assert d.label == "Green" and d.rating == 3
```

- [ ] **Step 2: Ejecutar y ver que falla**

Run: `cd "Photo Selector" && pytest tests/test_types.py -v`
Expected: FAIL — `ModuleNotFoundError: photoselect.types`.

- [ ] **Step 3: Implementar `types.py`**

```python
# photoselect/types.py
from __future__ import annotations
from dataclasses import dataclass, field
from pathlib import Path

@dataclass(frozen=True)
class FaceMetrics:
    box: tuple[int, int, int, int]   # x, y, w, h
    eye_aspect_ratio: float          # EAR; alto = ojos abiertos
    eye_sharpness: float             # varianza Laplaciano sobre la cara
    is_smiling: bool

@dataclass
class PhotoMetrics:
    path: Path
    timestamp: float                 # epoch segundos (EXIF o mtime)
    sharpness_global: float
    exposure_score: float            # 0..1 (1 = bien expuesta)
    phash: int                       # hash perceptual de 64 bits
    faces: list[FaceMetrics] = field(default_factory=list)

    @property
    def has_faces(self) -> bool:
        return len(self.faces) > 0

@dataclass(frozen=True)
class Decision:
    path: Path
    label: str | None                # "Green" | "Blue" | "Red" | None
    rating: int                      # estrellas 0..5
```

- [ ] **Step 4: Ejecutar y ver que pasa**

Run: `cd "Photo Selector" && pytest tests/test_types.py -v`
Expected: PASS (2 tests).

- [ ] **Step 5: Commit**

```bash
git add "Photo Selector/photoselect/types.py" "Photo Selector/tests/test_types.py"
git commit -m "feat(photo-selector): core dataclasses (FaceMetrics, PhotoMetrics, Decision)"
```

---

### Task 3: Presets (`presets.py`)

**Files:**
- Create: `Photo Selector/photoselect/presets.py`
- Create: `Photo Selector/presets/eventos-escolares.yaml`
- Test: `Photo Selector/tests/test_presets.py`

- [ ] **Step 1: Escribir el test que falla**

```python
# tests/test_presets.py
from pathlib import Path
from photoselect.presets import Preset, load_preset

def test_default_preset_blur_threshold():
    p = Preset()
    assert p.blur == "moderado"
    assert p.blur_threshold == 100.0

def test_load_preset_overrides(tmp_path: Path):
    yaml_file = tmp_path / "p.yaml"
    yaml_file.write_text("blur: estricto\nstars_keeper: 4\n", encoding="utf-8")
    p = load_preset(yaml_file)
    assert p.blur == "estricto"
    assert p.blur_threshold == 150.0
    assert p.stars_keeper == 4

def test_load_preset_none_returns_default():
    assert load_preset(None).blur == "moderado"
```

- [ ] **Step 2: Ejecutar y ver que falla**

Run: `cd "Photo Selector" && pytest tests/test_presets.py -v`
Expected: FAIL — `ModuleNotFoundError: photoselect.presets`.

- [ ] **Step 3: Implementar `presets.py`**

```python
# photoselect/presets.py
from __future__ import annotations
from dataclasses import dataclass, field
from pathlib import Path
import yaml

BLUR_THRESHOLDS = {"indulgente": 50.0, "moderado": 100.0, "estricto": 150.0}

@dataclass(frozen=True)
class Preset:
    blur: str = "moderado"               # indulgente | moderado | estricto
    eyes_closed: str = "score_only"      # solo penaliza ranking
    duplicates: str = "stack"            # informativo; agrupado siempre activo
    stars_keeper: int = 3
    keep_detail_shots: bool = True
    ear_threshold: float = 0.5           # umbral sobre eyes_open_score (0..1); ver Revisión v2.A
    ocec_open: float = 0.58              # OCEC: prob_open >= -> abierto
    ocec_closed: float = 0.42           # OCEC: prob_open <= -> cerrado
    burst_time_window_s: float = 3.0
    phash_max_distance: int = 8
    keeper_threshold: float = 0.5
    highlight_threshold: float = 0.75
    sharp_ref: float = 300.0             # normaliza nitidez a 0..1
    labels: dict[str, str] = field(
        default_factory=lambda: {"keeper": "Green", "highlight": "Blue", "reject": "Red"})
    weights: dict[str, float] = field(
        default_factory=lambda: {"eye_sharp": 0.3, "sharp": 0.2, "expo": 0.2,
                                 "eyes_open": 0.2, "smile": 0.1})

    @property
    def blur_threshold(self) -> float:
        return BLUR_THRESHOLDS[self.blur]

def load_preset(path: Path | None) -> Preset:
    if path is None:
        return Preset()
    data = yaml.safe_load(Path(path).read_text(encoding="utf-8")) or {}
    return Preset(**data)
```

- [ ] **Step 4: Crear el preset de ejemplo**

```yaml
# presets/eventos-escolares.yaml
blur: moderado
eyes_closed: score_only
duplicates: stack
stars_keeper: 3
keep_detail_shots: true
```

- [ ] **Step 5: Ejecutar y ver que pasa**

Run: `cd "Photo Selector" && pytest tests/test_presets.py -v`
Expected: PASS (3 tests).

- [ ] **Step 6: Commit**

```bash
git add "Photo Selector/photoselect/presets.py" "Photo Selector/presets" "Photo Selector/tests/test_presets.py"
git commit -m "feat(photo-selector): preset config + YAML loader"
```

---

### Task 4: Nitidez (`analysis/sharpness.py`)

**Files:**
- Create: `Photo Selector/photoselect/analysis/sharpness.py`
- Test: `Photo Selector/tests/test_sharpness.py`

- [ ] **Step 1: Escribir el test que falla**

```python
# tests/test_sharpness.py
import numpy as np
import cv2
from photoselect.analysis import sharpness

def _checker(size=200, blur=0):
    img = np.zeros((size, size, 3), np.uint8)
    img[::2] = 255  # rayas de alto contraste = mucha textura
    if blur:
        img = cv2.GaussianBlur(img, (0, 0), blur)
    return img

def test_blurry_has_lower_sharpness_than_sharp():
    sharp = sharpness.global_sharpness(_checker(blur=0))
    blurry = sharpness.global_sharpness(_checker(blur=5))
    assert sharp > blurry

def test_region_sharpness_uses_box():
    img = _checker(blur=0)
    val = sharpness.region_sharpness(img, (10, 10, 50, 50))
    assert val > 0.0

def test_region_sharpness_empty_box_returns_zero():
    img = _checker()
    assert sharpness.region_sharpness(img, (0, 0, 0, 0)) == 0.0
```

- [ ] **Step 2: Ejecutar y ver que falla**

Run: `cd "Photo Selector" && pytest tests/test_sharpness.py -v`
Expected: FAIL — módulo inexistente.

- [ ] **Step 3: Implementar `sharpness.py`**

```python
# photoselect/analysis/sharpness.py
from __future__ import annotations
import cv2
import numpy as np

def laplacian_variance(gray: np.ndarray) -> float:
    return float(cv2.Laplacian(gray, cv2.CV_64F).var())

def global_sharpness(image_bgr: np.ndarray) -> float:
    gray = cv2.cvtColor(image_bgr, cv2.COLOR_BGR2GRAY)
    return laplacian_variance(gray)

def region_sharpness(image_bgr: np.ndarray, box: tuple[int, int, int, int]) -> float:
    x, y, w, h = box
    crop = image_bgr[max(0, y):y + h, max(0, x):x + w]
    if crop.size == 0:
        return 0.0
    gray = cv2.cvtColor(crop, cv2.COLOR_BGR2GRAY)
    return laplacian_variance(gray)
```

- [ ] **Step 4: Ejecutar y ver que pasa**

Run: `cd "Photo Selector" && pytest tests/test_sharpness.py -v`
Expected: PASS (3 tests).

- [ ] **Step 5: Commit**

```bash
git add "Photo Selector/photoselect/analysis/sharpness.py" "Photo Selector/tests/test_sharpness.py"
git commit -m "feat(photo-selector): sharpness (Laplacian variance) global + region"
```

---

### Task 5: Exposición (`analysis/exposure.py`)

**Files:**
- Create: `Photo Selector/photoselect/analysis/exposure.py`
- Test: `Photo Selector/tests/test_exposure.py`

- [ ] **Step 1: Escribir el test que falla**

```python
# tests/test_exposure.py
import numpy as np
from photoselect.analysis import exposure

def _solid(value):
    return np.full((100, 100, 3), value, np.uint8)

def _midgray_gradient():
    row = np.linspace(40, 215, 100, dtype=np.uint8)
    return np.repeat(row[None, :], 100, axis=0)[:, :, None].repeat(3, axis=2)

def test_well_exposed_scores_high():
    assert exposure.exposure_score(_midgray_gradient()) > 0.8

def test_blown_out_scores_low():
    assert exposure.exposure_score(_solid(255)) < 0.2

def test_crushed_blacks_score_low():
    assert exposure.exposure_score(_solid(0)) < 0.2

def test_score_in_unit_range():
    s = exposure.exposure_score(_solid(128))
    assert 0.0 <= s <= 1.0
```

- [ ] **Step 2: Ejecutar y ver que falla**

Run: `cd "Photo Selector" && pytest tests/test_exposure.py -v`
Expected: FAIL — módulo inexistente.

- [ ] **Step 3: Implementar `exposure.py`**

```python
# photoselect/analysis/exposure.py
from __future__ import annotations
import cv2
import numpy as np

def exposure_score(image_bgr: np.ndarray) -> float:
    """1.0 = bien expuesta; baja con pixeles quemados (>=250) o aplastados (<=5)."""
    gray = cv2.cvtColor(image_bgr, cv2.COLOR_BGR2GRAY)
    hist = cv2.calcHist([gray], [0], None, [256], [0, 256]).flatten()
    total = float(gray.size)
    clipped_high = hist[250:].sum() / total
    clipped_low = hist[:6].sum() / total
    penalty = (clipped_high + clipped_low) * 3.0
    return float(max(0.0, min(1.0, 1.0 - penalty)))
```

- [ ] **Step 4: Ejecutar y ver que pasa**

Run: `cd "Photo Selector" && pytest tests/test_exposure.py -v`
Expected: PASS (4 tests).

- [ ] **Step 5: Commit**

```bash
git add "Photo Selector/photoselect/analysis/exposure.py" "Photo Selector/tests/test_exposure.py"
git commit -m "feat(photo-selector): exposure score from histogram clipping"
```

---

### Task 6: Hash perceptual (`analysis/embedding.py`)

**Files:**
- Create: `Photo Selector/photoselect/analysis/embedding.py`
- Test: `Photo Selector/tests/test_embedding.py`

- [ ] **Step 1: Escribir el test que falla**

```python
# tests/test_embedding.py
import numpy as np
from photoselect.analysis import embedding

def _img(seed):
    rng = np.random.default_rng(seed)
    return rng.integers(0, 256, (128, 128, 3), dtype=np.uint8)

def test_identical_images_have_zero_distance():
    img = _img(1)
    assert embedding.hamming(embedding.phash(img), embedding.phash(img.copy())) == 0

def test_different_images_have_large_distance():
    d = embedding.hamming(embedding.phash(_img(1)), embedding.phash(_img(99)))
    assert d > 8

def test_hamming_basic():
    assert embedding.hamming(0b1010, 0b0011) == 2
```

- [ ] **Step 2: Ejecutar y ver que falla**

Run: `cd "Photo Selector" && pytest tests/test_embedding.py -v`
Expected: FAIL — módulo inexistente.

- [ ] **Step 3: Implementar `embedding.py`**

```python
# photoselect/analysis/embedding.py
from __future__ import annotations
import imagehash
import numpy as np
from PIL import Image

def phash(image_bgr: np.ndarray) -> int:
    rgb = image_bgr[:, :, ::-1]                 # BGR -> RGB
    h = imagehash.phash(Image.fromarray(rgb))
    return int(str(h), 16)

def hamming(a: int, b: int) -> int:
    return bin(a ^ b).count("1")
```

- [ ] **Step 4: Ejecutar y ver que pasa**

Run: `cd "Photo Selector" && pytest tests/test_embedding.py -v`
Expected: PASS (3 tests).

- [ ] **Step 5: Commit**

```bash
git add "Photo Selector/photoselect/analysis/embedding.py" "Photo Selector/tests/test_embedding.py"
git commit -m "feat(photo-selector): perceptual hash (pHash) + hamming distance"
```

---

### Task 7: Detección de caras (`analysis/faces.py`)

**Files:**
- Create: `Photo Selector/photoselect/analysis/faces.py`
- Create: `Photo Selector/tests/fixtures/face_open.jpg` (foto pequeña con 1 rostro frontal claro)
- Create: `Photo Selector/tests/fixtures/no_face.jpg` (foto de objeto/paisaje, sin caras)
- Test: `Photo Selector/tests/test_faces.py`

> **Nota:** se necesita el modelo YuNet. Step 1 lo descarga a `models/`. Las fixtures son
> JPEGs reales pequeños (≤800px); añádelos al repo (son livianos).

- [ ] **Step 1: Descargar el modelo YuNet**

Run (PowerShell):
```powershell
cd "Photo Selector"; New-Item -ItemType Directory -Force models | Out-Null; Invoke-WebRequest -Uri "https://github.com/opencv/opencv_zoo/raw/main/models/face_detection_yunet/face_detection_yunet_2023mar.onnx" -OutFile "models/face_detection_yunet_2023mar.onnx"
```
Expected: archivo `models/face_detection_yunet_2023mar.onnx` (~230 KB). (No se versiona — está en `.gitignore`.)

> **También descarga el modelo OCEC** (ojos cerrados, usado en Task 8 v2). Fuente:
> rama `onnx` de [PINTO0309/OCEC](https://github.com/PINTO0309/OCEC/tree/onnx) (MIT) o el
> archivo en Zenodo. Guarda el `.onnx` como `models/ocec_s.onnx`. Si no se descarga, `eyes.py`
> hace fallback a EAR automáticamente (los tests siguen pasando).

- [ ] **Step 2: Añadir las fixtures**

Copia dos JPEGs pequeños a `tests/fixtures/`: `face_open.jpg` (un rostro frontal nítido) y
`no_face.jpg` (sin personas). Verifica: `ls "Photo Selector/tests/fixtures"`.

- [ ] **Step 3: Escribir el test que falla**

```python
# tests/test_faces.py
from pathlib import Path
import cv2
import pytest
from photoselect.analysis import faces

FIX = Path(__file__).parent / "fixtures"

@pytest.mark.skipif(not faces.MODEL_PATH.exists(), reason="modelo YuNet no descargado")
def test_detects_face_in_portrait():
    img = cv2.imread(str(FIX / "face_open.jpg"))
    boxes = faces.detect_faces(img)
    assert len(boxes) >= 1
    x, y, w, h = boxes[0]
    assert w > 0 and h > 0

@pytest.mark.skipif(not faces.MODEL_PATH.exists(), reason="modelo YuNet no descargado")
def test_no_face_in_landscape():
    img = cv2.imread(str(FIX / "no_face.jpg"))
    assert faces.detect_faces(img) == []
```

- [ ] **Step 4: Ejecutar y ver que falla**

Run: `cd "Photo Selector" && pytest tests/test_faces.py -v`
Expected: FAIL — `ModuleNotFoundError: photoselect.analysis.faces`.

- [ ] **Step 5: Implementar `faces.py`**

```python
# photoselect/analysis/faces.py
from __future__ import annotations
from pathlib import Path
import cv2
import numpy as np

MODEL_PATH = Path(__file__).resolve().parents[2] / "models" / "face_detection_yunet_2023mar.onnx"

def detect_faces(image_bgr: np.ndarray, score_threshold: float = 0.6) -> list[tuple[int, int, int, int]]:
    """Devuelve cajas (x, y, w, h) de las caras detectadas."""
    h, w = image_bgr.shape[:2]
    detector = cv2.FaceDetectorYN.create(str(MODEL_PATH), "", (w, h), score_threshold)
    _, faces = detector.detect(image_bgr)
    if faces is None:
        return []
    boxes: list[tuple[int, int, int, int]] = []
    for f in faces:
        x, y, fw, fh = f[:4].astype(int)
        boxes.append((int(x), int(y), int(fw), int(fh)))
    return boxes
```

- [ ] **Step 6: Ejecutar y ver que pasa**

Run: `cd "Photo Selector" && pytest tests/test_faces.py -v`
Expected: PASS (2 tests). Si el modelo no está, los tests se SKIPpean (no fallan).

- [ ] **Step 7: Commit**

```bash
git add "Photo Selector/photoselect/analysis/faces.py" "Photo Selector/tests/test_faces.py" "Photo Selector/tests/fixtures/face_open.jpg" "Photo Selector/tests/fixtures/no_face.jpg"
git commit -m "feat(photo-selector): YuNet face detection wrapper"
```

---

### Task 8: Ojos y sonrisa (`analysis/eyes.py`)

**Files:**
- Create: `Photo Selector/photoselect/analysis/eyes.py`
- Create: `Photo Selector/tests/fixtures/face_closed.jpg` (mismo encuadre con ojos cerrados)
- Test: `Photo Selector/tests/test_eyes.py`

- [ ] **Step 1: Añadir la fixture de ojos cerrados**

Copia `face_closed.jpg` a `tests/fixtures/` (un rostro frontal con los ojos claramente cerrados).

- [ ] **Step 2: Escribir el test que falla**

```python
# tests/test_eyes.py
from pathlib import Path
import cv2
from photoselect.analysis import eyes

FIX = Path(__file__).parent / "fixtures"

def test_open_eyes_have_higher_ear_than_closed():
    open_img = cv2.imread(str(FIX / "face_open.jpg"))
    closed_img = cv2.imread(str(FIX / "face_closed.jpg"))
    ear_open, _ = eyes.analyze_eyes(open_img)
    ear_closed, _ = eyes.analyze_eyes(closed_img)
    assert ear_open > ear_closed

def test_returns_zero_when_no_face():
    import numpy as np
    blank = np.zeros((100, 100, 3), np.uint8)
    ear, smiling = eyes.analyze_eyes(blank)
    assert ear == 0.0 and smiling is False
```

- [ ] **Step 3: Ejecutar y ver que falla**

Run: `cd "Photo Selector" && pytest tests/test_eyes.py -v`
Expected: FAIL — módulo inexistente.

- [ ] **Step 4: Implementar `eyes.py`**

```python
# photoselect/analysis/eyes.py
from __future__ import annotations
import math
import cv2
import numpy as np
import mediapipe as mp

_RIGHT_EYE = [33, 160, 158, 133, 153, 144]
_LEFT_EYE = [362, 385, 387, 263, 373, 380]
_MOUTH_CORNERS = (61, 291)
_MOUTH_VERT = (13, 14)

_mesh = mp.solutions.face_mesh.FaceMesh(
    static_image_mode=True, max_num_faces=1, refine_landmarks=True)

def _ear(pts: list[tuple[float, float]]) -> float:
    p1, p2, p3, p4, p5, p6 = pts
    return (math.dist(p2, p6) + math.dist(p3, p5)) / (2.0 * math.dist(p1, p4) + 1e-6)

def analyze_eyes(face_crop_bgr: np.ndarray) -> tuple[float, bool]:
    """Devuelve (EAR promedio de ambos ojos, is_smiling). EAR alto = ojos abiertos."""
    h, w = face_crop_bgr.shape[:2]
    rgb = cv2.cvtColor(face_crop_bgr, cv2.COLOR_BGR2RGB)
    res = _mesh.process(rgb)
    if not res.multi_face_landmarks:
        return 0.0, False
    lm = res.multi_face_landmarks[0].landmark

    def pt(i: int) -> tuple[float, float]:
        return (lm[i].x * w, lm[i].y * h)

    ear = (_ear([pt(i) for i in _RIGHT_EYE]) + _ear([pt(i) for i in _LEFT_EYE])) / 2.0
    mouth_w = math.dist(pt(_MOUTH_CORNERS[0]), pt(_MOUTH_CORNERS[1]))
    mouth_h = math.dist(pt(_MOUTH_VERT[0]), pt(_MOUTH_VERT[1]))
    is_smiling = mouth_w > 0 and (mouth_h / mouth_w) > 0.35
    return float(ear), bool(is_smiling)
```

- [ ] **Step 5: Ejecutar y ver que pasa**

Run: `cd "Photo Selector" && pytest tests/test_eyes.py -v`
Expected: PASS (2 tests).

- [ ] **Step 6: Commit**

```bash
git add "Photo Selector/photoselect/analysis/eyes.py" "Photo Selector/tests/test_eyes.py" "Photo Selector/tests/fixtures/face_closed.jpg"
git commit -m "feat(photo-selector): eye-aspect-ratio + smile via MediaPipe FaceMesh"
```

---

### Task 9: Carga de imágenes (`loader.py`)

**Files:**
- Create: `Photo Selector/photoselect/loader.py`
- Test: `Photo Selector/tests/test_loader.py`

- [ ] **Step 1: Escribir el test que falla**

```python
# tests/test_loader.py
from pathlib import Path
import os
import time
import numpy as np
import cv2
from photoselect import loader

def test_is_raw():
    assert loader.is_raw(Path("a.CR2")) is True
    assert loader.is_raw(Path("a.jpg")) is False

def test_load_jpeg_resizes_to_max_dim(tmp_path: Path):
    big = np.zeros((4000, 6000, 3), np.uint8)
    p = tmp_path / "big.jpg"
    cv2.imwrite(str(p), big)
    img = loader.load_image(p)
    assert max(img.shape[:2]) <= loader.MAX_DIM

def test_capture_timestamp_falls_back_to_mtime(tmp_path: Path):
    p = tmp_path / "x.jpg"
    cv2.imwrite(str(p), np.zeros((10, 10, 3), np.uint8))
    os.utime(p, (1000.0, 1234.0))
    assert loader.capture_timestamp(p) == 1234.0
```

- [ ] **Step 2: Ejecutar y ver que falla**

Run: `cd "Photo Selector" && pytest tests/test_loader.py -v`
Expected: FAIL — módulo inexistente.

- [ ] **Step 3: Implementar `loader.py`**

```python
# photoselect/loader.py
from __future__ import annotations
import datetime
import os
from pathlib import Path
import cv2
import numpy as np

RAW_EXTS = {".cr2", ".cr3", ".nef", ".arw", ".raf", ".rw2", ".orf", ".dng"}
JPEG_EXTS = {".jpg", ".jpeg"}
MAX_DIM = 2500
_EXIF_DATETIME_ORIGINAL = 36867
_EXIF_DATETIME = 306

def is_raw(path: Path) -> bool:
    return path.suffix.lower() in RAW_EXTS

def _resize(img: np.ndarray, max_dim: int = MAX_DIM) -> np.ndarray:
    h, w = img.shape[:2]
    scale = max_dim / max(h, w)
    if scale < 1.0:
        img = cv2.resize(img, (int(w * scale), int(h * scale)), interpolation=cv2.INTER_AREA)
    return img

def load_image(path: Path) -> np.ndarray:
    if is_raw(path):
        return _load_raw_preview(path)
    img = cv2.imread(str(path), cv2.IMREAD_COLOR)
    if img is None:
        raise ValueError(f"No se pudo leer la imagen: {path}")
    return _resize(img)

def _load_raw_preview(path: Path) -> np.ndarray:
    import rawpy
    with rawpy.imread(str(path)) as raw:
        try:
            thumb = raw.extract_thumb()
            if thumb.format == rawpy.ThumbFormat.JPEG:
                arr = cv2.imdecode(np.frombuffer(thumb.data, np.uint8), cv2.IMREAD_COLOR)
                if arr is not None:
                    return _resize(arr)
        except (rawpy.LibRawNoThumbnailError, rawpy.LibRawUnsupportedThumbnailError):
            pass
        rgb = raw.postprocess(half_size=True)
        return _resize(cv2.cvtColor(rgb, cv2.COLOR_RGB2BGR))

def capture_timestamp(path: Path) -> float:
    try:
        from PIL import Image
        exif = Image.open(path).getexif()
        dt = exif.get(_EXIF_DATETIME_ORIGINAL) or exif.get(_EXIF_DATETIME)
        if dt:
            return datetime.datetime.strptime(dt, "%Y:%m:%d %H:%M:%S").timestamp()
    except Exception:
        pass
    return os.path.getmtime(path)
```

- [ ] **Step 4: Ejecutar y ver que pasa**

Run: `cd "Photo Selector" && pytest tests/test_loader.py -v`
Expected: PASS (3 tests).

- [ ] **Step 5: Commit**

```bash
git add "Photo Selector/photoselect/loader.py" "Photo Selector/tests/test_loader.py"
git commit -m "feat(photo-selector): image loader (JPEG/RAW preview, resize, EXIF timestamp)"
```

---

### Task 10: Agrupado de ráfagas (`grouping.py`)

**Files:**
- Create: `Photo Selector/photoselect/grouping.py`
- Test: `Photo Selector/tests/test_grouping.py`

- [ ] **Step 1: Escribir el test que falla**

```python
# tests/test_grouping.py
from pathlib import Path
from photoselect.types import PhotoMetrics
from photoselect.presets import Preset
from photoselect.grouping import group_bursts

def _pm(name, ts, phash):
    return PhotoMetrics(Path(name), ts, 200.0, 0.9, phash)

def test_similar_consecutive_photos_form_one_group():
    preset = Preset()
    photos = [
        _pm("a.jpg", 0.0, 0b0),
        _pm("b.jpg", 1.0, 0b1),       # cerca en tiempo + pHash similar
        _pm("c.jpg", 2.0, 0b11),
        _pm("d.jpg", 60.0, 0xFFFFFFFFFFFFFFFF),  # lejos -> grupo aparte
    ]
    groups = group_bursts(photos, preset)
    assert sorted(len(g) for g in groups) == [1, 3]

def test_time_gap_splits_group():
    preset = Preset(burst_time_window_s=1.0)
    photos = [_pm("a.jpg", 0.0, 0b0), _pm("b.jpg", 5.0, 0b0)]
    assert len(group_bursts(photos, preset)) == 2

def test_every_photo_appears_exactly_once():
    preset = Preset()
    photos = [_pm(f"{i}.jpg", float(i), 0b0) for i in range(5)]
    groups = group_bursts(photos, preset)
    flat = sorted(i for g in groups for i in g)
    assert flat == list(range(5))
```

- [ ] **Step 2: Ejecutar y ver que falla**

Run: `cd "Photo Selector" && pytest tests/test_grouping.py -v`
Expected: FAIL — módulo inexistente.

- [ ] **Step 3: Implementar `grouping.py`**

```python
# photoselect/grouping.py
from __future__ import annotations
from .types import PhotoMetrics
from .embedding import hamming
from .presets import Preset

def group_bursts(photos: list[PhotoMetrics], preset: Preset) -> list[list[int]]:
    """Agrupa índices de fotos consecutivas en el tiempo y perceptualmente similares."""
    if not photos:
        return []
    order = sorted(range(len(photos)), key=lambda i: photos[i].timestamp)
    groups: list[list[int]] = []
    current: list[int] = [order[0]]
    for idx in order[1:]:
        prev, cur = photos[current[-1]], photos[idx]
        same_time = (cur.timestamp - prev.timestamp) <= preset.burst_time_window_s
        similar = hamming(cur.phash, prev.phash) <= preset.phash_max_distance
        if same_time and similar:
            current.append(idx)
        else:
            groups.append(current)
            current = [idx]
    groups.append(current)
    return groups
```

- [ ] **Step 4: Ejecutar y ver que pasa**

Run: `cd "Photo Selector" && pytest tests/test_grouping.py -v`
Expected: PASS (3 tests).

- [ ] **Step 5: Commit**

```bash
git add "Photo Selector/photoselect/grouping.py" "Photo Selector/tests/test_grouping.py"
git commit -m "feat(photo-selector): sequential burst grouping (time + pHash)"
```

---

### Task 11: Decisión (`decision.py`)

**Files:**
- Create: `Photo Selector/photoselect/decision.py`
- Test: `Photo Selector/tests/test_decision.py`

- [ ] **Step 1: Escribir el test que falla**

```python
# tests/test_decision.py
from pathlib import Path
from photoselect.types import PhotoMetrics, FaceMetrics
from photoselect.presets import Preset
from photoselect.decision import decide, photo_score

def _face(ear=0.3, sharp=250.0, smiling=True):
    return FaceMetrics((0, 0, 50, 50), ear, sharp, smiling)

def _pm(name, sharp=250.0, expo=0.9, faces=None):
    return PhotoMetrics(Path(name), 0.0, sharp, expo, 0, faces or [])

def test_blurry_photo_is_red():
    preset = Preset()
    photos = [_pm("blur.jpg", sharp=10.0)]
    groups = [[0]]
    d = decide(photos, groups, preset)[0]
    assert d.label == "Red" and d.rating == 0

def test_best_of_group_green_others_red():
    preset = Preset()
    photos = [
        _pm("a.jpg", faces=[_face(ear=0.05)]),   # ojos cerrados -> peor
        _pm("b.jpg", faces=[_face(ear=0.35)]),   # ojos abiertos -> mejor
    ]
    groups = [[0, 1]]
    decisions = decide(photos, groups, preset)
    assert decisions[1].label in ("Green", "Blue")
    assert decisions[0].label == "Red"

def test_detail_shot_without_faces_is_kept():
    preset = Preset(keep_detail_shots=True)
    photos = [_pm("cake.jpg", sharp=250.0, expo=0.9, faces=[])]
    groups = [[0]]
    d = decide(photos, groups, preset)[0]
    assert d.label in ("Green", "Blue") and d.rating == 3

def test_closed_eyes_lower_score():
    preset = Preset()
    open_p = _pm("o.jpg", faces=[_face(ear=0.35)])
    closed_p = _pm("c.jpg", faces=[_face(ear=0.05)])
    assert photo_score(open_p, preset) > photo_score(closed_p, preset)
```

- [ ] **Step 2: Ejecutar y ver que falla**

Run: `cd "Photo Selector" && pytest tests/test_decision.py -v`
Expected: FAIL — módulo inexistente.

- [ ] **Step 3: Implementar `decision.py`**

```python
# photoselect/decision.py
from __future__ import annotations
from .types import PhotoMetrics, Decision
from .presets import Preset

def photo_score(p: PhotoMetrics, preset: Preset) -> float:
    w = preset.weights

    def nsharp(v: float) -> float:
        return min(1.0, v / preset.sharp_ref)

    if not p.has_faces:
        return 0.6 * nsharp(p.sharpness_global) + 0.4 * p.exposure_score

    n = len(p.faces)
    eye_sharp = sum(nsharp(f.eye_sharpness) for f in p.faces) / n
    eyes_open = sum(1.0 for f in p.faces if f.eye_aspect_ratio >= preset.ear_threshold) / n
    smiling = sum(1.0 for f in p.faces if f.is_smiling) / n
    return (w["eye_sharp"] * eye_sharp + w["sharp"] * nsharp(p.sharpness_global)
            + w["expo"] * p.exposure_score + w["eyes_open"] * eyes_open + w["smile"] * smiling)

def _keep_solo(p: PhotoMetrics, score: float, preset: Preset) -> bool:
    if score >= preset.keeper_threshold:
        return True
    return (not p.has_faces and preset.keep_detail_shots and p.exposure_score >= 0.5
            and p.sharpness_global >= preset.blur_threshold)

def decide(photos: list[PhotoMetrics], groups: list[list[int]], preset: Preset) -> list[Decision]:
    scores = [photo_score(p, preset) for p in photos]
    out: dict[int, Decision] = {}
    lab = preset.labels
    for group in groups:
        best = max(group, key=lambda i: scores[i])
        for i in group:
            p = photos[i]
            if p.sharpness_global < preset.blur_threshold:
                out[i] = Decision(p.path, lab["reject"], 0)
            elif i != best:
                out[i] = Decision(p.path, lab["reject"], 0)   # peor del grupo
            elif len(group) == 1 and not _keep_solo(p, scores[i], preset):
                out[i] = Decision(p.path, None, 0)
            else:
                label = lab["highlight"] if scores[i] >= preset.highlight_threshold else lab["keeper"]
                out[i] = Decision(p.path, label, preset.stars_keeper)
    return [out[i] for i in range(len(photos))]
```

- [ ] **Step 4: Ejecutar y ver que pasa**

Run: `cd "Photo Selector" && pytest tests/test_decision.py -v`
Expected: PASS (4 tests).

- [ ] **Step 5: Commit**

```bash
git add "Photo Selector/photoselect/decision.py" "Photo Selector/tests/test_decision.py"
git commit -m "feat(photo-selector): scoring + decision rules (green/blue/red)"
```

---

### Task 12: Escritura XMP (`xmp_writer.py`)

**Files:**
- Create: `Photo Selector/photoselect/xmp_writer.py`
- Test: `Photo Selector/tests/test_xmp_writer.py`

> **Nota:** `build_xmp` es puro (testeado). `write_metadata` para JPEG llama a `exiftool`
> (binario externo) — ese test se SKIPpea si `exiftool` no está en el PATH.

- [ ] **Step 1: Escribir el test que falla**

```python
# tests/test_xmp_writer.py
import shutil
from pathlib import Path
import cv2
import numpy as np
import pytest
from photoselect import xmp_writer

def test_build_xmp_includes_rating_and_label():
    xmp = xmp_writer.build_xmp(3, "Green")
    assert "<xmp:Rating>3</xmp:Rating>" in xmp
    assert "<xmp:Label>Green</xmp:Label>" in xmp

def test_build_xmp_without_label_omits_label_tag():
    xmp = xmp_writer.build_xmp(0, None)
    assert "xmp:Label" not in xmp

def test_raw_writes_sidecar(tmp_path: Path):
    raw = tmp_path / "img.CR2"
    raw.write_bytes(b"fake-raw")
    xmp_writer.write_metadata(raw, 3, "Green")
    sidecar = tmp_path / "img.xmp"
    assert sidecar.exists()
    assert "Green" in sidecar.read_text(encoding="utf-8")

@pytest.mark.skipif(shutil.which("exiftool") is None, reason="exiftool no instalado")
def test_jpeg_embeds_metadata(tmp_path: Path):
    p = tmp_path / "img.jpg"
    cv2.imwrite(str(p), np.zeros((20, 20, 3), np.uint8))
    xmp_writer.write_metadata(p, 3, "Green")
    import subprocess
    res = subprocess.run(["exiftool", "-XMP-xmp:Rating", "-XMP-xmp:Label", str(p)],
                         capture_output=True, text=True)
    assert "3" in res.stdout and "Green" in res.stdout
    assert not (tmp_path / "img.xmp").exists()   # no sidecar para JPEG
```

- [ ] **Step 2: Ejecutar y ver que falla**

Run: `cd "Photo Selector" && pytest tests/test_xmp_writer.py -v`
Expected: FAIL — módulo inexistente.

- [ ] **Step 3: Implementar `xmp_writer.py`**

```python
# photoselect/xmp_writer.py
from __future__ import annotations
import subprocess
from pathlib import Path
from .loader import is_raw

_XMP_TEMPLATE = """<?xpacket begin="﻿" id="W5M0MpCehiHzreSzNTczkc9d"?>
<x:xmpmeta xmlns:x="adobe:ns:meta/">
 <rdf:RDF xmlns:rdf="http://www.w3.org/1999/02/22-rdf-syntax-ns#">
  <rdf:Description rdf:about="" xmlns:xmp="http://ns.adobe.com/xap/1.0/">
   <xmp:Rating>{rating}</xmp:Rating>{label}
  </rdf:Description>
 </rdf:RDF>
</x:xmpmeta>
<?xpacket end="w"?>"""

def build_xmp(rating: int, label: str | None) -> str:
    label_xml = f"\n   <xmp:Label>{label}</xmp:Label>" if label else ""
    return _XMP_TEMPLATE.format(rating=rating, label=label_xml)

def write_metadata(path: Path, rating: int, label: str | None) -> None:
    if is_raw(path):
        path.with_suffix(".xmp").write_text(build_xmp(rating, label), encoding="utf-8")
    else:
        _embed_jpeg(path, rating, label)

def _embed_jpeg(path: Path, rating: int, label: str | None) -> None:
    args = ["exiftool", "-overwrite_original", "-P", f"-XMP-xmp:Rating={rating}",
            f"-XMP-xmp:Label={label or ''}", str(path)]
    subprocess.run(args, check=True, capture_output=True)
```

- [ ] **Step 4: Ejecutar y ver que pasa**

Run: `cd "Photo Selector" && pytest tests/test_xmp_writer.py -v`
Expected: PASS (3 tests + 1 skip si no hay exiftool).

- [ ] **Step 5: Commit**

```bash
git add "Photo Selector/photoselect/xmp_writer.py" "Photo Selector/tests/test_xmp_writer.py"
git commit -m "feat(photo-selector): XMP writer (RAW sidecar, JPEG embedded via exiftool)"
```

---

### Task 13: Pipeline (`pipeline.py`)

**Files:**
- Create: `Photo Selector/photoselect/pipeline.py`
- Test: `Photo Selector/tests/test_pipeline.py`

> El test usa monkeypatch para no depender de modelos pesados: sustituye los analizadores
> por stubs deterministas y verifica el cableado (orden, ensamblado de `PhotoMetrics`,
> longitud de decisiones).

- [ ] **Step 1: Escribir el test que falla**

```python
# tests/test_pipeline.py
from pathlib import Path
import numpy as np
import cv2
from photoselect import pipeline
from photoselect.presets import Preset

def test_cull_folder_returns_decision_per_image(tmp_path: Path, monkeypatch):
    for i in range(3):
        cv2.imwrite(str(tmp_path / f"img_{i}.jpg"), np.zeros((20, 20, 3), np.uint8))
    (tmp_path / "notes.txt").write_text("ignore me")

    monkeypatch.setattr(pipeline.loader, "load_image", lambda p: np.zeros((20, 20, 3), np.uint8))
    monkeypatch.setattr(pipeline.loader, "capture_timestamp", lambda p: 0.0)
    monkeypatch.setattr(pipeline.sharpness, "global_sharpness", lambda img: 250.0)
    monkeypatch.setattr(pipeline.exposure, "exposure_score", lambda img: 0.9)
    monkeypatch.setattr(pipeline.embedding, "phash", lambda img: 0)
    monkeypatch.setattr(pipeline.faces, "detect_faces", lambda img: [])

    decisions = pipeline.cull_folder(tmp_path, Preset())
    assert len(decisions) == 3
    assert all(d.path.suffix == ".jpg" for d in decisions)

def test_analyze_photo_assembles_metrics(tmp_path: Path, monkeypatch):
    p = tmp_path / "a.jpg"
    cv2.imwrite(str(p), np.zeros((20, 20, 3), np.uint8))
    monkeypatch.setattr(pipeline.loader, "load_image", lambda x: np.zeros((20, 20, 3), np.uint8))
    monkeypatch.setattr(pipeline.loader, "capture_timestamp", lambda x: 42.0)
    monkeypatch.setattr(pipeline.sharpness, "global_sharpness", lambda img: 111.0)
    monkeypatch.setattr(pipeline.exposure, "exposure_score", lambda img: 0.8)
    monkeypatch.setattr(pipeline.embedding, "phash", lambda img: 7)
    monkeypatch.setattr(pipeline.faces, "detect_faces", lambda img: [(0, 0, 10, 10)])
    monkeypatch.setattr(pipeline.eyes, "analyze_eyes", lambda crop: (0.3, True))
    monkeypatch.setattr(pipeline.sharpness, "region_sharpness", lambda img, box: 90.0)

    pm = pipeline.analyze_photo(p)
    assert pm.timestamp == 42.0 and pm.sharpness_global == 111.0
    assert pm.phash == 7 and len(pm.faces) == 1
    assert pm.faces[0].eye_aspect_ratio == 0.3
```

- [ ] **Step 2: Ejecutar y ver que falla**

Run: `cd "Photo Selector" && pytest tests/test_pipeline.py -v`
Expected: FAIL — módulo inexistente.

- [ ] **Step 3: Implementar `pipeline.py`**

```python
# photoselect/pipeline.py
from __future__ import annotations
from pathlib import Path
from . import loader, grouping, decision
from .analysis import sharpness, exposure, embedding, faces, eyes
from .types import PhotoMetrics, FaceMetrics, Decision
from .presets import Preset

IMAGE_EXTS = loader.JPEG_EXTS | loader.RAW_EXTS

def analyze_photo(path: Path) -> PhotoMetrics:
    img = loader.load_image(path)
    face_metrics: list[FaceMetrics] = []
    for box in faces.detect_faces(img):
        x, y, w, h = box
        crop = img[max(0, y):y + h, max(0, x):x + w]
        if crop.size == 0:
            continue
        ear, smiling = eyes.analyze_eyes(crop)
        face_metrics.append(FaceMetrics(box, ear, sharpness.region_sharpness(img, box), smiling))
    return PhotoMetrics(
        path=path,
        timestamp=loader.capture_timestamp(path),
        sharpness_global=sharpness.global_sharpness(img),
        exposure_score=exposure.exposure_score(img),
        phash=embedding.phash(img),
        faces=face_metrics,
    )

def cull_folder(folder: Path, preset: Preset) -> list[Decision]:
    paths = sorted(p for p in folder.iterdir() if p.suffix.lower() in IMAGE_EXTS)
    photos = [analyze_photo(p) for p in paths]
    groups = grouping.group_bursts(photos, preset)
    return decision.decide(photos, groups, preset)
```

- [ ] **Step 4: Ejecutar y ver que pasa**

Run: `cd "Photo Selector" && pytest tests/test_pipeline.py -v`
Expected: PASS (2 tests).

- [ ] **Step 5: Commit**

```bash
git add "Photo Selector/photoselect/pipeline.py" "Photo Selector/tests/test_pipeline.py"
git commit -m "feat(photo-selector): pipeline (analyze_photo + cull_folder)"
```

---

### Task 14: CLI (`cli.py`)

**Files:**
- Create: `Photo Selector/photoselect/cli.py`
- Test: `Photo Selector/tests/test_cli.py`

- [ ] **Step 1: Escribir el test que falla**

```python
# tests/test_cli.py
import json
from pathlib import Path
from typer.testing import CliRunner
from photoselect.cli import app
from photoselect.types import Decision
from photoselect import cli

runner = CliRunner()

def test_dry_run_outputs_json(tmp_path: Path, monkeypatch):
    monkeypatch.setattr(cli, "cull_folder",
                        lambda folder, cfg: [Decision(Path("a.jpg"), "Green", 3)])
    out = tmp_path / "report.json"
    result = runner.invoke(app, ["cull", str(tmp_path), "--dry-run", "--out", str(out)])
    assert result.exit_code == 0
    data = json.loads(out.read_text(encoding="utf-8"))
    assert data[0]["label"] == "Green" and data[0]["rating"] == 3

def test_cull_writes_metadata(tmp_path: Path, monkeypatch):
    written = []
    monkeypatch.setattr(cli, "cull_folder",
                        lambda folder, cfg: [Decision(Path("a.jpg"), "Red", 0)])
    monkeypatch.setattr(cli.xmp_writer, "write_metadata",
                        lambda path, rating, label: written.append((path, rating, label)))
    result = runner.invoke(app, ["cull", str(tmp_path)])
    assert result.exit_code == 0
    assert written == [(Path("a.jpg"), 0, "Red")]

def test_blur_flag_overrides_preset(tmp_path: Path, monkeypatch):
    captured = {}
    monkeypatch.setattr(cli, "cull_folder",
                        lambda folder, cfg: captured.setdefault("blur", cfg.blur) or [])
    runner.invoke(app, ["cull", str(tmp_path), "--blur", "estricto", "--dry-run"])
    assert captured["blur"] == "estricto"
```

- [ ] **Step 2: Ejecutar y ver que falla**

Run: `cd "Photo Selector" && pytest tests/test_cli.py -v`
Expected: FAIL — módulo inexistente.

- [ ] **Step 3: Implementar `cli.py`**

```python
# photoselect/cli.py
from __future__ import annotations
import json
from dataclasses import replace
from pathlib import Path
import typer
from .presets import load_preset
from .pipeline import cull_folder
from . import xmp_writer

app = typer.Typer(help="Selector de fotos de eventos (culling).")

@app.command()
def cull(
    folder: Path = typer.Argument(..., help="Carpeta con las fotos"),
    preset: Path = typer.Option(None, "--preset", help="Archivo YAML de preset"),
    blur: str = typer.Option(None, "--blur", help="indulgente | moderado | estricto"),
    dry_run: bool = typer.Option(False, "--dry-run", help="No escribe XMP; solo reporta"),
    out: Path = typer.Option(None, "--out", help="Ruta del JSON de reporte (con --dry-run)"),
) -> None:
    cfg = load_preset(preset)
    if blur:
        cfg = replace(cfg, blur=blur)
    decisions = cull_folder(folder, cfg)

    if dry_run:
        payload = [{"path": str(d.path), "label": d.label, "rating": d.rating} for d in decisions]
        text = json.dumps(payload, indent=2, ensure_ascii=False)
        if out:
            out.write_text(text, encoding="utf-8")
        else:
            typer.echo(text)
        return

    for d in decisions:
        xmp_writer.write_metadata(d.path, d.rating, d.label)
    typer.echo(f"Procesadas {len(decisions)} fotos.")
```

> `dataclasses.replace` requiere que `Preset` sea un dataclass (lo es). Reemplaza `blur` y
> recalcula `blur_threshold` automáticamente (es `@property`).

- [ ] **Step 4: Ejecutar y ver que pasa**

Run: `cd "Photo Selector" && pytest tests/test_cli.py -v`
Expected: PASS (3 tests).

- [ ] **Step 5: Correr toda la suite + lint**

Run: `cd "Photo Selector" && pytest -q && ruff check .`
Expected: todos los tests verdes (los de modelo SKIPpean si falta YuNet/exiftool); ruff limpio.

- [ ] **Step 6: Commit**

```bash
git add "Photo Selector/photoselect/cli.py" "Photo Selector/tests/test_cli.py"
git commit -m "feat(photo-selector): typer CLI (cull, --dry-run, --blur, --preset)"
```

---

### Task 15: Prueba de extremo a extremo con fotos reales (manual)

**Files:** ninguno (verificación manual).

- [ ] **Step 1:** Copia 20–40 fotos reales de un evento (mezcla nítidas, borrosas, ráfagas, ojos cerrados, una de detalle/torta) a una carpeta de prueba.

- [ ] **Step 2:** Dry-run para inspeccionar sin tocar nada:

Run: `cd "Photo Selector" && photoselect cull "RUTA/carpeta" --dry-run --out report.json`
Expected: `report.json` con un objeto por foto (`path`, `label`, `rating`). Revisa que:
borrosas → `Red`; mejor de cada ráfaga → `Green`/`Blue`, las otras → `Red`; foto de detalle → `Green`.

- [ ] **Step 3:** Ejecutar de verdad (escribe XMP):

Run: `cd "Photo Selector" && photoselect cull "RUTA/carpeta"`
Expected: "Procesadas N fotos." JPEGs con metadatos embebidos; RAW con sidecar `.xmp`.

- [ ] **Step 4:** Abrir la carpeta en Lightroom y confirmar que los colores y estrellas aparecen. Ajustar umbrales en un preset YAML si hace falta (`--blur`, pesos) y repetir el dry-run.

---

## Self-Review (cobertura del spec)

| Requisito del spec | Tarea |
|---|---|
| CLI sin UI, flags + preset YAML | 3, 14 |
| JPEG directo / RAW preview embebido / resize ≤2500px | 9 |
| Timestamp EXIF con fallback | 9 |
| Nitidez global + por región (ojos) | 4 |
| Caras (YuNet) | 7 |
| Ojos abiertos/cerrados (EAR) + sonrisa | 8 |
| Exposición (histograma) | 5 |
| Duplicados pHash + ventana temporal | 6, 10 |
| Reglas: borrosa→Red, mejor grupo→Green/Blue, peores→Red | 11 |
| Ojos cerrados = solo penaliza ranking (sin color) | 11 |
| `keep_detail_shots` (fotos sin caras nítidas) | 11 |
| Escribe Label+Rating: sidecar RAW / embebido JPEG | 12 |
| Orquestación carpeta→decisiones | 13 |
| `--dry-run` con JSON | 14 |
| Verificación end-to-end en Lightroom | 15 |

**Fuera de alcance (Fase 2 del Proyecto 1):** aprendizaje de preferencias a partir de
correcciones. No se implementa en este plan; el diseño se especificará al llegar a esa fase.
```
