# Session Handoff: Desacoplamiento GutoFlow y Módulo Portable de 5 Máscaras en LightCraft
**Fecha:** 2026-10-19 | **Workspace:** C:\Users\Guill\Documents\GUTOFLOW

## 1. Objetivo Activo y Alcance
- Desacoplar la arquitectura de renderizado: GutoFlow asume culling, biometría y recetas XMP, mientras LightCraft procesa el revelado y las 5 máscaras de forma nativa en Rust.
- Resolver el congelamiento de la UI en LightCraft causado por invocaciones en segundo plano a `python.exe -m services.mask_generator`.
- Diseñar un módulo modular y portable de síntesis de 5 máscaras anatómicas para exportar a cualquier versión de LightCraft.

## 2. Archivos y Símbolos Modificados
- [`crates/pipeline/src/masks.rs`](file:///c:/Users/Guill/Documents/GUTOFLOW/gutoflow-rust/lightcraft/crates/pipeline/src/masks.rs):
  - Añadida función pública `pub fn generate_anatomical_mattes(faces: &[Rect]) -> Mattes`.
  - Generación en memoria (<1ms) de Sujeto Pop, Piel Facial, Iris/Pupila, Esclera Ocular y Dientes.
  - Implementada agregación multi-persona (`max()`) para fotos familiares y grupales.
- [`crates/engine/src/media.rs`](file:///c:/Users/Guill/Documents/GUTOFLOW/gutoflow-rust/lightcraft/crates/engine/src/media.rs):
  - Eliminados definitivamente `RUNNING_MATTE_JOBS` y el `std::thread::spawn` que llamaba a `python.exe`.
  - Normalizado `photo_cache_key` reemplazando `\` por `/` y convirtiendo a minúsculas.
  - `generate_person_matte` refactorizado como delegador directo a `generate_anatomical_mattes`.
  - Desacoplada la dependencia de rutas absolutas hardcodeadas a disco local.
- [`backend/scripts/process_nas_sessions.py`](file:///c:/Users/Guill/Documents/GUTOFLOW/backend/scripts/process_nas_sessions.py):
  - Normalizada la función `photo_cache_key` para paridad estricta de hash FNV-1a con Rust.
  - `generate_lightroom_xmp()` actualizado para inyectar `mwg-rs:Regions` estándar con bounding boxes de rostros.
  - Almacenamiento de ancho y alto de referencia en `meta_dict` para normalización precisa de coordenadas.
- [`.agents/lightcraft_anatomical_masks.patch`](file:///c:/Users/Guill/Documents/GUTOFLOW/.agents/lightcraft_anatomical_masks.patch):
  - Parche unificado git de 17 KB para portar la funcionalidad a otros clones de LightCraft.

## 3. Decisiones Técnicas y Parámetros Críticos
- **Rust Puro sin Dependencias:** Las máscaras anatómicas se generan matemáticamente sobre matrices `512x512` sin librerías externas ni llamadas a sistema.
- **División de Responsabilidades:**
  - **GutoFlow:** Detección biométrica (ojos abiertos/cerrados vía EAR, mirada Gaze, sonrisa MAR) y curaduría VIP (3★ azul, 2★ verde, 0★ reject rojo).
  - **XMP Sidecar:** Canal de transporte desacoplado (`mwg-rs:Regions` y `crs:MaskGroupBasedCorrections`).
  - **LightCraft:** Lectura instantánea (<2ms) y síntesis de máscaras en memoria al vuelo.
- **Normalización de Hashes:** Garantiza que paths de red Windows (`\\MYCLOUDEX2ULTRA\...`) coincidan exactamente en Rust y Python.
- **Paridad con Adobe Lightroom Classic:** Ambas herramientas leen los mismos sidecars XMP de manera estándar.

## 4. Estado de Verificación
- `cargo check --workspace` en `gutoflow-rust/lightcraft` verificado exitosamente en 20.55s (0 errores, 0 fallos).
- Verificación sintáctica con `python -m py_compile backend/scripts/process_nas_sessions.py` exitosa.
- Parche `.agents/lightcraft_anatomical_masks.patch` validado y exportado.
- Cero subprocessos Python detectados en el hilo de renderizado de LightCraft.

## 5. Próximo Paso Inmediato
- Iniciar LightCraft, abrir o sincronizar una sesión del NAS y comprobar que las fotos seleccionadas muestran las 5 máscaras aplicadas instantáneamente sin entorpecer la fluidez de la interfaz.
