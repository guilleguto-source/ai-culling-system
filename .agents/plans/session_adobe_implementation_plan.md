# Plan Específico de Sesión: Implementación Adobe en LightCraft y GutoFlow
> Fecha: 2026-10-27 | Estado: Pendiente de Ejecución (Pausado para Investigación)
> Contexto: Resultados de Ingeniería Inversa en Photoshop 2026 y Lightroom Classic 14.x

---

## 1. Resumen de Objetivos
Trasladar los algoritmos y esquemas extraídos a los 4 puntos de integración directa:

1. **Punto 3 (XMP Exporter):** Actualizar `backend/services/xmp_exporter.py` para inyectar `crs:Recompute="true"`, `crs:MaskSubType="fMaskSemanticLabel"` y las 11 etiquetas oficiales (`FaceSkin`, `IrisAndPupil`, etc.).
2. **Punto 1 (Guided Filter):** Implementar el compute shader `gutoflow-rust/lightcraft/crates/gpu/src/wgsl/guided_filter.wgsl` con aceleración piramidal ($s=4$, box filter y regularización $\epsilon=10^{-4}$).
3. **Punto 2 (Malla Facial 7 Zonas):** Crear `gutoflow-rust/lightcraft/crates/raster/src/face_mesh.rs` con el modelo anatómico de `CLFaceEditor.cpp` para alimentar `liquify_warp.wgsl`.
4. **Punto 4 (API Culling):** Crear `backend/routers/culling.py` para exponer análisis en batch y consultas reactivas por sliders vía SQLite.

---

## 2. Checklist Técnico para Reanudar
- [ ] **Paso 1:** Modificar `backend/services/xmp_exporter.py` (Líneas 255-299) con la sintaxis verificada de `CameraRaw.8bi`.
- [ ] **Paso 2:** Crear `guided_filter.wgsl` en `crates/gpu/src/wgsl/`.
- [ ] **Paso 3:** Crear `face_mesh.rs` en `crates/raster/src/` y enlazar en `lib.rs`.
- [ ] **Paso 4:** Crear `backend/routers/culling.py` y registrar en `backend/main.py`.
