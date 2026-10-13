# Guto Flow — Historia y Evolución del Proyecto

Documento histórico que registra el origen, las decisiones arquitectónicas y la evolución de **Guto Flow** desde su primer script de línea de comandos hasta el ecosistema actual **Digital Darkroom**.

---

## 1. Los Orígenes (Junio 2026)

### Etapa 0 — `Photo Selector` (`photoselect` CLI)
* **Fecha:** 26–27 de Junio de 2026
* **Ubicación original:** `Documents\Claude Code\Photo Selector`
* **Cómo comenzó:** Un paquete de línea de comandos en Python (`photoselect`) diseñado para automatizar el descarte fotográfico de eventos (inicialmente calibrado con el preset `eventos-escolares.yaml`).
* **Stack inicial:**
  * Detección de rostros ligera con **YuNet** (`face_detection_yunet_2023mar.onnx`).
  * Apertura de ojos con **OCEC** (`ocec_s.onnx`) y sonrisas con `hsc_s_48x48.onnx`.
  * Agrupamiento básico por `pHash` y escritura inicial de sidecars `.xmp`.
* **Limitación que motivó el cambio:** El análisis sobre miniaturas pequeñas (224px) perdía nitidez real en retratos grupales y carecía de interfaz visual para auditar decisiones o entrenar el gusto del fotógrafo.

### Etapa 1 — Boceto GUI (`ai_culling_system` v0.1)
* **Fecha:** 27 de Junio de 2026
* **Ubicación original:** `.gemini\ai_culling_system` → migrado a `teamwork_projects\ai_culling_system`
* **Salto arquitectónico:** Creación de la arquitectura dual **Electron + React (Vite)** en el frontend y **FastAPI (Python)** en el backend, permitiendo previsualización rápida e inspección interactiva.

---

## 2. Crecimiento Versión a Versión

### v0.1.0 a v0.8.0 — Construcción de los Cimientos
* **v0.1.0 (Initial MVP):** Ingesta de carpetas, lectura EXIF, cálculo de nitidez Laplaciana y exportación de estrellas a XMP.
* **v0.2.0 – v0.3.0 (Pipeline de Pre-edición Real):** Medición de luminancia en piel y escena global (`pre_edit.py`), estimación de balance de blancos (WB) y rescate tonal automático de altas luces y sombras.
* **v0.4.0 (Atributos Faciales & Ranking Visual):** Evaluación de nitidez localizada en el rostro para no penalizar el bokeh artístico ($f/1.4 - f/1.8$) mediante árbitro **CPBD** (Cumulative Probability of Blur Detection).
* **v0.5.0 (UX: Modo Duelo & Settings):** Comparación lado a lado (1v1) para desempate humano rápido y configuración dinámica de mapeo de estrellas/colores compatible con etiquetas en español e inglés de Lightroom.
* **v0.6.0 (Production Hardening):** Escritura atómica XMP con reintentos anti-bloqueo SMB/NAS y soporte nativo de **XMP embebido en segmento APP1 para JPEGs** (sin depender de ExifTool).
* **v0.7.0 (Búsqueda Semántica Offline & Storyline):** Integración de embeddings visuales para buscar fotos por texto/concepto sin internet y primera versión de línea de tiempo del evento.
* **v0.8.0 (Packaging & Model Downloader):** Asistente de primera ejecución para descarga verificada de pesos ONNX y empaquetado autónomo.

---

### v1.0.0 a v1.5.0 — Aprendizaje Activo y Sincronización con Lightroom
* **v1.0.0 – v1.1.0:** Motor de aprendizaje incremental (`TasteModel`). Guto Flow lee los cambios que el fotógrafo hace en Lightroom (`/reimport_xmp`) o en los Duelos y ajusta sus pesos de selección al estilo personal del autor.
* **v1.2.0 – v1.3.0:** Auto-Crop inteligente con detección de horizonte y aprendizaje del encuadre preferido del usuario (`crop_style.py`).
* **v1.5.0:** Calibración de selectividad contra historial real de catálogos `.lrcat` de Lightroom (lector SQLite solo-lectura `lr_catalog.py`), evitando sobre-selección y ajustando la agresividad del pre-revelado.

---

### v2.0.0 — Migración a UniFace y Arquitectura Limpia
* **Por qué cambiamos MediaPipe / YuNet por UniFace (SCRFD + ArcFace):**
  * Los detectores ligeros fallaban en rostros de perfil, contraluces o grupos grandes.
  * **UniFace** unificó detección de alta precisión, landmarks oculares y embeddings de identidad **ArcFace** en un solo paso vectorizado.
* **Garantía de Cobertura VIP e Invitados:** Agrupación de identidades faciales en todo el evento para asegurar que ningún protagonista o invitado recurrente quede fuera de la selección final.
* **Streaming SSE:** Progreso en tiempo real fase por fase hacia la UI sin bloqueos.

---

### v2.1.0 a v2.2.0 — Motor de Selección V2 y Flujo de Cliente
* **Soporte Dual RAW + JPEG:** Emparejamiento automático de archivos cámara; lo decidido sobre el JPEG o RAW se replica en ambos.
* **Herramientas de Cliente y Metadatos:**
  * Importación directa de selección del cliente (`/tools/import-selection`).
  * Inyección por lotes de Copyright, créditos y taxonomía GPS de ciudades de Ecuador (`metadata_manager.py`).
* **Selectividad Estructurada:** Niveles precisos (30% / 40% / 50%) con protección estricta de ganadores de ráfaga, singletons y protagonistas VIP.

---

### v2.3.0 — Aceleración en Rust, Storyline 2.0 y Digital Darkroom UI
* **Motor Nativo en Rust:** Extracción ultrarrápida de *MakerNotes* y `Burst ID` nativo de fabricante (Canon, Sony, Nikon, Fuji) + detección de disparos fallidos de flash (*Flash Misfire*).
* **Storyline 2.0:**
  * Segmentación semántico-temporal calibrada para eventos largos (`HARD_GAP=15m`, `SOFT_GAP=5m`).
  * Extracción inteligente de capítulo **B-Roll / Detalles** con guardia (`BROLL_MIN_MAIN_PHOTOS=8`) para nunca vaciar momentos cortos.
* **Rediseño "Digital Darkroom":** Interfaz profesional de cuarto oscuro (`#08090C` / `#0D0F14`, acento ámbar `#E9A04A`, tipografía técnica monoespaciada, atajos de teclado `1–4`, Inspector de 320px).

---

### v2.3.1 (Octubre 2026) — Protección Lightroom, Sesiones Monocromáticas y Recomendador B&N
* **Unificación en Proyecto Maestro:** Consolidación definitiva en `C:\Users\Guill\Documents\GUTOFLOW`.
* **Merge No-Destructivo (`Guto ∪ Cliente`):** Al importar la lista del cliente, sus fotos se suman (4★/Red/Pick) sin degradar ni borrar ninguna foto previamente elegida por Guto Flow, incluyendo búsqueda recursiva (`rglob`) si alguna foto del cliente estaba fuera del snapshot.
* **Protección de Revelado Manual de Lightroom (`has_lightroom_edits` + `patch_xmp_metadata`):** Si una foto ya fue editada en Lightroom, Guto Flow actualiza solo estrellas/color/bandera in-place y jamás sobreescribe los nodos `crs:*` (exposición, curvas, WB o máscaras).
* **Soporte de Sesiones Monocromáticas (Rojo sobre Rojo) y B&N:**
  * Preservación del 100% del gradiente en el canal dominante para evitar falsos descartes por desenfoque en escenas de un solo color.
  * Aislamiento de clusters por número de rostros (retratos individuales vs. parejas nunca se colapsan como duplicados).
  * Nuevo módulo `bw_recommender.py` e insignia **B&N** en UI para detectar fotos con canal saturado recuperable en monocromo o alto contraste de claroscuro (velas/contraluz).

---

## 3. Hoja de Ruta Futura (v2.4+ — Linux & LightCraft)
* Empaquetado nativo Linux (`.AppImage` / `.deb`) con aceleración directa ONNX Runtime + CUDA/TensorRT.
* Conector directo e integración vía **MCP** con **LightCraft** (revelador RAW Open Source en Rust de 32-bit float y color OkLCh) para independizar el flujo de trabajo de Adobe.
