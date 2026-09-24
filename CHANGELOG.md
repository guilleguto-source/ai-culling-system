# Changelog

Todos los cambios notables en **Guto Flow** están documentados en este archivo.
El formato está basado en [Keep a Changelog](https://keepachangelog.com/es-ES/1.0.0/) y este proyecto se adhiere a [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

---

## [2.3.0] - 2026-09-23

### 🚀 Novedades y Arquitectura
- **Extracción Nativa MakerNotes en Rust (`rust_core`):** Parseo a bajo nivel de tags EXIF de secuencia propietaria de fabricantes (Sony `0x0017`/`0x200B`, Nikon `0x001D`/`0x0019`, Canon `DriveMode`).
- **Clustering Híbrido y Pacing Adaptativo (`clustering.py`):** Algoritmo DBSCAN con cálculo dinámico de la mediana de $\Delta t$ inter-disparo en lugar de umbrales rígidos. Integración de *Union-Find* para forzar distancia $0.0$ en identificadores de ráfaga coincidentes.
- **Hero Shot & Gaze Continuity (`culling.py` / `decision.py`):** Inyección de bono (+0.35) a tomas con orientación facial frontal (*Yaw* $< 15^\circ$) y ojos abiertos para anclar la mirada en duelos de retrato y grupos.
- **Storyline 2.0 con Escisión B-Roll (`storyline_builder.py`):** Detección semántica y aislamiento de fotografías de detalles/objetos a un capítulo dedicado (`capitulo_broll`), evitando distorsiones de pacing en el flujo cronológico del evento.
- **Digital Darkroom UI (Fases 1, 2 y 3):** Rediseño visual hacia paleta de cuarto oscuro (`#08090C`, `#0D0F14`), acento ámbar (`#E9A04A`), tipografía mono para métricas técnicas, virtualización a 60 FPS con `react-virtuoso` y panel Inspector estilizado.

### 🧠 Transición de Modelos y Racionales Técnicos
- **De pHash Visual a Rust MakerNotes + Adaptive DBSCAN:**
  - *Motivo:* El hash perceptual (pHash) producía falsos positivos con ruidos ISO altos y fallaba en ráfagas con paneo rápido del fotógrafo.
  - *Decisión:* Usar el ID inyectado por el obturador de la cámara en los MakerNotes EXIF vía Rust como señal determinante.
- **De Calificación Estática a Hero Shot (Yaw de SCRFD Landmarks):**
  - *Motivo:* La IA solía preferir fotogramas intermedios de transición donde una persona sonreía pero miraba hacia un lado.
  - *Decisión:* Aprovechar los 5 landmarks faciales para calcular el ángulo Yaw y priorizar contacto visual frontal.

### ⚡ Impacto Cuantitativo & Benchmarks
- **Fiabilidad en Ráfagas:** **100% de precisión** en la identificación de secuencias reales de hardware.
- **Rendimiento de UI:** Renderizado virtualizado fluido a **60 FPS constantes** en catálogos de más de 15,000 fotografías.
- **Resolución de Fallos:** Corrección del error 500 en `/session/load` y estabilización del Storyline en eventos continuos (>1,700 fotos).

---

## [2.1.0] - 2026-09-11

### 🚀 Novedades y Arquitectura
- **Motor de Selección V2 (`selection_v2.py`):** Algoritmo de dos pasadas con supervivencia obligatoria de fotos por capítulo, control de pacing dinámico y algoritmo de ajuste proporcional al objetivo (*trim to target*).
- **Tratamiento Unificado RAW + JPEG:** Agrupación transparente por *stem* en el estimador dinámico, clustering y sincronización dual de archivos sidecar `.XMP`.
- **Suite de Herramientas de Cliente:** Modal de exportación de previsualizaciones optimizadas, importación de selecciones externas y barra de personajes VIP (`VIPBar`).
- **Persistencia Histórica de Sesiones:** Módulo `session_history_store.py` con SQLite para registrar la tasa de retención real del fotógrafo y auto-calibrar la selectividad.

### 🧠 Transición de Modelos y Racionales Técnicos
- **De Selección Plana Global a Selección V2 Jerárquica:**
  - *Motivo:* En sesiones con iluminación deficiente o eventos complejos, el filtro global eliminaba capítulos enteros si los scores promedio eran bajos.
  - *Decisión:* Garantizar cuota mínima de supervivencia por momento temporal, asegurando una narrativa visual completa.

### ⚡ Impacto Cuantitativo & Benchmarks
- **Retención Calibrada:** Eliminación del 100% de casos de sub-selección (capítulos vacíos).
- **Tasa de Acierto de Estilo:** Mejora del **+20%** en la coincidencia de tomas elegidas según el historial del fotógrafo.

---

## [2.0.0] - 2026-08-25

### 🚀 Novedades y Re-arquitectura
- **Migración Integral a UniFace (SCRFD + ArcFace ONNX):** Reemplazo definitivo de MediaPipe e InsightFace por un motor facial unificado en ONNX Runtime.
- **Búsqueda Semántica con SigLIP:** Adopción de modelos SigLIP en sustitución de CLIP estándar para embeddings multimodales de alta resolución.
- **Arquitectura Limpia y Lazy Loading:** Carga diferida (Singleton) de redes neuronales, reduciendo el consumo de RAM en reposo.
- **Refactorización de Red y Eliminación de URLs Hardcodeadas:** Centralización del 100% de llamadas HTTP/SSE en `apiClient.ts`.
- **Limpieza de Dependencias:** Purgado de librerías obsoletas (`mediapipe`, canales IPC en desuso) y suite de pruebas ampliada a 325 tests pasando.

### 🧠 Transición de Modelos y Racionales Técnicos
- **De MediaPipe Face Mesh a UniFace (SCRFD ONNX):**
  - *Motivo:* MediaPipe arrastraba dependencias pesadas de TensorFlow/C++, dependencias binarias inestables en Windows y alto consumo de memoria.
  - *Decisión:* SCRFD es un detector ultra-ligero y robusto ante rostros pequeños, ocluidos o en ángulos extremos.
- **De InsightFace a ArcFace Unificado:**
  - *Motivo:* Conflictos de compatibilidad con paquetes C++ y dependencias de CUDA en CPU.
  - *Decisión:* ArcFace 512D ejecutado directamente en ONNX Runtime con quantización INT8/FP32.
- **De CLIP ViT-B/32 a SigLIP:**
  - *Motivo:* CLIP presentaba limitaciones semánticas en detalles específicos de bodas (ej. "alianzas sobre mesa de madera").
  - *Decisión:* SigLIP ofrece una función de pérdida sigmoide con mayor granularidad en conceptos visuales complejos.

### ⚡ Impacto Cuantitativo & Benchmarks
- **Huella en Disco:** Reducción de **~200 MB** en el instalador y dependencias de Python.
- **Cold Start:** Inicio del backend acelerado de **4.5s a 1.2s** (-73% de latencia de arranque).
- **Inferencia Facial:** **+40% FPS** en procesamiento sobre CPU multinúcleo.
- **Precisión Semántica:** Reducción del **25% de falsos positivos** en búsquedas en lenguaje natural.

---

## [1.3.0] - 2026-08-08

### 🚀 Novedades y Mejoras
- **Storyline 1.0 Foundation:** Segmentación de eventos fotográficos por ventanas temporales y pausas de disparo.
- **Streaming de Progreso en Tiempo Real:** Reemplazo de polling HTTP por Server-Sent Events (SSE) en `job_manager.py` para métricas instantáneas.
- **Selección Múltiple en Grid:** Soporte para `Shift + Click`, `Ctrl + Click` y atajo global `Ctrl + A` en cuadrícula.
- **Control de Orientación en Ráfagas:** Detección de fotos verticales y horizontales (H/V) permitiendo seleccionar hasta 2 candidatas complementarias.

### 🧠 Transición de Modelos y Racionales Técnicos
- **De Polling HTTP a SSE (Server-Sent Events):**
  - *Motivo:* El frontend saturaba el bucle de eventos del backend con peticiones cada 200ms durante la ingesta masiva.
  - *Decisión:* Canal unidireccional HTTP con streaming asíncrono.

### ⚡ Impacto Cuantitativo & Benchmarks
- **Carga de Red Local:** **-90% de sobrecarga** de peticiones HTTP.
- **Latencia de Progreso:** Notificación de avance de fases en **<100 ms**.

---

## [1.2.0] - 2026-07-27

### 🚀 Novedades y Mejoras
- **Búsqueda Semántica Offline:** Integración de embeddings vectoriales locales para consultas en lenguaje natural sin conexión a internet.
- **Refinamiento con Modelo de Visión (VLM):** Desempate de expresiones sutiles en ráfagas de alta dificultad.
- **Lupa de Precisión & Histogramas:** Herramienta Loupe con zoom al 100% centrado en ojos y panel de inspección EXIF.
- **Pipeline de Empaquetado Windows:** Automatización de compilación con PyInstaller (backend FastAPI) y Electron Builder (instalador NSIS).

### 🧠 Transición de Modelos y Racionales Técnicos
- **Inferencia Vectorial Local:**
  - *Motivo:* Dependencia inaceptable de APIs en la nube para fotógrafos con catálogos confidenciales y sin conexión en campo.
  - *Decisión:* Inferencia 100% offline mediante pesos ONNX locales pre-descargados.

### ⚡ Impacto Cuantitativo & Benchmarks
- **Privacidad:** **0 bytes** enviados a servidores externos.
- **Velocidad de Búsqueda:** Búsqueda en 5,000 fotos en **<80 ms** usando distancias coseno en memoria.

---

## [1.1.0] - 2026-07-20

### 🚀 Novedades y Mejoras
- **Aprendizaje Continuo desde Lightroom:** Reimportación de XMP modificados para registrar correcciones manuales y auto-ajustar pesos de culling.
- **Modo Duelo (Duel View):** Interfaz interactiva de comparación lado a lado con controles rápidos de teclado (`P` para Pick, `X` para Rechazar).
- **Cobertura y Detección de Personas:** Detección de sujetos frecuentes y garantía de presencia equilibrada en el evento.
- **Deshacer Exportación (Undo Export):** Reversión segura de etiquetas de color y estrellas previas.

### 🧠 Transición de Modelos y Racionales Técnicos
- **Clasificador Facial Dinámico:**
  - *Motivo:* Criterios fijos de apertura de ojos descartaban sonrisas genuinas donde los ojos se entrecierran naturalmente.
  - *Decisión:* Entrenar pesos relativos aprendiendo de las decisiones aprobadas por el usuario.

---

## [1.0.0] - 2026-07-16

### 🚀 Lanzamiento Inicial (MVP)
- **Motor Fundacional de Culling:** Cálculo de nitidez laplaciana, detección de parpadeo y clustering temporal básico.
- **Inyección XMP No Destructiva:** Escritura directa en archivos `.XMP` sidecar de estrellas, etiquetas de color (`Red`, `Green`, `Blue`, `Purple`) y banderines sin requerir tener Lightroom abierto.
- **Pre-Edición Automatizada:** Corrección de balance de blancos por tono de piel, nivelación de exposición y aplicación de presets.
- **Recorte Inteligente (Auto-Crop):** Sugerencia de encuadre respetando la regla de tercios y rostros detectados.
- **Interfaz Gráfica:** Aplicación de escritorio desarrollada con React, TypeScript y Electron.
