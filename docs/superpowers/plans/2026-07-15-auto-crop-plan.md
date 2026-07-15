# Plan de implementación: auto-crop no destructivo (Fase 5)

**Spec**: `docs/superpowers/specs/2026-07-15-auto-crop-design.md`

## Paso 1 — Geometría (`backend/services/auto_crop.py`, sin tocar nada más)

- `CropProposal` dataclass: `left, top, right, bottom` (fracciones 0..1,
  bordes internos) + `angle` (grados) + `reason` (str, para logs/UI).
- `detect_horizon_angle(img_gray) -> float | None`: Canny + HoughLinesP,
  candidatas casi horizontales (|θ|<15°) y largas (≥25% del ancho), mediana
  ponderada por longitud. None si no hay señal.
- `propose_crop(scene_type, face_bboxes, eye_landmarks, saliency_region,
  img_shape, level) -> CropProposal | None`:
  - Constantes nombradas: `LEVEL_LIMITS = {"minimo": .10, "medio": .20,
    "agresivo": .35}`, `MAX_LEVEL_ANGLE = 7.0`, `MAX_ROTATION_CROP = .08`,
    `MIN_CHANGE = .02`, `MIN_ANGLE = 0.5`, `FACE_EDGE_MARGIN = 0.5`,
    `GAZE_AIR_RATIO = 2/3`.
  - Grupos (≥3 caras): solo ángulo (reglas spec). Retrato (1-2): ángulo +
    recomposición tercios/mirada. Detalle: ángulo + saliencia a tercios.
  - Aspect ratio original SIEMPRE; validación de rostros dentro del crop;
    salvaguarda de cambio mínimo.
- Tests (`test_auto_crop.py`): los del spec (geometría + horizonte sintético).

## Paso 2 — XMP con crs:Crop*

- `xmp_exporter.py`: namespace `crs` en NS; `_build_xmp_packet(..., crop=None)`
  añade HasCrop/CropLeft/Top/Right/Bottom/Angle/CropConstrainToWarp;
  `write_xmp(..., crop=None)` lo pasa; `export_results_to_xmp` lee
  `result.get("crop")`.
- Verificar que `xmp_reader` (sync Fase 4) sigue leyendo Rating/Label igual
  con los campos nuevos presentes (test roundtrip).
- Tests en `test_lightroom_sync.py` o nuevo: paquete con crop parsea; sync
  no genera ejemplos por cambios de crop.

## Paso 3 — Pipeline y settings

- `settings_manager`: default `selection_preferences.auto_crop = "minimo"`.
- `main.py` FASE 4: para cada resultado `selected` con `auto_crop != off`,
  llamar `propose_crop` (usa thumb_ai, bboxes, landmarks, saliencia ya
  calculados) y adjuntar `result["crop"]` (dict fracciones) + `has_crop`.
  El RAW hermano hereda el mismo crop.
- Duelos (`/learn_preference`): el re-export del ganador conserva su crop si
  lo tenía (recalcular con los mismos datos no es posible ahí — guardar el
  crop en el snapshot de export y reutilizarlo).

## Paso 4 — UI

- `SettingsModal.tsx`: select "Auto-encuadre" con off/mínimo/medio/agresivo
  (labels en español, default mínimo).
- `GridView.tsx` y `DuelView.tsx`: badge "✂" si `has_crop`.

## Riesgos

- Falsos horizontes en interiores (mesas, marcos): mitigado por exigencia de
  longitud ≥25% del ancho y mediana ponderada; calibrar en primera prueba real.
- Lightroom y orientación EXIF: los crs:Crop* se aplican sobre la imagen ya
  orientada; nuestros bboxes vienen del thumb ya transpuesto (exif_transpose),
  consistente. Verificar con una foto vertical real en la prueba de campo.
