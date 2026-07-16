# Plan de implementación: pre-edición (Fase 6)

**Spec**: `docs/superpowers/specs/2026-07-15-pre-edicion-design.md`

## Paso 1 — Preset manager (`backend/services/preset_manager.py`)

- `load_preset(path) -> PresetData`: parsea el .xmp (atributos del
  rdf:Description + elementos hijos crs), separa:
  - `settings`: dict de campos a fusionar (tras lista negra del spec).
  - `elements`: subárboles XML a copiar (ToneCurvePV2012*, PointColors,
    ColorVariance, MaskGroupBasedCorrections, Look si hubiera).
  - `wb_bias`: (IncrementalTemperature, IncrementalTint) extraídos.
- `register_recent(path)`: copia a `backend/models/presets/`, actualiza
  settings.recent_presets (máx 5, MRU).
- Tests con el formato real (fixture reducida del GutoPro Day).

## Paso 2 — Estimadores (`backend/services/pre_edit.py`, geometría/color puro)

- `estimate_exposure(img_rgb, face_bboxes) -> float` (stops, sin bias):
  piel (región central de bboxes, mediana entre caras) o mediana global;
  sRGB→lineal; constantes `TARGET_SKIN=0.42`, `TARGET_MID=0.18`,
  `MAX_EXPOSURE=1.5`.
- `estimate_wb(img_rgb, face_bboxes) -> tuple[float, float] | None`:
  piel (con caras) o blancos (top luminancia, baja saturación); dominante →
  (temp_inc, tint_inc), `MAX_WB=15`.
- `segment_light_sessions(signatures ordenadas) -> list[list[int]]`:
  histéresis `BREAK_RUN=4`, `SESSION_BREAK_DELTA`, rechazo outliers MAD,
  sesión mínima 5 → hereda vecina.
- `compute_pre_edits(all_photos_data, bias) -> dict[idx, {exposure, temp,
  tint}]`: sesiones + medianas + clamps (±0.7 EV vs sesión).
- Tests: los del spec (escenario 50 fotos/6 grupos, cortes, clamps, signos).

## Paso 3 — XMP y pipeline

- `xmp_exporter._build_xmp_packet(..., develop: dict | None)`: fusiona
  `preset settings/elements` + `Exposure2012` + `IncrementalTemperature/Tint`
  (omitir WB si el archivo es RAW). Mantener compat: sin develop → paquete
  actual.
- `main.py` FASE 4.6 (tras crop, antes del export): si `pre_edit.enabled`,
  calcular firmas para todas las fotos (reutiliza thumb_ai y bboxes),
  sesiones, y adjuntar `result["develop"]` a las selected. RAW hermano:
  mismo develop sin WB.
- Snapshot: guardar develop junto a crop para re-export en duelos.
- Settings: defaults nuevos en settings_manager.

## Paso 4 — Endpoints y UI

- `GET /presets`, `POST /presets/use {path}` (valida + registra MRU).
- SettingsModal sección "Pre-edición": toggle, drag&drop + buscar (input
  file), dropdown recientes, slider bias, nota máscaras IA.
- Electron: permitir file dialog (IPC ya existente o input type=file).

## Paso 5 — Verificación de campo

- Re-correr culling en evento de prueba, validar en LR: look del preset,
  uniformidad WB por bloque, pieles a +0.3, RAW sin WB roto.
- Calibrar `TARGET_SKIN` y `SESSION_BREAK_DELTA` con feedback del usuario.

## Riesgos

- Máscaras IA del preset pueden pedir recomputo en LR (limitación Adobe,
  documentada en UI).
- Piel no caucásica/iluminación de color (pista de baile): el target de piel
  es luminancia (no tono), robusto a etnia; luces de fiesta saturadas pueden
  sesgar WB → el consenso de sesión mitiga.
- Tamaño del paquete APP1 (JPEG) con preset grande: verificar < 64 KB
  (GutoPro Day ≈ 15 KB, holgado).
