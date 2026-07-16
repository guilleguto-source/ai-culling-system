# Plan de implementación: refactor arquitectónico v2 (Guto Flow)

**Fecha**: 2026-07-16
**Contexto**: mejoras estructurales tras 6 fases de features. El sistema
funciona; esto reduce deuda técnica y habilita re-selección instantánea,
escala a miles de fotos y acelera la calibración.

## Principio de orden

El refactor de datos (Fase A) es el cimiento: habilita persistencia (B),
re-selección instantánea (C) y el visor de depuración (F). Las fases de
limpieza (D) y escala (E) son independientes y de bajo riesgo. Cada fase
deja el sistema funcionando y con sus tests en verde.

Prioridad recomendada: **A → B → C** (la cadena de más valor) y **D** en
paralelo (limpieza segura). E y F cuando se necesiten (escala / calibración).

---

## Fase A — `PhotoAnalysis`: un objeto por foto (cimiento)

**Problema**: el pipeline mantiene ~15 listas paralelas (`scene_types[i]`,
`blur_scores[i]`, `pre_skin[i]`, `pre_wb[i]`, `sharp_anywhere[i]`…)
sincronizadas a mano. Cada métrica nueva toca 3 sitios (incluida la rama de
error) y un descuido las desalinea.

**Diseño**:
- `backend/services/analysis.py` (nuevo): dataclass `PhotoAnalysis` con todos
  los campos por foto (índice, path, scene_type, face_bboxes, eye_landmarks,
  face_sharpness, closed_eyes, saliency, blur_score, blur_flag,
  sharp_anywhere, skin_lum, global_lum, clip_frac, wb_estimate, aesthetic,
  embedding_path, person_bboxes, error).
- `analyze_photo(record, detectors, settings) -> PhotoAnalysis`: una función
  que produce el objeto completo; la rama de error devuelve un
  `PhotoAnalysis` con `error` seteado y defaults (nunca listas fuera de fase).
- `_run_culling_pipeline` pasa a iterar sobre `list[PhotoAnalysis]`; las
  FASES 3c/4 leen `pa.blur_score` en vez de `blur_scores[idx]`.

**Riesgo**: toca todo el pipeline. Mitigación: es mecánico; los 112 tests
actuales cubren el comportamiento observable (labels, XMP, crop, exposición),
así que un refactor correcto los deja intactos.

**Tests**: los existentes deben pasar sin cambios. Añadir
`test_analysis.py`: `analyze_photo` sobre foto sintética con/ sin cara,
rama de error produce objeto válido.

---

## Fase B — Persistencia del análisis por evento

**Problema**: el análisis (95% del tiempo de cómputo) vive solo en RAM.
Re-correr o re-seleccionar re-analiza todo.

**Diseño**:
- `backend/services/analysis_store.py` (nuevo): SQLite
  `backend/models/analysis/<hash-dir>.db`. Una fila por foto con los campos
  escalares de `PhotoAnalysis` (JSON para bboxes/landmarks) keyed por
  `(path, mtime)`.
- Al ingestar: si existe fila con el mtime actual → cargar `PhotoAnalysis`
  desde DB y saltar el análisis. Si no → analizar y persistir.
- El embedding ya tiene su caché `.npy`; la DB guarda solo su clave.
- Versión de esquema: si cambia el set de detectores/umbrales estructurales,
  invalidar (columna `analysis_version`).

**Tests**: `test_analysis_store.py` — roundtrip, hit por mtime, miss por
mtime cambiado, invalidación por versión.

---

## Fase C — Re-selección instantánea (separar analizar de decidir)

**Problema**: cambiar selectividad (few↔moderado) obliga a re-analizar.

**Diseño**:
- Extraer FASE 4 completa (gates → score → selectividad → labels → crop) a
  `backend/services/decision.py`: `decide(analyses, settings) -> results`.
  No decodifica imágenes; opera sobre `PhotoAnalysis` + settings.
- Endpoint `POST /reselect {directory}`: carga análisis desde la DB (Fase B),
  corre `decide` con los settings actuales, re-exporta XMP y snapshot.
  Instantáneo (segundos).
- UI: al cambiar "Selectivity Target" o el nivel de crop en Settings con un
  evento ya analizado, ofrecer "Re-seleccionar" (sin re-analizar).

**Dependencias**: A (objeto) + B (persistencia). El crop necesita el thumb
para la guardia de piel/horizonte → o se cachea el resultado del crop en la
DB (recomendado: el crop es determinista dado el análisis) o `decide` recibe
acceso perezoso al thumb solo para las selected.

**Tests**: `test_reselect.py` — mismo análisis + dos niveles de selectividad
→ distinto nº de selected sin recomputar métricas.

---

## Fase D — Limpieza de código muerto (independiente, bajo riesgo)

- Quitar `expression.onnx` del flujo si no se usa (verificar con grep).
- Quitar `culling_mode` de settings (nunca conectado a lógica).
- Quitar el pickle SGD legado (`user_taste_model.pkl`) y su compat.
- Degradar las heurísticas estéticas a fallback documentado: siguen como
  respaldo cuando no hay taste model, pero dejar claro en comentario que el
  camino principal es el embedding.
- Cada eliminación con su test de no-regresión.

---

## Fase E — Streaming / lotes (escala)

**Problema**: todos los `thumb_ai` (1600px) en RAM no escala a miles de fotos.

**Diseño**:
- Procesar la ingesta+análisis en lotes (p.ej. 200 fotos): analizar lote,
  persistir a la DB (Fase B), liberar los arrays, siguiente lote.
- El clustering y las sesiones de luz necesitan visión global → operan sobre
  los campos escalares ya persistidos, no sobre los pixeles.
- `thumb_ui` (pequeño) sí puede quedar en el caché de thumbnails para la UI.

**Tests**: `test_streaming.py` — evento simulado de N fotos procesado en
lotes produce el mismo resultado que en una pasada.

---

## Fase F — Visor de depuración (acelera calibración)

**Problema**: calibrar (signo de horizonte, target de piel, umbrales) exige
round-trips por Lightroom.

**Diseño**:
- Endpoint `GET /debug/overlay?path=...`: dibuja sobre el thumb las cajas de
  cara/persona, el crop propuesto, la zona de saliencia y anota exposición/WB
  calculados + sesión de luz asignada.
- Vista "Debug" en la UI (toggle) que muestra ese overlay en el grid.

**Dependencias**: A (acceso limpio a los datos por foto).

---

## Acciones de activación (no son código, pero desbloquean valor)

1. **Descargar CLIP** (`clip_vit_b32_visual.onnx`) → activa el aprendizaje de
   gusto que ya alimentan los duelos y el sync de Lightroom.
2. **Parser AFInfo2 de Canon** (posible Fase G): leer el punto de enfoque del
   MakerNote para distinguir error de enfoque de intención, y anclar el crop.
3. **Composición por cuerpo completo**: las cajas YOLO hoy solo protegen;
   podrían encuadrar el cuerpo, no solo la cara (Fase H).

---

## Recomendación de ejecución

Si solo se hace UNA cosa: **Fase C** (re-selección instantánea), que exige A+B
como cimiento. Es el mayor salto de experiencia — probar few/moderado/más sin
esperar 5 minutos cada vez. El resto es higiene técnica valiosa pero no urgente.
