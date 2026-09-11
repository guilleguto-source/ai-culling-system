# Changelog

Todos los cambios notables en **Guto Flow** están documentados en este archivo.
El formato está basado en [Keep a Changelog](https://keepachangelog.com/es-ES/1.0.0/) y este proyecto se adhiere a [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [2.1.0] - 2026-09-11

### 🚀 Novedades y Mejoras
- **Motor de Selección V2:** Supervivencia obligatoria, control de pacing, recorte a objetivo (`trim to target`) y bonificación de puntuación VIP (+20%).
- **Tratamiento Unificado RAW + JPEG:** Agrupación transparente por stem en estimación, selección y exportación dual de sidecars XMP.
- **Herramientas de Cliente y UI:** Modales interactivos (`ClientToolsModal`, `PreCullingModal`, `SleepCountdownModal`), barra VIP (`VIPBar`) y mejoras visuales en biblioteca.
- **Detección y Filtros Robustos:** Adapters para motor facial, perfiles de hardware, filtros de discrepancias y persistencia histórica de sesión.
- **Historial y Benchmarks de Culling Agent:** Integración de reportes de auditoría, planes de migración y suite de scripts de validación en `docs/culling_agent/` y `scripts/scratch/`.

---

## [2.0.0] - 2026-08-25

### 🚀 Novedades y Re-arquitectura
- **Migración Integral a UniFace:** Reemplazo de MediaPipe e InsightFace por un pipeline unificado de detección facial y embeddings (SCRFD + ArcFace) con alto rendimiento en CPU/GPU.
- **Búsqueda Semántica con SigLIP:** Migración desde CLIP a modelos SigLIP optimizados para mayor fidelidad semántica en imágenes de alta resolución.
- **Lazy Loading de Modelos IA:** Carga bajo demanda y patrón Singleton para modelos ONNX (`FaceAnalyzer`, `MobileGaze`), reduciendo el cold start del backend en 2–4 segundos.
- **Optimización de 5 Pasos:**
  - Erradicación de todas las URLs hardcodeadas (`127.0.0.1:8000`) en el frontend, centralizando 100% de la capa de red en `apiClient`.
  - Eliminación de dependencias obsoletas (`mediapipe` en `requirements.txt`) reduciendo ~200MB de footprint.
  - Purgado de código muerto: canales IPC en desuso (`backend:undo:*`), vistas huérfanas y métodos sin consumidor.
  - Aislamiento de módulos legacy en `backend/services/legacy/`.
  - Suite de pruebas automatizadas actualizada a 325 tests pasando (0 fallos).

---

## [1.3.0] - 2026-08-08

### ✨ Características
- **Storyline 2.0 Foundation:** Segmentación semántico-temporal automática para estructurar eventos fotográficos por bloques de tiempo y escenas.
- **Event Library & Autocompletado:** Biblioteca de eventos para categorizar y buscar momentos clave de una sesión.
- **Selección Múltiple en Grid:** Soporte completo de selección de fotos en cuadrícula usando combinaciones `Shift + Click`, `Ctrl + Click` y atajo global `Ctrl + A`.
- **Streaming de Progreso en Tiempo Real:** Integración de Server-Sent Events (SSE) en el backend para reportar el avance granular de cada fase del pipeline.
- **Reglas de Ráfagas Mejoradas:** Control de orientación horizontal/vertical (H/V) y selección de máximo 2 fotos representativas por ráfaga.

---

## [1.2.0] - 2026-07-27

### ✨ Características
- **Búsqueda Semántica Offline:** Capacidad de buscar fotografías mediante lenguaje natural (ej. *"abrazo de los novios"*, *"pastel de cumpleaños"*) sin conexión a internet.
- **Refinamiento VLM (Visual Language Model):** Desempate de expresiones complejas y sonrisas usando modelos de visión avanzada.
- **Wizard de Descarga de Modelos:** Asistente interactivo en el frontend para descargar y verificar los pesos de IA requeridos.
- **Inspector de Fotos y Lupa:** Panel lateral con datos EXIF avanzados, histograma y herramienta de zoom/lupa de alta definición.
- **Empaquetado de Producción:** Pipeline de distribución reproducible combinando PyInstaller para el backend y Electron Builder para el instalador nativo de Windows.

---

## [1.1.0] - 2026-07-20

### ✨ Características
- **Aprendizaje Continuo desde Lightroom:** Sincronización bidireccional mediante reimportación XMP para aprender el criterio de selección, revelado y recorte del fotógrafo.
- **Reconocimiento y Cobertura de Personas:** Detección de identidades y garantía de cobertura mínima de personas relevantes en el evento.
- **Calibración Facial:** Clasificador aprendido sobre atributos faciales (ojos cerrados, dirección de mirada, sonrisas) relativo a la ganadora de la ráfaga.
- **Modo Duelo (Duel View):** Comparador lado a lado para desempatar manualmente ráfagas dudosas con atajos rápidos de teclado.
- **Soporte de Deshacer (Undo Export):** Capacidad de revertir calificaciones y metadatos XMP aplicados a disco.

---

## [1.0.0] - 2026-07-16

### 🚀 Lanzamiento Inicial (MVP)
- **Motor de Culling Inteligente:** Detección de nitidez (blur score), análisis de ojos cerrados y clustering por similitud temporal/visual.
- **Integración XMP sin Lightroom Abierto:** Inyección directa de estrellas, colores (Verde, Azul, Rojo) y banderines en metadatos de archivos JPEG y RAW.
- **Pre-Edición Automatizada:** Aplicación de recetas de revelado (.XMP), corrección de balance de blancos por tono de piel y ajuste relativo de exposición.
- **Auto-Encuadre No Destructivo:** Sugerencia de recorte inteligente (Crop) preservando sujetos y rostros mediante metadatos `crs:Crop*`.
- **Interfaz Gráfica Nativa:** Aplicación de escritorio desarrollada con React, TypeScript, Tailwind CSS y Electron.
