# Plan de implementación: aprendizaje del historial + reconocimiento de personas

**Fecha**: 2026-07-17
**Contexto**: el programa ya aprende del gusto (duelos + sync de Lightroom) y
de la calibración de rostros. Este plan explota dos fuentes nuevas y grandes:
(1) el **historial de ediciones** del usuario (2 años en Lightroom) y (2) la
**identidad de las personas** (ArcFace). No inventa señal: aprende de lo que el
fotógrafo ya decidió.

## Datos disponibles (relevados 2026-07-17)

- **Catálogo autoritativo**: `Catalogo 2025.lrcat` — 129k imágenes (feb-2024 a
  jul-2026), prácticamente todas con revelado; 27k con estrellas, 11.8k con
  color. El "Catalogo 2026" quedó abandonado. Fuente completa aunque el XMP no
  se haya escrito a disco.
- **En disco**: RAW con sidecar `.xmp` (revelado 100%, rating ~37%) y JPG con
  XMP embebido (rating+color leíbles con el `xmp_reader` actual). ~4.840
  sidecars; recorte completo (CropTop/Left/Bottom/Right + CropAngle).

## Convención de selección del usuario (regla de "seleccionada")

Ver memoria `photo-selector-rating-convention`. Resumen, **solo desde
2025-02-01** (105.588 fotos en ese rango):

| Marca | Significado | Señal |
|---|---|---|
| 2★ (16.398) | Interesante | **Positiva** |
| 3★ (2.113) | Super | **Positiva fuerte** (highlight) |
| 1★ (3.222) | Bajada al editar, no convenció | **Negativa** |
| Banderín negro / pick=-1 (3.026) | A borrar | **Negativa** |
| 4★ (1.053) / 5★ (34) | Marcador "por dónde quedé" | **Ignorar** |
| 0★ (82.768) | Sin revisar o no interesa | Ambiguo (ver Fase H) |

- **Ignorar colores** (uso reciente, Rojas apenas ahora).
- **Ignorar banderín blanco** (pick=1): no es parte del método.
- **Ignorar ediciones extremas** de exposición (>~1 EV): son errores del
  usuario en fotos muy oscuras (3-4 proyectos), no su estilo.

## Principio de orden

La **Fase H** (bootstrap del historial) es el cimiento de datos: alimenta el
gusto, el revelado (J) y el recorte (K). La **Fase I** (escena) es requisito de
J y K. **ArcFace (Fase L)** es una pista independiente (identidad), sin
dependencias con las demás. Cada fase deja el sistema funcionando y con tests
en verde.

Prioridad recomendada: **H → I → J** (cadena de más valor y menor esfuerzo),
**K** después (geométrica, más difícil), **L** en paralelo cuando se quiera.

---

## Fase H — Bootstrap del historial (cimiento de datos)

**Problema**: 2 años de decisiones del fotógrafo viven en el catálogo y los XMP,
pero el sistema solo aprende de lo que él corrige *después* de un culling.

**Diseño**:
- `backend/services/lr_catalog.py` (nuevo): lector **solo-lectura** del
  `.lrcat` (SQLite, `mode=ro&immutable=1`). Mapea `Adobe_images` ↔ ruta de
  archivo (`AgLibraryFile` + `AgLibraryFolder`) y expone rating, pick,
  captureTime, y los ajustes de revelado/recorte (`Adobe_imageDevelopSettings`).
  Filtra `captureTime >= '2025-02-01'`.
- `backend/services/xmp_reader.py` (extender): hoy solo lee `stars`/`color`.
  Añadir lectura de **revelado** (Exposure2012, Temperature, Tint, Contrast2012,
  Highlights/Shadows2012, etc.) y **recorte** (Crop*). Para eventos sin catálogo.
- `backend/services/history_bootstrap.py` (nuevo):
  - **H1 (barato, sin análisis de imagen)**: recorre catálogo/XMP, aplica la
    convención → etiqueta cada foto como `positiva | negativa | ignorar` y
    guarda sus registros crudos de revelado y recorte. Sin tocar píxeles.
  - **H2 (pesado, lote)**: para las fotos de ráfagas *revisadas* (que contienen
    al menos una 2★+, prueba de revisión), calcula el embedding CLIP y sintetiza
    pares **ganadora (2-3★) vs perdedora (0-1★/negro)** dentro de la ráfaga →
    `taste_model.add_example` / `learn_preference` con `source="history"`. Reusa
    el clustering por phash+tiempo ya existente.
  - Peso temporal: los eventos recientes pesan más (deriva de gusto en 2 años).
- Endpoint `POST /history/bootstrap {roots, dry_run}`: dry-run primero (reporta
  cuántas positivas/negativas/pares saldrían, sin escribir), luego real. Lote de
  una noche; idempotente (marca eventos ya procesados).

**Riesgo**: cómputo de H2 (analizar decenas de miles de imágenes). Mitigación:
correr primero sobre 3-4 eventos recientes, ver el `cross_val` del gusto, y
recién escalar. H1 no tiene ese costo.

**Tests**: `test_lr_catalog.py` (mapeo ruta↔imagen sobre un `.lrcat` mínimo
sintético, filtro de fecha), `test_history_bootstrap.py` (convención de
etiquetas; una ráfaga sin 2★ no genera pares; extremos de exposición excluidos).

---

## Fase I — Categorización de escena (data-driven)

**Problema**: para aprender revelado y recorte "por tipo de foto" hace falta
saber el tipo, y el clasificador de escena actual tiene categorías limitadas.

**Diseño**:
- `backend/services/scene_grouping.py` (nuevo): sobre los embeddings CLIP de las
  fotos editadas, descubrir las categorías reales del fotógrafo. Dos opciones a
  evaluar:
  - **Zero-shot CLIP**: comparar contra un set de prompts ("atardecer",
    "retrato interior", "grupal", "detalle anillos/ramo", "ceremonia", …).
  - **Clustering** (k-means/HDBSCAN) de embeddings + etiqueta representativa.
- Salida: `scene_category` por foto, persistida junto al análisis. Reusable por
  J y K.

**Riesgo**: categorías inestables. Mitigación: empezar con zero-shot (etiquetas
legibles y controlables), medir contra una muestra revisada a ojo.

**Tests**: `test_scene_grouping.py` — set sintético de embeddings agrupables cae
en las categorías esperadas; foto sin escena clara → categoría "otros".

---

## Fase J — Estilo de revelado por escena

**Problema**: la pre-edición aplica un sesgo fijo de exposición/WB; no refleja
la mano del fotógrafo ni cambia por tipo de foto.

**Diseño**:
- `backend/services/develop_style.py` (nuevo): a partir de los registros de
  revelado de la Fase H, agrupados por `scene_category` (Fase I), aprender la
  **receta por escena** (medianas robustas / regresión ligera de exposición, WB,
  contraste, sombras, altas luces). **Winsorizar/descartar** exposición >~1 EV.
- Integrar en `pre_edit.compute_pre_edits`: si hay receta fiable para la escena
  de la foto, usarla como sesgo; si no, caer en el comportamiento actual.
- Métrica honesta: error de la receta en validación cruzada por escena, visible
  en la UI (como el "aprendido" de calibración).

**Dependencias**: H (datos de revelado), I (escena).

**Tests**: `test_develop_style.py` — recetas separadas por escena; winsorización
de extremos; fallback a sesgo fijo sin datos suficientes.

---

## Fase K — Recorte aprendido

**Problema**: el auto-crop usa reglas fijas; no aprende cómo encuadra el
fotógrafo respecto a las personas ni por tipo de escena.

**Diseño**:
- Del XMP/catálogo se saca el recorte real (Crop* + ángulo). De la imagen
  original, `person_detector` + rostros dan la geometría del sujeto.
- `backend/services/crop_style.py` (nuevo): traducir cada recorte a
  **descriptores relativos** — relación de aspecto, headroom sobre la cabeza,
  márgenes laterales, posición del horizonte (¿tercio?), caída de rostros sobre
  tercios, ángulo de enderezado. Aprender sus distribuciones por escena.
- **Distinguir reencuadre de cambio de aspecto**: un crop que solo cambia la
  relación (p.ej. a 4:5) no es decisión de composición → filtrar o pesar aparte.
- Integrar en `auto_crop.propose_crop`: usar las tendencias aprendidas en vez de
  (o además de) las reglas actuales. Empezar por lo más aprendible: aspecto,
  horizonte y headroom.
- **Polígono de personas** (opcional, futuro): hoy `person_detector` da cajas,
  suficientes para encuadre. Siluetas reales necesitarían un modelo de
  segmentación aparte — no bloquea esta fase.

**Dependencias**: H (recortes), I (escena), análisis de imagen (cajas de
persona/rostro). Más difícil que J: es geométrico y pide más ejemplos por escena.

**Tests**: `test_crop_style.py` — descriptores relativos correctos dado
sujeto+recorte sintéticos; separación reencuadre vs cambio de aspecto; fallback
a reglas fijas sin datos.

---

## Fase L — Reconocimiento de personas (ArcFace)

**Problema**: el sistema no sabe *quién* está en cada foto. Eso impide
garantizar "al menos una buena de cada persona" y aprender el mejor ángulo de
alguien en particular.

**Diseño**:
- `backend/models/arcface_r50.onnx` (nuevo, ~90-170 MB): modelo de embeddings de
  identidad facial (512-d). Degradación como CLIP: si no está, la función se
  desactiva sin romper nada.
- `backend/services/face_identity.py` (nuevo):
  - Alinear cada rostro (usar landmarks de ojos de MediaPipe → warp a 112×112,
    el input estándar de ArcFace) y embeber. Reusa el pipeline de recorte de
    cara y el caché en disco (como `face_embedding`).
  - Agrupar por identidad dentro del evento por similitud coseno (umbral
    calibrable). Opcional: galería persistente para reconocer a la misma persona
    entre eventos (novia recurrente, familia).
- Usos que habilita (una vez agrupado):
  - **Cobertura**: en la decisión, garantizar que cada identidad tenga al menos
    una foto seleccionada de calidad (evita dejar a alguien fuera).
  - **Gusto por persona** (futuro): el mejor ángulo/expresión de una identidad,
    condicionando el score.
- Integrar la cobertura en `decision.apply_decision_logic` como una garantía
  suave (no baja la calidad, solo evita omitir personas).

**Riesgo**: costo por rostro (embedding + alineación) y falsos agrupamientos.
Mitigación: solo sobre rostros válidos (MediaPipe) y de tamaño mínimo; umbral de
identidad conservador; corre en el análisis, cacheado.

**Tests**: `test_face_identity.py` — misma persona (crops distintos) agrupa;
personas distintas no; sin modelo → no-op. `test_cobertura.py` — un evento con N
identidades selecciona al menos una por identidad.

---

## Verdad honesta / riesgos transversales

- **Sin metadata no hay señal**: eventos sin catálogo ni XMP no enseñan nada.
  El catálogo cubre el hueco de los XMP no escritos.
- **Deriva de gusto (2 años)**: pesar más lo reciente; permitir elegir eventos.
- **Cómputo**: H2, J, K y L necesitan analizar imágenes reales (embeddings /
  geometría). Es un lote acotado a las ~18k seleccionadas/revisadas, de una
  noche, no en vivo.
- **Recorte (K) es el más difícil**: geometría, no promedios; empezar por
  aspecto/horizonte/headroom.
- **Leer el catálogo en vivo**: hacerlo solo-lectura e idealmente con Lightroom
  cerrado (WAL). Nunca escribir en el `.lrcat`.

## Recomendación de ejecución

Si se hace la cadena de más valor con menos esfuerzo: **H1 → I → J**
(revelado por escena, dato completo, poco cómputo). **H2** (gusto del historial)
en el mismo barrido nocturno. **L (ArcFace)** como pista paralela de alto valor
(abre "una buena de cada persona"). **K (recorte)** al final, cuando el análisis
de imagen del resto ya esté rodando.
