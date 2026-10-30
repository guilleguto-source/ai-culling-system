# Plan de Implementación: Fusión Integral URE Mesh + Correcciones de Auditoría (Code Review)

## Resumen del Plan
Unificación definitiva en el código de producción de Guto Flow 3:
1. **Auditoría (Code Review):**
   - [x] Limpieza de representante previo en `rep_scores` en desempate VLM diferido (`backend/routers/culling.py`).
   - [x] Propagación de `face_bboxes`, `face_regions` y dimensiones en `backend/services/decision.py`.
   - [x] Corrección de memory leak C++ y restauración de `TARGET_SIZE=512` en `backend/services/mask_generator.py`.
   - [x] Sincronización de etiquetas en `src/renderer/src/components/GridView.tsx`.
   - [x] Imports tipados en `src/renderer/src/api/client.ts`.
   - [x] Erradicación de bare excepts en `backend/scripts/vlm_stream_runner.py`.
2. **URE Mesh:**
   - [x] Pre-revelado adaptativo con sesgo `+0.28 EV` en `backend/services/pre_edit.py`.
   - [x] Preset de estilo `GutoPro Day Boy` al 100% de fuerza.
   - [x] Smart Crop 3:2 / 2:3 con filtro YCrCb y Straighten $\theta \le 6.0^\circ$ en `backend/services/auto_crop.py` y `straighten.py`.
   - [x] Inyección de directivas XMP de máscaras IA (`crs:MaskGroupBasedCorrections`: Piel Facial con textura intacta) para Lightroom Classic.

---

## Archivos Modificados
- `backend/routers/culling.py`
- `backend/routers/advanced.py`
- `backend/services/pre_edit.py`
- `backend/services/decision.py`
- `backend/services/auto_crop.py`
- `backend/services/straighten.py` (nuevo servicio URE Mesh)
- `backend/services/mask_generator.py`
- `backend/scripts/vlm_stream_runner.py`
- `src/renderer/src/api/client.ts`
- `src/renderer/src/components/GridView.tsx`

---

## Checklist de Verificación
- [x] Desempate VLM diferido no deja huérfanos en `rep_scores`.
- [x] `face_bboxes` y `face_regions` inyectados en `results` por `decision.py`.
- [x] Retoque de piel en `AdvancedPanel` procesa con éxito fotos con rostros ($N > 0$) e inyecta máscaras anatómicas en XMP.
- [x] Máscaras de Piel Facial con textura intacta escritas en `.xmp` para Lightroom.
- [x] Pre-revelado con sesgo `+0.28 EV` aplicado.
- [x] Preset al 100% sin atenuación.
- [x] Smart Crop (3:2 / 2:3) y enderezado angular $\le 6^\circ$ operativos.
- [x] `mask_generator.py` libera memoria C++ y re-exporta `TARGET_SIZE`.
- [x] Filtros de GridView (`highlighted`, `duplicate`, `trash`, `doubtful`) y cliente API tipados.
