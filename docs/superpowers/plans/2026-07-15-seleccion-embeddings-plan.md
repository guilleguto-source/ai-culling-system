# Plan de implementación: gates técnicos + embeddings + sync Lightroom

**Spec**: `docs/superpowers/specs/2026-07-15-seleccion-embeddings-design.md`

Orden pensado para que cada fase deje el sistema funcionando (degradación
incluida desde el inicio). Cada fase termina con sus tests en verde.

---

## Fase 1 — Gates técnicos (solo backend, sin dependencias nuevas)

**1.1** `backend/services/face_assessment.py`
- Añadir `compute_face_sharpness(img_rgb, face_bboxes) -> list[float]`:
  varianza del Laplaciano por crop de cara (gris, crop con margen 10%).
- Extender `FaceAssessmentResult` con `sharpness: float`.

**1.2** `backend/services/cluster_gates.py` (nuevo)
- `apply_technical_gates(cluster: list[record]) -> list[record]`:
  - Regla ojos: si ≥1 foto del cluster tiene todos los ojos abiertos,
    descartar las que tienen ojos cerrados.
  - Regla nitidez: si ≥1 foto tiene todas sus caras con sharpness ≥ umbral
    relativo (mediana del cluster × 0.5), descartar las que no.
  - Nunca devolver lista vacía (si todo se descarta → devolver cluster entero).

**1.3** Integrar en `main.py`: elegir representative entre supervivientes de
los gates (heurísticas actuales como scorer, sin cambios aún).

**Tests**: fixtures sintéticas (blur gaussiano sobre crop de cara), cluster
todo-defectuoso → nada descartado.

---

## Fase 2 — Embedding service

**2.1** `backend/services/embedding_service.py` (nuevo)
- Carga perezosa de `backend/models/clip_vit_b32_visual.onnx` con onnxruntime.
- `is_available() -> bool`; `embed(img_rgb) -> np.ndarray | None`
  (preproceso CLIP estándar 224×224, salida 512-d L2-normalizada, float32).
- Caché disco: `backend/models/emb_cache/` — archivo `.npy` por hash de
  `(path, mtime)`; `embed_path(path, img_rgb)` consulta caché primero.

**2.2** `backend/models/README.md`: instrucciones de descarga del ONNX
(fuente y nombre de archivo exactos).

**2.3** Ingesta: en `main.py` (post-clustering), embeber solo fotos que
pertenecen a clusters >1 (donde se rankea) para acotar coste; si
`is_available()` es False → skip con WARNING.

**Tests**: smoke (shape, norma, determinismo, caché hit), sin ONNX → None
sin excepción.

---

## Fase 3 — Taste model sobre embeddings

**3.1** `backend/services/taste_store.py` (nuevo)
- SQLite `backend/models/taste_examples.db`, esquema del spec.
- `add_example(embedding, label, source, event_dir)`, `load_examples()`
  (filtra por `embedding_dim`/`model_version` compatibles), recuperación de
  DB corrupta (rename `.bak` + recrear).

**3.2** Reescribir `taste_model.py` conservando interfaz pública
(`is_trained`, `learn_preference`, `predict_score`):
- `is_trained` = nº ejemplos compatibles ≥ 50.
- `learn_preference(winner_emb, loser_emb, source, event_dir)` → 2 ejemplos
  (+1/−1) + re-fit LogisticRegression.
- `predict_score(embedding) -> float` = predict_proba.
- Fallback frío: `main.py` usa heurísticas + desempate por ratio de ojos
  abiertos cuando `not is_trained`.
- Ignorar `user_taste_model.pkl` legado.

**3.3** `main.py` `/learn_preference`: pasar embeddings (desde caché) en lugar
de las 3 features; mantener re-export XMP inmediato.

**Tests**: 50 ejemplos sintéticos separables → is_trained y score ordena bien;
ejemplos de dim incompatible excluidos; DB corrupta recuperada.

---

## Fase 4 — Sync Lightroom

**4.1** `backend/services/xmp_reader.py` (nuevo)
- Leer label desde sidecar `.xmp` (RAW) y APP1 embebido (JPEG).
- `read_current_labels(directory) -> dict[path, label]`.

**4.2** `main.py` `POST /reimport_xmp {directory}`
- Cargar resultados del último run del directorio (persistir el export
  original si aún no se guarda), comparar label actual vs exportado usando
  `ratings_mapping` (orden de categorías define subir/bajar).
- Subió → +1, bajó → −1 (embedding desde caché; si no hay, re-embeber).
- Respuesta: `{corrections: n, upgraded: x, downgraded: y}`.

**4.3** UI: botón "Sincronizar desde Lightroom" (vista de resultados) →
llama endpoint y muestra conteo.

**Tests**: sidecars fixture con labels modificados → signos correctos;
directorio sin XMPs → 0 correcciones sin error.

---

## Riesgos

- **Export original no persistido**: hoy el resultado vive en memoria/UI.
  Fase 4 exige persistir el mapeo exportado (JSON junto al directorio o en
  backend/models/). Resolver en 4.2.
- **Coste de embeber en re-import**: mitigado por caché de Fase 2.
- **Umbral relativo de nitidez (×0.5 mediana)**: calibrar con fotos reales
  del usuario en la primera prueba de campo; dejar constante nombrada.
