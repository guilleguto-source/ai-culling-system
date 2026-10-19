# Spec: Photo Selector — Proyecto 1: Motor de Selección (Culling)

> Estado: borrador para revisión · Fecha: 2026-06-26

## Objective

Construir un **culler local** para eventos (estilo Aftershoot) que reciba una carpeta
de fotos y devuelva una preselección calificada, escrita como **XMP sidecar** para
revisarla en Lightroom.

- **Usuario:** fotógrafo de eventos (escolares, sociales) que dispara ~500–2.000 fotos
  por evento, mayormente JPEG, a veces RAW.
- **Problema que resuelve:** el culling manual de cada evento consume horas. El motor
  marca automáticamente keepers, borrosas, ojos cerrados y duplicados.
- **Éxito (fase 1):** apuntar el motor a una carpeta → en minutos cada foto tiene su
  `Label` de color + `Rating` en XMP → al abrir Lightroom el fotógrafo filtra por
  color/estrella y revisa, replicando su flujo actual de Aftershoot.

### Flujo actual del usuario (a replicar)

Preset "Eventos escolares", cantidad estándar. Etiquetas de color:

| Color  | Significado                              | Acción del usuario        |
|--------|------------------------------------------|---------------------------|
| 🟢 Green  | Seleccionado (keeper / mejor del grupo) | Conserva                  |
| 🔵 Blue   | Destacado (lo mejor de lo mejor)         | Conserva, prioriza        |
| 🔴 Red    | Borrosa **o** peor(es) de un grupo de duplicados | **Revisa** antes de borrar |
| (sin color) | Neutra (no seleccionada, no descartada) | —                       |

Estrellas: keeper = 3★. Escribe a XMP. El usuario revisa los 🔴 antes de borrar.

**Decisiones del usuario (2026-06-26):**
- **Ojos cerrados:** NO lleva color; solo penaliza el ranking para elegir la mejor del grupo.
- **Duplicados:** NO se apilan de forma nativa (los stacks viven en el `.lrcat`, no en XMP).
  En cambio: la mejor del grupo = 🟢 Green; la(s) peor(es) del grupo = 🔴 Red. Sin 🟡.
- **Fotos de detalle:** las fotos **sin caras** pero nítidas y bien expuestas (torta,
  decoración, detalles) NO se descartan — regla `keep_detail_shots`.

## Tech Stack

- **Python 3.11**
- **ONNX Runtime (CPU)** — inferencia de modelos.
- **OpenCV (`opencv-contrib-python`)** — I/O de imagen, YuNet face detector, Laplaciano.
- **MediaPipe Face Mesh** — landmarks faciales (ojos para EAR, sonrisa, orientación).
- **rawpy** + **exifread/Pillow** — extracción del JPEG embebido de RAW; lectura EXIF (timestamp).
- **imagehash (pHash)** — hash perceptual para duplicados casi idénticos.
- **NumPy / scikit-learn** — clustering de ráfagas (DBSCAN sobre distancia de embeddings + tiempo).
- **python-xmp-toolkit** o escritura directa de XMP (formato Adobe `crs`/`xap`).
- **typer** — CLI.

Todos los modelos son **pre-entrenados**; no se entrena nada en fase 1.

## Commands

```bash
# Instalar
pip install -e .

# Procesar una carpeta (escribe XMP junto a cada foto)
photoselect cull ./evento --preset eventos-escolares

# Dry-run: genera un reporte JSON sin tocar XMP
photoselect cull ./evento --dry-run --out report.json

# Ajustar severidad de detección de borrosas (indulgente|moderado|estricto)
photoselect cull ./evento --blur strict

# Tests
pytest
pytest --cov=photoselect

# Lint / formato
ruff check . --fix
ruff format .
```

## Project Structure

```
photoselect/
  __init__.py
  cli.py                 → entrypoint typer (cull, dry-run)
  pipeline.py            → orquesta: carga → análisis → agrupado → decisión → salida
  io/
    loader.py            → resuelve JPEG/RAW; extrae preview embebido; reescala a ~2500px
    xmp_writer.py        → escribe Label + Rating al sidecar .xmp
  analysis/
    faces.py             → YuNet: detecta caras, devuelve cajas + score
    eyes.py              → MediaPipe: EAR (ojos abiertos/cerrados), mirada, sonrisa
    sharpness.py         → varianza Laplaciano global + sobre región de ojos
    exposure.py          → métricas de histograma (quemados, sombras tapadas)
    embedding.py         → vector perceptual por foto (pHash + features ligeras)
  grouping.py            → clustering de ráfagas (tiempo + similitud) → grupos
  decision.py            → reglas: asigna color+estrellas, elige mejor de cada grupo
  presets.py             → parámetros por preset (umbrales, severidad)
tests/
  fixtures/              → imágenes de prueba pequeñas (nítida, borrosa, ojos cerrados, ráfaga)
  test_sharpness.py
  test_eyes.py
  test_grouping.py
  test_decision.py
  test_xmp_writer.py
docs/superpowers/specs/  → este spec
```

## Code Style

Funciones puras y testeables; cada analizador recibe una imagen (o crop) y devuelve un
dataclass de métricas, sin efectos secundarios. La decisión final vive en un solo lugar.

```python
from dataclasses import dataclass

@dataclass(frozen=True)
class FaceMetrics:
    box: tuple[int, int, int, int]      # x, y, w, h
    eye_aspect_ratio: float             # < EAR_THRESHOLD = ojos cerrados
    eye_sharpness: float                # varianza Laplaciano sobre región de ojos
    is_smiling: bool

def analyze_face(crop: np.ndarray) -> FaceMetrics:
    """Métricas de UNA cara recortada. Sin I/O, sin estado global."""
    ...
```

Convenciones: `snake_case`; type hints obligatorios; dataclasses `frozen` para
resultados; umbrales nombrados (constantes en `presets.py`, nunca números mágicos en lógica).

## Data Flow

```
carpeta → loader (preview ~2500px + EXIF time)
        → faces → [por cara: eyes, eye_sharpness]
        → sharpness global → exposure → embedding(pHash)
        → grouping (DBSCAN: tiempo+similitud) → grupos de ráfaga
        → decision (reglas + mejor de cada grupo)
        → xmp_writer (Label + Rating)
```

### Reglas de decisión (una foto, un color)

Se evalúa en este orden; el primero que aplica gana:

1. **🔴 Red** — `sharpness_global < blur_threshold` (severidad ajustable). Borrosa global.
2. **🔴 Red** — pertenece a un grupo de duplicados y es de las **peores** del grupo
   (todas menos la mejor, o las que quedan por debajo de un margen de score).
3. **🔵 Blue** — es la mejor de su grupo **y** score alto (destacado).
4. **🟢 Green** — keeper: mejor de su grupo, o foto suelta que pasa umbrales, o
   **foto de detalle** (sin caras, nítida, bien expuesta) si `keep_detail_shots`.
5. Sin color — neutra (no entra en selección ni en descartes).

Ojos cerrados **no produce color**: solo baja el score de esa foto para que no sea
elegida como mejor del grupo.

Estrellas: keepers (Green/Blue) = **3★**. Configurable por preset.

"Mejor del grupo" = mayor score combinado: `w1·eye_sharpness_open + w2·sharpness_global
+ w3·exposure_ok + w4·(ojos_abiertos) + w5·sonrisa`. Pesos en `presets.py` (y ajustables
por el aprendizaje de Fase 2 — ver abajo).

### Fase 2 (dentro del Proyecto 1): aprendizaje de tus preferencias

Add-on opcional posterior a que el motor base funcione. El motor registra las
**correcciones** del usuario (fotos que re-seleccionó o descartó respecto a lo que sugirió)
en un log; un ajuste periódico re-pondera los pesos del score para acercarse al gusto del
usuario (p. ej. dar más valor a fotos de detalle). No es edición — es personalización de la
selección. Detalle de diseño se especifica cuando lleguemos a esta fase.

## Testing Strategy

- **Framework:** pytest + pytest-cov.
- **Unitarios por analizador:** cada uno con fixtures conocidos (una nítida vs una borrosa
  → `sharpness` las separa; un par ojos abiertos/cerrados → `eyes` los separa).
- **Agrupado:** fixture de 4 fotos casi idénticas (ráfaga) + 1 distinta → un solo grupo + suelta.
- **Decisión:** tabla de casos (entrada de métricas → color+estrellas esperado). Es lógica
  pura, fácil de cubrir al 100%.
- **XMP:** escribir y releer el sidecar; verificar `Label` y `Rating` correctos y que
  Lightroom los interpreta (validar contra un XMP de referencia exportado por Lightroom).
- **Cobertura objetivo:** ≥85% en `analysis/`, `grouping.py`, `decision.py`, `xmp_writer.py`.

## Boundaries

- **Siempre:** correr `pytest` y `ruff` antes de commit; no tocar el archivo de imagen
  original (solo escribir el `.xmp` sidecar); umbrales en `presets.py`.
- **Preguntar primero:** añadir dependencias nuevas; cambiar el mapeo color→significado;
  escribir algo que no sea el sidecar (p. ej. mover/borrar archivos).
- **Nunca:** borrar fotos automáticamente (el usuario revisa los 🔴 antes); modificar el
  catálogo `.lrcat` de Lightroom; subir imágenes a ningún servicio externo.

## Success Criteria

1. `photoselect cull ./evento` procesa 1.000 JPEG en CPU en un tiempo razonable
   (objetivo orientativo: < ~15 min) y escribe un `.xmp` por foto.
2. Sobre un set de prueba etiquetado a mano: borrosas detectadas con **recall ≥ 90%**
   (no se nos escapan borrosas obvias) sin marcar en rojo fotos claramente nítidas.
3. Ojos cerrados: detecta ≥ 85% de los casos evidentes en fotos con caras frontales.
4. Ráfagas casi idénticas quedan en el mismo grupo y se marca exactamente una keeper.
5. Al abrir la carpeta en Lightroom, los colores y estrellas aparecen correctamente.
6. `--dry-run` produce un JSON con métricas por foto para inspección/ajuste de umbrales.

## Decisiones cerradas (2026-06-26)

- **Sin UI** en fase 1: opciones por flags de CLI + preset YAML.
- **CPU por defecto, GPU opcional** (mismo código, `onnxruntime-gpu` si más adelante).
- **RAW:** extraer JPEG embebido a resolución completa; si falta, decodificar a media res.
- **No** leer los Smart Previews / catálogo de Lightroom (sin acoplarse a internals Adobe).
- **Duplicados:** pHash + ventana temporal para arrancar; mejor=Green, peores=Red, sin apilado nativo.
- **Ojos cerrados:** solo penaliza ranking, sin color.
- **`keep_detail_shots`:** activado — no descartar fotos sin caras pero nítidas.
- **Aprendizaje de preferencias:** Fase 2 del Proyecto 1.

## Open Questions

1. **Embedding para duplicados:** si pHash + ventana temporal se queda corto agrupando
   variaciones de un mismo momento, escalar a embeddings ONNX (MobileNet/CLIP). A evaluar
   en implementación, no bloquea el arranque.
2. **Mirada a cámara:** ¿criterio de selección en tus eventos o secundario? (Por defecto:
   factor menor del score, no decisivo.)
```
